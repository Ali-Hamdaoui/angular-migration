"""Durable checksum-bound production preflight and G01 decisions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.core.config import Settings
from app.domain.preflight import G01Decision, G01DecisionRequest, PreflightRequest, PreflightResult, PreflightSnapshot
from app.domain.system import EnvironmentCapabilitySnapshot
from app.domain.path_validation import PathValidationSnapshot
from app.domain.source_analysis import SourceAnalysisSnapshot
from app.repositories.models import EnvironmentCapabilityModel, PathValidationModel, SourceAnalysisModel, TargetReservationModel
from app.repositories.preflight_models import ApprovalGateModel, PreflightArtifactMetadataModel, PreflightModel, UserDecisionModel
from app.repositories.session import session_scope
from app.state.preflight_transition_service import PreflightTransitionService
from app.services.preflight_events import append_preflight_event
from app.domain.contracts import ArtifactType
from app.services.migration_workspace_layout_service import MigrationWorkspaceLayoutService, WorkspaceLayoutError

GATE_ID = "G01"
GATE_VERSION = "s1-g01-v1"
EXPIRY = timedelta(minutes=15)


class PreflightError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


class ProductionPreflightService:
    def __init__(self, settings: Settings, *, session_scope_factory=session_scope, now_provider=None) -> None:
        self._settings = settings
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._layout = MigrationWorkspaceLayoutService(platform_repository_root=settings.platform_repository_root)
        self._fallback_artifact_root = settings.artifact_root

    def create(self, request: PreflightRequest) -> PreflightResult:
        with self._scope() as session:
            existing = session.scalar(select(PreflightModel).where(PreflightModel.idempotency_key == request.idempotency_key))
            if existing:
                binding = existing.binding or {}
                path = session.get(PathValidationModel, binding.get("path_validation_id"))
                if path is None:
                    raise PreflightError("TARGET_RESERVATION_INVALID", "The bound path validation record is missing.")
                path_snapshot = PathValidationSnapshot.model_validate(path.snapshot)
                self._require_live_reservation(session, path, path_snapshot)
                return PreflightResult(snapshot=PreflightSnapshot.model_validate(existing.snapshot))
            path = session.get(PathValidationModel, request.path_validation_id)
            environment = session.get(EnvironmentCapabilityModel, request.environment_snapshot_id)
            analysis = session.get(SourceAnalysisModel, request.source_analysis_id)
            if not path or not environment or not analysis:
                raise PreflightError("PREFLIGHT_PREREQUISITE_MISSING", "Path, environment, and source analysis evidence are required.", status_code=422)
            path_snapshot = PathValidationSnapshot.model_validate(path.snapshot)
            reservation = self._require_live_reservation(session, path, path_snapshot)
            env_snapshot = EnvironmentCapabilitySnapshot.model_validate(environment.snapshot)
            analysis_snapshot = SourceAnalysisSnapshot.model_validate(analysis.snapshot)
            preflight_id = f"preflight-{uuid4().hex[:12]}"
            try:
                output_root = path_snapshot.resolved_output_root or path_snapshot.target_output_path
                self._layout.for_run(output_root, preflight_id)
                # A preflight has no approved run yet. Keep its evidence under the configured
                # external application-data root so validation never creates the selected output.
                metadata_root = self._fallback_artifact_root / "preflights"
                artifacts = LocalFilesystemArtifactStore(metadata_root / preflight_id, fixed_run_root=metadata_root / preflight_id)
            except WorkspaceLayoutError as error:
                raise PreflightError("UNSAFE_WORKSPACE_LAYOUT", str(error), status_code=422) from error
            blockers = sorted(set(path_snapshot.blockers + env_snapshot.blockers + analysis_snapshot.blockers))
            warnings = sorted(set(path_snapshot.warnings + env_snapshot.warnings + analysis_snapshot.warnings))
            binding = {
                "path_validation_id": path.id, "path_checksum": path.checksum,
                "environment_snapshot_id": environment.id, "environment_checksum": environment.checksum,
                "source_analysis_id": analysis.id, "source_analysis_checksum": analysis.checksum,
                "target_angular_family": request.target_angular_family.strip(),
                "migration_mode": request.migration_mode.strip(),
                "target_reservation": {"id": reservation.id, "status": reservation.status, "expires_at": reservation.expires_at.isoformat()} if reservation else None,
                "policy_versions": {"gate": GATE_VERSION, "path": path_snapshot.policy_version, "environment": env_snapshot.policy_version, "analysis": analysis_snapshot.policy_version},
            }
            input_checksum = self._checksum(binding)
            now, expires = self._now(), self._now() + EXPIRY
            prereq = {
                "preflight_request.json": {"request": request.model_dump(mode="json"), "binding": binding},
                "environment_capability_summary.json": env_snapshot.model_dump(mode="json"),
                "path_safety_report.json": path_snapshot.model_dump(mode="json"),
                "eligibility_result.json": analysis_snapshot.model_dump(mode="json"),
            }
            refs: dict[str, dict] = {}
            for name, payload in prereq.items():
                stored = artifacts.write_text_artifact(preflight_id, f"00_job_setup/{name}", json.dumps(payload, sort_keys=True, indent=2), ArtifactType.JSON, created_by="production-preflight-service", created_at=now, input_hashes={"input": input_checksum}, policy_version=GATE_VERSION)
                refs[name] = stored.ref.model_dump(mode="json")
            artifact_set_checksum = self._checksum({name: ref["checksum"] for name, ref in sorted(refs.items())})
            status = "blocked" if blockers else ("passed_with_warnings" if warnings else "passed")
            snapshot = PreflightSnapshot(preflight_id=preflight_id, gate_id=GATE_ID, gate_version=GATE_VERSION, state_version=1, status=status, created_at=now, expires_at=expires, input_checksum=input_checksum, artifact_set_checksum=artifact_set_checksum, target_angular_family=request.target_angular_family.strip(), migration_mode=request.migration_mode.strip(), source_path=path_snapshot.source_path, target_parent_path=path_snapshot.target_parent_path, generated_output_name=path_snapshot.generated_output_name, resolved_output_root=path_snapshot.resolved_output_root, platform_repository_root=path_snapshot.platform_repository_root, target_output_path=path_snapshot.target_output_path, target_reservation_id=reservation.id if reservation else None, approval_status="pending", blockers=blockers, warnings=warnings, artifacts=refs)
            result_ref = artifacts.write_text_artifact(preflight_id, "00_job_setup/preflight_result.json", snapshot.model_dump_json(indent=2), ArtifactType.JSON, created_by="production-preflight-service", created_at=now, input_hashes={"artifact_set": artifact_set_checksum}, policy_version=GATE_VERSION)
            refs["preflight_result.json"] = result_ref.ref.model_dump(mode="json")
            index_ref = artifacts.write_text_artifact(preflight_id, "00_job_setup/g01_evidence_index.json", json.dumps({"gate_id": GATE_ID, "gate_version": GATE_VERSION, "input_checksum": input_checksum, "artifact_set_checksum": artifact_set_checksum, "artifacts": refs}, indent=2, sort_keys=True), ArtifactType.JSON, created_by="production-preflight-service", created_at=now, input_hashes={"artifact_set": artifact_set_checksum}, policy_version=GATE_VERSION)
            refs["g01_evidence_index.json"] = index_ref.ref.model_dump(mode="json")
            snapshot = snapshot.model_copy(update={"artifacts": refs})
            for ref in refs.values():
                session.add(PreflightArtifactMetadataModel(id=f"metadata-{ref['artifact_id']}", preflight_id=preflight_id, artifact_id=ref["artifact_id"], artifact_type=ref["artifact_type"], relative_path=ref["relative_path"], checksum=ref["checksum"], created_at=now))
            session.add(PreflightModel(id=preflight_id, idempotency_key=request.idempotency_key, actor=request.actor, gate_id=GATE_ID, gate_version=GATE_VERSION, status=status, input_checksum=input_checksum, artifact_set_checksum=artifact_set_checksum, expires_at=expires, binding=binding, snapshot=snapshot.model_dump(mode="json"), created_at=now))
            session.add(ApprovalGateModel(id=f"gate-{preflight_id}-g01", preflight_id=preflight_id, gate_id=GATE_ID, gate_version=GATE_VERSION, status="pending", state_version=1, input_checksum=input_checksum, artifact_set_checksum=artifact_set_checksum, expires_at=expires, created_at=now))
            append_preflight_event(session, preflight_id=preflight_id, event_type="PREFLIGHT_CREATED", actor=request.actor, idempotency_key=request.idempotency_key, payload={"input_checksum": input_checksum, "artifact_set_checksum": artifact_set_checksum}, occurred_at=now)
            return PreflightResult(snapshot=snapshot)

    def _require_live_reservation(self, session, path: PathValidationModel, path_snapshot: PathValidationSnapshot) -> TargetReservationModel:
        reservation_id = path_snapshot.reservation_id
        reservation = session.get(TargetReservationModel, reservation_id) if reservation_id else None
        if reservation is None or reservation.validation_id != path.id:
            raise PreflightError("TARGET_RESERVATION_INVALID", "The target reservation is missing or not bound to this path validation.")
        if reservation.target_path != path_snapshot.resolved_output_root:
            raise PreflightError("TARGET_RESERVATION_INVALID", "The target reservation does not match the resolved output root.")
        expires_at = reservation.expires_at if reservation.expires_at.tzinfo else reservation.expires_at.replace(tzinfo=UTC)
        if expires_at <= self._now():
            raise PreflightError("TARGET_RESERVATION_EXPIRED", "The target reservation has expired.")
        if reservation.status not in {"reserved", "eligible"}:
            raise PreflightError("TARGET_RESERVATION_INVALID", "The target reservation is not available for preflight.")
        return reservation

    def get(self, preflight_id: str) -> PreflightResult | None:
        with self._scope() as session:
            row = session.get(PreflightModel, preflight_id)
            if row is None:
                return None
            gate = session.scalar(select(ApprovalGateModel).where(ApprovalGateModel.preflight_id == preflight_id, ApprovalGateModel.gate_id == GATE_ID))
            decisions = list(session.scalars(select(UserDecisionModel).where(UserDecisionModel.preflight_id == preflight_id).order_by(UserDecisionModel.decided_at, UserDecisionModel.id)))
            snapshot = PreflightSnapshot.model_validate(row.snapshot).model_copy(update={"approval_status": gate.status if gate else "pending", "decision_history": [self._decision(item).model_dump(mode="json") for item in decisions]})
            return PreflightResult(snapshot=snapshot)

    def decide(self, preflight_id: str, request: G01DecisionRequest) -> G01Decision:
        with self._scope() as session:
            replay = session.scalar(select(UserDecisionModel).where(UserDecisionModel.idempotency_key == request.idempotency_key))
            if replay:
                return self._decision(replay, replay=True)
            row = session.get(PreflightModel, preflight_id)
            gate = session.scalar(select(ApprovalGateModel).where(ApprovalGateModel.preflight_id == preflight_id, ApprovalGateModel.gate_id == request.gate_id))
            if not row or not gate or request.gate_id != GATE_ID:
                raise PreflightError("G01_NOT_FOUND", "The G01 gate was not found.", status_code=404)
            if request.expected_state_version != gate.state_version:
                raise PreflightError("STALE_STATE_VERSION", "The G01 gate state version is stale.")
            if request.input_checksum != row.input_checksum or request.artifact_set_checksum != row.artifact_set_checksum:
                raise PreflightError("APPROVAL_MARKED_STALE", "G01 evidence checksum does not match the current preflight.")
            path = session.get(PathValidationModel, row.binding["path_validation_id"])
            environment = session.get(EnvironmentCapabilityModel, row.binding["environment_snapshot_id"])
            analysis = session.get(SourceAnalysisModel, row.binding["source_analysis_id"])
            current = (path.checksum if path else None, environment.checksum if environment else None, analysis.checksum if analysis else None)
            bound = (row.binding["path_checksum"], row.binding["environment_checksum"], row.binding["source_analysis_checksum"])
            if current != bound:
                row.status = gate.status = "stale"
                append_preflight_event(session, preflight_id=preflight_id, event_type="APPROVAL_MARKED_STALE", actor=request.actor, idempotency_key=request.idempotency_key, payload={}, occurred_at=self._now())
                raise PreflightError("APPROVAL_MARKED_STALE", "A bound preflight input changed; create a new preflight.")
            required_artifacts = ("preflight_request.json", "environment_capability_summary.json", "path_safety_report.json", "eligibility_result.json")
            snapshot = PreflightSnapshot.model_validate(row.snapshot)
            artifacts = self._artifact_store(snapshot)
            artifact_refs = row.snapshot.get("artifacts", {})
            artifact_checksums = {}
            try:
                for artifact_name in required_artifacts:
                    ref = artifact_refs[artifact_name]
                    stored = artifacts.read_artifact_by_id(ref["artifact_id"])
                    actual_checksum = "sha256:" + hashlib.sha256(stored.content.encode("utf-8")).hexdigest()
                    if actual_checksum != ref["checksum"]:
                        raise ValueError("artifact content checksum changed")
                    artifact_checksums[artifact_name] = actual_checksum
            except (KeyError, OSError, ValueError):
                append_preflight_event(session, preflight_id=preflight_id, event_type="APPROVAL_MARKED_STALE", actor=request.actor, idempotency_key=request.idempotency_key, payload={"reason": "artifact_checksum_changed"}, occurred_at=self._now())
                row.status = gate.status = "stale"
                raise PreflightError("APPROVAL_MARKED_STALE", "A bound artifact changed; create a new preflight.")
            if self._checksum(dict(sorted(artifact_checksums.items()))) != row.artifact_set_checksum:
                append_preflight_event(session, preflight_id=preflight_id, event_type="APPROVAL_MARKED_STALE", actor=request.actor, idempotency_key=request.idempotency_key, payload={"reason": "artifact_set_checksum_changed"}, occurred_at=self._now())
                row.status = gate.status = "stale"
                raise PreflightError("APPROVAL_MARKED_STALE", "The bound artifact set changed; create a new preflight.")
            expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
            if expires_at <= self._now():
                row.status = gate.status = "expired"
                raise PreflightError("PREFLIGHT_EXPIRED", "The preflight has expired.")
            if request.decision in {"approved", "approved_with_comment"} and row.status == "blocked":
                raise PreflightError("PREFLIGHT_BLOCKED", "G01 approval is not allowed while mandatory blockers remain.")
            try:
                PreflightTransitionService().validate(gate=gate, decision=request.decision, expected_state_version=request.expected_state_version)
            except ValueError as error:
                code, _, message = str(error).partition(": ")
                raise PreflightError(code, message) from error
            now = self._now()
            decision = UserDecisionModel(id=f"decision-{uuid4().hex[:12]}", preflight_id=preflight_id, gate_id=GATE_ID, decision=request.decision, actor=request.actor, comment=request.comment, input_checksum=request.input_checksum, artifact_set_checksum=request.artifact_set_checksum, state_version=gate.state_version, idempotency_key=request.idempotency_key, decided_at=now)
            session.add(decision)
            PreflightTransitionService().apply(gate=gate, preflight=row, decision=request.decision)
            event_type = {"approved": "G01_APPROVED", "approved_with_comment": "G01_APPROVED", "modification_requested": "G01_MODIFICATION_REQUESTED", "rejected": "G01_REJECTED"}[request.decision]
            append_preflight_event(session, preflight_id=preflight_id, event_type=event_type, actor=request.actor, idempotency_key=request.idempotency_key, payload={"decision": request.decision, "state_version": gate.state_version}, occurred_at=now)
            return self._decision(decision)

    def _artifact_store(self, snapshot: PreflightSnapshot) -> LocalFilesystemArtifactStore:
        metadata_root = self._fallback_artifact_root / "preflights" / snapshot.preflight_id
        return LocalFilesystemArtifactStore(metadata_root, fixed_run_root=metadata_root)

    @staticmethod
    def _checksum(value: object) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _decision(row: UserDecisionModel, *, replay: bool = False) -> G01Decision:
        return G01Decision(decision_id=row.id, preflight_id=row.preflight_id, gate_id=row.gate_id, decision=row.decision, actor=row.actor, comment=row.comment, decided_at=row.decided_at, input_checksum=row.input_checksum, artifact_set_checksum=row.artifact_set_checksum, state_version=row.state_version, idempotent_replay=replay)
