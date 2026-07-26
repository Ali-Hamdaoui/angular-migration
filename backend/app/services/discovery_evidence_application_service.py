import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.api.discovery_contracts import DiscoveryEvidenceResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, PhaseStatus, RunPhase, RunStatus, WorkflowEventType
from app.repositories.models import ArtifactMetadataModel, DiscoveryEvidenceModel, G03ApprovalModel, MigrationRunModel, SourceSnapshotModel
from app.repositories.session import session_scope
from app.services.discovery_service import DiscoveryService
from app.state.transition_service import StateTransitionService, TransitionRequest


class DiscoveryEvidenceError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code, self.message, self.status_code = code, message, status_code
        super().__init__(message)


class DiscoveryEvidenceApplicationService:
    def __init__(self, *, session_scope_factory=session_scope, coordinator=None, now_provider=None) -> None:
        self.scope = session_scope_factory
        self.coordinator = coordinator or DiscoveryService()
        self.now = now_provider or (lambda: datetime.now(UTC))

    def capture(self, run_id, request):
        checksum = "sha256:" + hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.scope() as session:
            old = session.scalar(select(DiscoveryEvidenceModel).where(DiscoveryEvidenceModel.run_id == run_id, DiscoveryEvidenceModel.idempotency_key == request.idempotency_key))
            if old:
                if old.request_checksum != checksum:
                    raise DiscoveryEvidenceError("IDEMPOTENCY_KEY_REUSED", "Idempotency key was used with a different payload.", 409)
                return self.dto(old, True)
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise DiscoveryEvidenceError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
            if run.state_version != request.expected_state_version:
                raise DiscoveryEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409)
            if session.scalar(select(G03ApprovalModel).where(G03ApprovalModel.run_id == run_id, G03ApprovalModel.status == "approved")) is None:
                raise DiscoveryEvidenceError("G03_APPROVAL_REQUIRED", "An approved G03 baseline boundary is required.", 409)
            metadata = {item.id.removeprefix("metadata-"): item for item in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id))}
            if any(item not in metadata for item in request.prerequisite_artifact_ids):
                raise DiscoveryEvidenceError("PREREQUISITE_ARTIFACT_NOT_FOUND", "A prerequisite artifact is not registered.", 409)
            if any(metadata[item].checksum != request.prerequisite_artifact_checksums.get(item) for item in request.prerequisite_artifact_ids):
                raise DiscoveryEvidenceError("PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH", "A prerequisite checksum does not match.", 409)
            self.transition(session, run, request, WorkflowEventType.DISCOVERY_STARTED, "discovery started", {}, next_run_phase=RunPhase.DISCOVERY_BASELINE.value, next_phase_status=PhaseStatus.RUNNING.value)
            snapshot = self._authoritative_snapshot(session, run_id)
            workspace = Path(snapshot.snapshot_path).resolve(strict=True)
            snapshot_id = snapshot.id
        try:
            results, drafts = self.coordinator.discover(workspace)
        except Exception as error:
            return self.block(run_id, request, checksum, str(error))
        with self.scope() as session:
            run = session.get(MigrationRunModel, run_id)
            store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
            ids, checks = [], {}
            by_scanner = {item.scanner: item for item in results}
            for draft in drafts:
                scanner = by_scanner[draft.name.removesuffix("_inventory.json")]
                artifact = store.write_text_artifact(run_id, "02_analysis/" + draft.name, draft.content, ArtifactType.JSON, created_by="discovery-evidence", created_at=self.now(), input_hashes=self._input_hashes(workspace, scanner.findings, snapshot_id), policy_version=DiscoveryService.policy_version)
                ids.append(artifact.ref.artifact_id); checks[artifact.ref.artifact_id] = artifact.ref.checksum
                session.add(ArtifactMetadataModel(id="metadata-" + artifact.ref.artifact_id, run_id=run_id, stage_id=None, artifact_type=artifact.ref.artifact_type.value, relative_path=artifact.ref.relative_path, checksum=artifact.ref.checksum, created_at=artifact.ref.created_at))
                self.transition(session, run, request, WorkflowEventType.SCANNER_COMPLETED, "scanner completed", {"scanner": scanner.scanner, "artifact_id": artifact.ref.artifact_id, "discovery_root": str(workspace), "snapshot_id": snapshot_id})
            blocked = any(item.status != "completed" for item in results)
            blocked_scanners = [item.scanner for item in results if item.status != "completed"]
            unknown_reasons = {item.scanner: list(item.unknowns) for item in results if item.status != "completed"}
            error_code = "DISCOVERY_SCANNER_BLOCKED" if blocked else None
            event = self.transition(session, run, request, WorkflowEventType.DISCOVERY_BLOCKED if blocked else WorkflowEventType.DISCOVERY_COMPLETED, "discovery blocked" if blocked else "discovery completed", {"artifact_count": len(ids), "error_code": error_code, "blocked_scanners": blocked_scanners, "unknown_reasons": unknown_reasons}, next_run_phase=RunPhase.DISCOVERY_BASELINE.value, next_phase_status=PhaseStatus.BLOCKED.value if blocked else PhaseStatus.COMPLETED.value, next_run_status=RunStatus.DIAGNOSTIC_HOLD if blocked else None)
            row = DiscoveryEvidenceModel(id="discovery-" + uuid4().hex[:12], run_id=run_id, idempotency_key=request.idempotency_key, request_checksum=checksum, actor=request.actor, status="blocked" if blocked else "completed", scanner_results=[item.model_dump(mode="json") for item in results], artifact_ids=ids, artifact_checksums=checks, prerequisite_artifact_ids=request.prerequisite_artifact_ids, error_code="DISCOVERY_SCANNER_BLOCKED" if blocked else None, state_version=event.next_state_version, event_sequence=event.event_sequence, created_at=self.now(), updated_at=self.now())
            session.add(row); session.flush(); return self.dto(row)

    def block(self, run_id, request, checksum, message):
        with self.scope() as session:
            run = session.get(MigrationRunModel, run_id)
            event = self.transition(session, run, request, WorkflowEventType.DISCOVERY_BLOCKED, "discovery dependency failed", {"error_code": "DISCOVERY_DEPENDENCY_FAILED", "blocked_scanners": [], "unknown_reasons": {}}, next_run_phase=RunPhase.DISCOVERY_BASELINE.value, next_phase_status=PhaseStatus.BLOCKED.value, next_run_status=RunStatus.DIAGNOSTIC_HOLD)
            row = DiscoveryEvidenceModel(id="discovery-" + uuid4().hex[:12], run_id=run_id, idempotency_key=request.idempotency_key, request_checksum=checksum, actor=request.actor, status="blocked", scanner_results=[], artifact_ids=[], artifact_checksums={}, prerequisite_artifact_ids=request.prerequisite_artifact_ids, error_code="DISCOVERY_DEPENDENCY_FAILED", state_version=event.next_state_version, event_sequence=event.event_sequence, created_at=self.now(), updated_at=self.now())
            session.add(row); session.flush(); return self.dto(row)

    def get(self, run_id):
        with self.scope() as session:
            row = session.scalar(select(DiscoveryEvidenceModel).where(DiscoveryEvidenceModel.run_id == run_id).order_by(DiscoveryEvidenceModel.created_at.desc()))
            return self.dto(row) if row else None

    @staticmethod
    def _authoritative_snapshot(session, run_id):
        snapshot = session.scalar(select(SourceSnapshotModel).where(SourceSnapshotModel.run_id == run_id, SourceSnapshotModel.status == "created").order_by(SourceSnapshotModel.created_at.desc()))
        if snapshot is None:
            raise DiscoveryEvidenceError("SOURCE_SNAPSHOT_NOT_FOUND", "A persisted source snapshot is required before discovery.", 409)
        return snapshot

    @staticmethod
    def _input_hashes(root: Path, findings, snapshot_id: str) -> dict[str, str]:
        references = sorted({reference for finding in findings for reference in finding.source_references if reference in {"package.json", "angular.json"}})
        checksums = {reference: "sha256:" + hashlib.sha256((root / reference).read_bytes()).hexdigest() for reference in references if (root / reference).is_file()}
        combined = "sha256:" + hashlib.sha256(json.dumps(checksums, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {"authoritative_snapshot_id": snapshot_id, "snapshot_id": snapshot_id, "input_relative_path": ",".join(references), "input_checksum": combined, "policy_version": DiscoveryService.policy_version, **{f"{Path(reference).stem}_checksum": checksum for reference, checksum in checksums.items()}}

    def transition(self, session, run, request, event, reason, payload, **changes):
        return StateTransitionService(session).apply_transition(TransitionRequest(run_id=run.id, expected_state_version=run.state_version, idempotency_key=request.idempotency_key + ":" + event.value + ":" + str(payload.get("scanner", "")), event_type=event, actor=request.actor, reason=reason, occurred_at=self.now(), payload=payload, **changes))

    def dto(self, row, replay=False):
        return DiscoveryEvidenceResponse(run_id=row.run_id, discovery_id=row.id, status=row.status, scanner_results=row.scanner_results, artifact_ids=row.artifact_ids, artifact_checksums=row.artifact_checksums, prerequisite_artifact_ids=row.prerequisite_artifact_ids, error_code=row.error_code, state_version=row.state_version, event_sequence=row.event_sequence, idempotent_replay=replay)




