"""Durable application service for the S1-F08 G02 boundary."""

from __future__ import annotations

import json
import hashlib
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, RunStatus, WorkflowEventType
from app.domain.g02 import (
    G02ApprovalPackage,
    G02ApprovalPackageBuilder,
    G02ApprovalResult,
    G02ApprovalService,
    G02Decision,
)
from app.repositories.g02_models import G02ApprovalModel
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel, SourceSnapshotModel
from app.repositories.session import session_scope
from app.state.transition_service import StateTransitionService, TransitionRequest
from app.snapshots import SnapshotIntegrityError, SnapshotService, SourceIntegrityVerifier


class G02ApplicationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class G02ApprovalApplicationService:
    GATE_ID = "G02"
    GATE_VERSION = "g02-v1"
    SOURCE_INTEGRITY_POLICY_VERSION = "source-snapshot-policy-v1"

    def __init__(self, *, session_scope_factory=session_scope, now_provider=None, policy_version: str | None = None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._policy_version = policy_version or self.SOURCE_INTEGRITY_POLICY_VERSION

    def get(self, run_id: str, gate_id: str):
        if gate_id != self.GATE_ID:
            return None
        with self._scope() as session:
            record = session.scalar(
                select(G02ApprovalModel)
                .where(G02ApprovalModel.run_id == run_id)
                .order_by(G02ApprovalModel.created_at.desc())
            )
            return self._dto(record) if record else None

    def authorize_baseline(self, run_id: str) -> G02ApprovalPackage:
        """Resolve and verify the persisted G02 approval used by baseline creation."""
        with self._scope() as session:
            record = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == run_id).order_by(G02ApprovalModel.created_at.desc()))
            if record is None or record.status not in {G02Decision.APPROVED.value, G02Decision.APPROVED_WITH_COMMENT.value}:
                raise G02ApplicationError("BASELINE_G02_REQUIRED", "An approved G02 boundary is required.", status_code=409)
            if not self._revalidate_record(session, record):
                run = session.get(MigrationRunModel, run_id)
                if run is not None:
                    self._mark_stale(session, run, record, "G02 evidence or policy version is stale.")
                raise G02ApplicationError("STALE_EVIDENCE", "The approved G02 boundary is stale.", status_code=409)
            return G02ApprovalPackage.model_validate(record.package)

    def initialize(self, run_id: str, request) -> object:
        """Create the review package without recording a decision."""
        if request.gate_id != self.GATE_ID:
            raise G02ApplicationError("GATE_NOT_FOUND", "Only G02 is supported by this endpoint.", status_code=404)
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G02ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            existing = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == run_id).order_by(G02ApprovalModel.created_at.desc()))
            if existing is not None:
                return self._dto(existing, replay=True)
            if run.state_version != request.expected_state_version:
                raise G02ApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)
            record = self._create_pending_record(session, run, request.actor, request.idempotency_key, now)
            return self._dto(record)

    def _create_pending_record(self, session, run, actor: str, idempotency_key: str, now: datetime):
        package, artifact_ids = self._create_package(session, run, actor, now)
        created = StateTransitionService(session).apply_transition(TransitionRequest(
            run_id=run.id, expected_state_version=run.state_version,
            idempotency_key=f"{idempotency_key}:created", event_type=WorkflowEventType.G02_CREATED,
            actor=actor, reason="G02 evidence package created", occurred_at=now,
            payload={"snapshot_id": package.snapshot_id, "package_checksum": package.package_checksum},
        ))
        integrity_event = StateTransitionService(session).apply_transition(TransitionRequest(
            run_id=run.id, expected_state_version=created.next_state_version,
            idempotency_key=f"{idempotency_key}:integrity",
            event_type=(WorkflowEventType.SOURCE_INTEGRITY_VERIFIED if package.source_integrity_verified else WorkflowEventType.SOURCE_INTEGRITY_FAILED),
            next_phase_status="waiting_approval" if package.source_integrity_verified else "blocked",
            next_approval_status="pending" if package.source_integrity_verified else "rejected",
            actor=actor, reason="G02 source integrity evaluated", occurred_at=now,
            payload={"snapshot_id": package.snapshot_id, "source_fingerprint": package.source_fingerprint},
        ))
        record = G02ApprovalModel(
            id=f"g02-{uuid4().hex[:12]}", run_id=run.id, gate_id=self.GATE_ID,
            gate_version=package.gate_version, idempotency_key=idempotency_key, actor=actor,
            status="pending", package=package.model_dump(mode="json"),
            package_checksum=package.package_checksum, artifact_set_checksum=package.artifact_set_checksum,
            snapshot_id=package.snapshot_id, state_version=integrity_event.next_state_version,
            event_sequence=integrity_event.event_sequence, artifact_ids=artifact_ids,
            created_at=now, updated_at=now,
        )
        session.add(record)
        session.flush()
        return record

    def decide(self, run_id: str, request) -> object:
        if request.gate_id != self.GATE_ID:
            raise G02ApplicationError("GATE_NOT_FOUND", "Only G02 is supported by this endpoint.", status_code=404)
        now = self._now()
        with self._scope() as session:
            existing_event = self._find_event(session, run_id, request.idempotency_key)
            if existing_event:
                record = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == run_id).order_by(G02ApprovalModel.created_at.desc()))
                if record is None or not self._revalidate_record(session, record):
                    if record is not None:
                        run = session.get(MigrationRunModel, run_id)
                        if run is not None:
                            self._mark_stale(session, run, record, "G02 evidence or policy version is stale.")
                            session.commit()
                    raise G02ApplicationError("STALE_EVIDENCE", "The G02 evidence or package checksum is stale.", status_code=409)
                return self._dto(record, replay=True)
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G02ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            if run.state_version != request.expected_state_version:
                raise G02ApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)
            record = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == run_id).order_by(G02ApprovalModel.created_at.desc()))
            if record is None:
                package, artifact_ids = self._create_package(session, run, request.actor, now)
                created = StateTransitionService(session).apply_transition(
                    TransitionRequest(
                        run_id=run_id, expected_state_version=run.state_version,
                        idempotency_key=f"{request.idempotency_key}:created",
                        event_type=WorkflowEventType.G02_CREATED, actor=request.actor,
                        reason="G02 evidence package created", occurred_at=now,
                        payload={"snapshot_id": package.snapshot_id, "package_checksum": package.package_checksum},
                    )
                )
                integrity_event = StateTransitionService(session).apply_transition(
                    TransitionRequest(
                        run_id=run_id, expected_state_version=created.next_state_version,
                        idempotency_key=f"{request.idempotency_key}:integrity",
                        event_type=(WorkflowEventType.SOURCE_INTEGRITY_VERIFIED if package.source_integrity_verified else WorkflowEventType.SOURCE_INTEGRITY_FAILED),
                        next_phase_status="waiting_approval" if package.source_integrity_verified else "blocked",
                        next_approval_status="pending" if package.source_integrity_verified else "rejected",
                        actor=request.actor, reason="G02 source integrity evaluated", occurred_at=now,
                        payload={"snapshot_id": package.snapshot_id, "source_fingerprint": package.source_fingerprint},
                    )
                )
                record = G02ApprovalModel(
                    id=f"g02-{uuid4().hex[:12]}", run_id=run_id, gate_id=self.GATE_ID,
                    gate_version=package.gate_version, idempotency_key=request.idempotency_key,
                    actor=request.actor, status="pending", package=package.model_dump(mode="json"),
                    package_checksum=package.package_checksum, artifact_set_checksum=package.artifact_set_checksum,
                    snapshot_id=package.snapshot_id, state_version=integrity_event.next_state_version,
                    event_sequence=integrity_event.event_sequence, artifact_ids=artifact_ids,
                    created_at=now, updated_at=now,
                )
                session.add(record)
                session.flush()
            elif not self._revalidate_record(session, record):
                self._mark_stale(session, run, record, "G02 evidence or policy version is stale.")
                return self._dto(record)
            package = G02ApprovalPackage.model_validate(record.package)
            result: G02ApprovalResult = G02ApprovalService().decide(package, request.decision, comment=request.comment)
            event_type = WorkflowEventType.G02_APPROVED if result.decision in {G02Decision.APPROVED, G02Decision.APPROVED_WITH_COMMENT} else WorkflowEventType.G02_REJECTED
            if result.stale:
                event_type = WorkflowEventType.G02_STALE
            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id, expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key, event_type=event_type,
                    next_phase_status=("running" if event_type == WorkflowEventType.G02_APPROVED else "blocked"),
                    next_approval_status=("approved" if event_type == WorkflowEventType.G02_APPROVED else "rejected"),
                    actor=request.actor, reason=result.reason or "G02 decision recorded", occurred_at=now,
                    payload={"package_checksum": package.package_checksum, "decision": result.decision.value},
                )
            )
            record.status = "stale" if result.stale else result.decision.value
            record.decision = result.decision.value
            record.baseline_input_boundary = result.baseline_input_boundary
            record.stale_reason = result.reason if result.stale else None
            record.comment = request.comment
            record.state_version = transition.next_state_version
            record.event_sequence = transition.event_sequence
            record.updated_at = now
            session.flush()
            return self._dto(record)

    def _create_package(self, session, run, actor: str, now: datetime) -> tuple[G02ApprovalPackage, list[str]]:
        snapshot = session.scalar(select(SourceSnapshotModel).where(SourceSnapshotModel.run_id == run.id).order_by(SourceSnapshotModel.created_at.desc()))
        if snapshot is None or snapshot.status != "created" or not snapshot.fingerprint:
            raise G02ApplicationError("SNAPSHOT_NOT_READY", "A created immutable source snapshot is required.", status_code=409)
        artifact_rows = list(session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run.id)))
        source_artifact_ids = set(snapshot.artifact_ids or [])
        refs = []
        from app.domain.contracts import ArtifactRefDto
        for row in artifact_rows:
            artifact_id = row.id.removeprefix("metadata-")
            if artifact_id in source_artifact_ids:
                refs.append(ArtifactRefDto(artifact_id=artifact_id, run_id=run.id, stage_id=row.stage_id, artifact_type=ArtifactType(row.artifact_type), relative_path=row.relative_path, created_at=row.created_at, checksum=row.checksum))

        inspected = None
        source_integrity_verified = False
        after_source_fingerprint = "sha256:source-unavailable"
        try:
            inspected = SnapshotService(Path(snapshot.snapshot_path).parent).inspect_snapshot(snapshot.id)
            source_integrity_verified = SourceIntegrityVerifier().verify(Path(snapshot.source_path), inspected.manifest)
            after_source_fingerprint = _manifest_fingerprint(Path(snapshot.source_path))
        except (OSError, ValueError, SnapshotIntegrityError):
            source_integrity_verified = False
        if inspected is None:
            raise G02ApplicationError("SNAPSHOT_EVIDENCE_INVALID", "Snapshot evidence could not be inspected.", status_code=409)

        manifest = inspected.manifest
        if manifest.policy_version != self._policy_version:
            raise G02ApplicationError("SOURCE_INTEGRITY_POLICY_STALE", "The snapshot uses an unsupported source-integrity policy version.", status_code=409)
        manifest_payload = {
            "manifest_id": manifest.manifest_id, "source_root": manifest.source_root,
            "generated_at": manifest.generated_at.isoformat(), "checksum": manifest.checksum,
            "policy_version": manifest.policy_version,
            "entries": [asdict(item) for item in manifest.entries],
            "exclusions": [asdict(item) for item in manifest.exclusions],
        }
        snapshot_root = Path(snapshot.snapshot_path)
        readonly_verified = all(not path.is_file() or not (path.stat().st_mode & 0o200) for path in snapshot_root.rglob("*")) and not (snapshot_root.stat().st_mode & 0o200)
        source_integrity_verified = source_integrity_verified and readonly_verified
        store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
        evidence_refs = []

        def write_evidence(name: str, payload: dict) -> None:
            stored = store.write_text_artifact(run.id, f"global/g02/{snapshot.id}/{name}", json.dumps(payload, sort_keys=True, indent=2), ArtifactType.JSON, created_by="g02-approval-service", created_at=now, input_hashes={"source_fingerprint": snapshot.fingerprint, "snapshot_fingerprint": inspected.fingerprint}, policy_version=manifest.policy_version)
            evidence_refs.append(stored.ref)
            session.add(ArtifactMetadataModel(id=f"metadata-{stored.ref.artifact_id}", run_id=run.id, stage_id=None, artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, created_at=now))

        write_evidence("source_integrity_before.json", {"fingerprint": snapshot.fingerprint, "manifest": manifest_payload, "git_metadata": snapshot.git_metadata or {}, "policy_version": manifest.policy_version})
        write_evidence("source_integrity_after_snapshot.json", {"fingerprint": after_source_fingerprint, "matches_before": source_integrity_verified, "manifest_checksum": manifest.checksum, "policy_version": manifest.policy_version})
        write_evidence("source_read_only_verification.json", {"snapshot_id": snapshot.id, "verified": readonly_verified, "snapshot_path": str(snapshot_root)})
        index_refs = refs + evidence_refs
        write_evidence("g02_evidence_index.json", {"snapshot_manifest": manifest_payload, "exclusions": [asdict(item) for item in manifest.exclusions], "copy_report": {"snapshot_id": snapshot.id, "status": "created", "file_count": len(manifest.entries)}, "git_metadata": snapshot.git_metadata or {}, "fingerprints": {"source_before": snapshot.fingerprint, "source_after": after_source_fingerprint, "snapshot": inspected.fingerprint}, "artifact_refs": [item.model_dump(mode="json") for item in index_refs]})
        all_refs = refs + evidence_refs
        package = G02ApprovalPackageBuilder().build(
            run_id=run.id, state_version=run.state_version, actor=actor, snapshot_id=snapshot.id,
            gate_version=self.GATE_VERSION, source_fingerprint=snapshot.fingerprint,
            after_source_fingerprint=after_source_fingerprint, snapshot_fingerprint=inspected.fingerprint,
            manifest_checksum=manifest.checksum, policy_version=manifest.policy_version,
            source_read_only_verified=source_integrity_verified, artifacts=all_refs,
        )
        return package, [item.artifact_id for item in all_refs]
    def _revalidate_record(self, session, record: G02ApprovalModel) -> bool:
        try:
            package = G02ApprovalPackage.model_validate(record.package)
            if package.package_checksum != record.package_checksum or package.artifact_set_checksum != record.artifact_set_checksum:
                return False
            if package.policy_version != self._policy_version or package.integrity.policy_version != self._policy_version:
                return False
            snapshot = session.get(SourceSnapshotModel, record.snapshot_id)
            if snapshot is None or snapshot.status != "created":
                return False
            if package.snapshot_id != record.snapshot_id:
                return False
            inspected = SnapshotService(Path(snapshot.snapshot_path).parent).inspect_snapshot(snapshot.id)
            if inspected.manifest.policy_version != self._policy_version:
                return False
            source_verified = SourceIntegrityVerifier().verify(Path(snapshot.source_path), inspected.manifest)
            if not source_verified or not _snapshot_is_read_only(Path(snapshot.snapshot_path)):
                return False
            if package.source_fingerprint != snapshot.fingerprint or package.snapshot_fingerprint != inspected.fingerprint:
                return False
            if not package.integrity.is_verified or package.integrity.after_snapshot_fingerprint != _manifest_fingerprint(Path(snapshot.source_path)):
                return False
            return package.package_checksum == record.package_checksum and package.artifact_set_checksum == record.artifact_set_checksum
        except (OSError, ValueError, SnapshotIntegrityError, AttributeError):
            return False

    def _mark_stale(self, session, run: MigrationRunModel, record: G02ApprovalModel, reason: str) -> None:
        if record.status == "stale":
            return
        transition = StateTransitionService(session).apply_transition(TransitionRequest(
            run_id=run.id, expected_state_version=run.state_version, idempotency_key=f"g02-stale-{record.id}",
            event_type=WorkflowEventType.G02_STALE, actor="g02-approval-service", reason=reason,
            next_run_status=RunStatus.DIAGNOSTIC_HOLD,
            next_phase_status="blocked", next_approval_status="rejected",
            occurred_at=self._now(), payload={"package_checksum": record.package_checksum},
        ))
        record.status = "stale"
        record.stale_reason = reason
        record.state_version = transition.next_state_version
        record.event_sequence = transition.event_sequence
        record.updated_at = self._now()
        session.flush()

    def _find_event(self, session, run_id: str, key: str):
        from app.repositories.models import WorkflowEventModel
        return session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id, WorkflowEventModel.idempotency_key == key))

    def _dto(self, record, *, replay: bool = False):
        from app.api.g02_contracts import G02ReviewResponse
        package = dict(record.package)
        integrity = dict(package.get("integrity") or {})
        # `status` is a derived property of the immutable evidence model and is
        # intentionally not part of the checksum-bound persisted package.  It
        # is nevertheless part of the public API contract consumed by the UI.
        integrity["status"] = "verified" if (
            integrity.get("source_read_only_verified")
            and integrity.get("before_fingerprint") == integrity.get("after_snapshot_fingerprint")
        ) else "failed"
        package["integrity"] = integrity
        return G02ReviewResponse(run_id=record.run_id, gate_id=record.gate_id, gate_version=record.gate_version, status=record.status, decision=record.decision, package=package, baseline_input_boundary=record.baseline_input_boundary, state_version=record.state_version, event_sequence=record.event_sequence, idempotent_replay=replay, stale_reason=record.stale_reason, comment=record.comment)

def _manifest_fingerprint(source_root: Path) -> str:
    from app.snapshots import SourceManifestBuilder
    manifest = SourceManifestBuilder().build(source_root)
    return f"sha256:{hashlib.sha256(manifest.checksum.encode('utf-8')).hexdigest()}"
def _snapshot_is_read_only(root: Path) -> bool:
    try:
        return all(not path.is_file() or not (path.stat().st_mode & 0o200) for path in root.rglob("*")) and not (root.stat().st_mode & 0o200)
    except OSError:
        return False






