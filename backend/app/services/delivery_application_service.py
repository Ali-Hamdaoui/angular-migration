"""Durable application service for the S4-F13 G14 delivery boundary."""
from __future__ import annotations
import hashlib, json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactRefDto, ArtifactType, WorkflowEventType
from app.domain.delivery import (
    DeliveryCandidate, G14ApprovalPackage, G14ApprovalPackageBuilder,
    G14ApprovalResult, G14ApprovalService, G14Decision,
)
from app.repositories.delivery_models import DeliveryRecordModel
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel
from app.repositories.session import session_scope
from app.state.transition_service import StateTransitionService, TransitionRequest
from app.delivery.services import DeliveryService, DeliveryManifest


class DeliveryApplicationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class DeliveryApplicationService:
    GATE_ID = "G14"
    GATE_VERSION = "g14-v1"

    def __init__(self, *, session_scope_factory=session_scope, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))

    def get(self, run_id: str, gate_id: str):
        if gate_id != self.GATE_ID:
            return None
        with self._scope() as session:
            record = session.scalar(
                select(DeliveryRecordModel)
                .where(DeliveryRecordModel.run_id == run_id)
                .order_by(DeliveryRecordModel.created_at.desc())
            )
            if record is not None and record.status != "stale" and not self._revalidate_record(session, record):
                run = session.get(MigrationRunModel, run_id)
                if run is not None:
                    self._mark_stale(session, run, record, "G14 evidence is stale.")
            return self._dto(record) if record else None

    def initialize(self, run_id: str, request) -> object:
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise DeliveryApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            existing = session.scalar(
                select(DeliveryRecordModel)
                .where(DeliveryRecordModel.run_id == run_id)
                .order_by(DeliveryRecordModel.created_at.desc())
            )
            if existing is not None:
                return self._dto(existing, replay=True)
            if run.state_version != request.expected_state_version:
                raise DeliveryApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)
            record, candidate = self._create_candidate(session, run, request.actor, request.idempotency_key, request.destination, now)
            return self._dto(record)

    def decide(self, run_id: str, request) -> object:
        if request.gate_id != self.GATE_ID:
            raise DeliveryApplicationError("GATE_NOT_FOUND", "Only G14 is supported by this endpoint.", status_code=404)
        now = self._now()
        with self._scope() as session:
            existing_event = self._find_event(session, run_id, request.idempotency_key)
            if existing_event:
                record = session.scalar(select(DeliveryRecordModel).where(DeliveryRecordModel.run_id == run_id).order_by(DeliveryRecordModel.created_at.desc()))
                if record is None or not self._revalidate_record(session, record):
                    if record is not None:
                        run = session.get(MigrationRunModel, run_id)
                        if run is not None:
                            self._mark_stale(session, run, record, "G14 evidence is stale.")
                            session.commit()
                    raise DeliveryApplicationError("STALE_EVIDENCE", "The G14 evidence is stale.", status_code=409)
                return self._dto(record, replay=True)
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise DeliveryApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            if run.state_version != request.expected_state_version:
                raise DeliveryApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)
            record = session.scalar(select(DeliveryRecordModel).where(DeliveryRecordModel.run_id == run_id).order_by(DeliveryRecordModel.created_at.desc()))
            if record is None:
                destination = getattr(request, 'destination', None) or "migrated-app"
                record, candidate = self._create_candidate(session, run, request.actor, f"{request.idempotency_key}:create", destination, now)
            package = G14ApprovalPackage.model_validate(record.package)
            result = G14ApprovalService().decide(package, request.decision, comment=request.comment)
            if result.stale:
                event_type = WorkflowEventType.G14_STALE
            elif result.decision == G14Decision.APPROVED_WITH_COMMENT:
                event_type = WorkflowEventType.G14_APPROVED
            elif result.decision == G14Decision.APPROVED:
                event_type = WorkflowEventType.G14_APPROVED
            elif result.decision == G14Decision.MODIFICATION_REQUESTED:
                event_type = WorkflowEventType.G14_MODIFICATION_REQUESTED
            else:
                event_type = WorkflowEventType.G14_REJECTED
            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id, expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key, event_type=event_type,
                    actor=request.actor, reason=result.reason or "G14 decision recorded", occurred_at=now,
                    payload={"package_checksum": package.package_checksum, "decision": result.decision.value},
                )
            )
            record.status = "stale" if result.stale else result.decision.value
            record.decision = result.decision.value
            record.state_version = transition.next_state_version
            record.event_sequence = transition.event_sequence
            record.comment = request.comment
            record.updated_at = now
            session.flush()
            return self._dto(record)

    def _create_candidate(self, session, run, actor: str, idempotency_key: str, destination: str, now: datetime):
        store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
        artifact_refs = []

        def write_evidence(name: str, payload: dict):
            stored = store.write_text_artifact(run.id, f"delivery/{uuid4().hex[:8]}/{name}", json.dumps(payload, sort_keys=True, indent=2), ArtifactType.JSON, created_by="delivery-application-service", created_at=now)
            artifact_refs.append(stored.ref)
            session.add(ArtifactMetadataModel(id=f"metadata-{stored.ref.artifact_id}", run_id=run.id, stage_id=None, artifact_type=stored.ref.artifact_type.value, relative_path=stored.ref.relative_path, checksum=stored.ref.checksum, created_at=now))

        # Create a delivery candidate fingerprint
        candidate_data = {"run_id": run.id, "actor": actor, "destination": destination, "run_status": run.status}
        candidate_fingerprint = "sha256:" + hashlib.sha256(json.dumps(candidate_data, sort_keys=True).encode("utf-8")).hexdigest()
        write_evidence("delivery_candidate.json", {"run_id": run.id, "candidate_fingerprint": candidate_fingerprint, "destination": destination, "actor": actor})
        write_evidence("candidate_fingerprint.json", {"fingerprint": candidate_fingerprint, "run_status": run.status})
        candidate = DeliveryCandidate(
            delivery_id=f"delivery-{uuid4().hex[:12]}", run_id=run.id,
            candidate_fingerprint=candidate_fingerprint,
            destination=destination, publication_status="candidate_ready",
            artifact_refs=tuple(artifact_refs),
        )
        package = G14ApprovalPackageBuilder().build(
            run_id=run.id, state_version=run.state_version, actor=actor,
            gate_version=self.GATE_VERSION, candidate=candidate,
            artifacts=tuple(artifact_refs),
        )
        started_event = StateTransitionService(session).apply_transition(TransitionRequest(
            run_id=run.id, expected_state_version=run.state_version,
            idempotency_key=f"{idempotency_key}:started", event_type=WorkflowEventType.DELIVERY_CANDIDATE_READY,
            actor=actor, reason="Delivery candidate created", occurred_at=now,
            payload={"candidate_fingerprint": candidate_fingerprint, "destination": destination},
        ))
        created_event = StateTransitionService(session).apply_transition(TransitionRequest(
            run_id=run.id, expected_state_version=started_event.next_state_version,
            idempotency_key=f"{idempotency_key}:created", event_type=WorkflowEventType.G14_CREATED,
            actor=actor, reason="G14 evidence package created", occurred_at=now,
            payload={"candidate_fingerprint": candidate_fingerprint, "package_checksum": package.package_checksum},
        ))
        record = DeliveryRecordModel(
            id=f"g14-{uuid4().hex[:12]}", run_id=run.id, gate_id=self.GATE_ID,
            gate_version=package.gate_version, idempotency_key=idempotency_key, actor=actor,
            status="pending", package=package.model_dump(mode="json"),
            package_checksum=package.package_checksum, artifact_set_checksum=package.artifact_set_checksum,
            destination=destination, published_fingerprint=None,
            state_version=created_event.next_state_version, event_sequence=created_event.event_sequence,
            artifact_ids=[r.artifact_id for r in artifact_refs],
            created_at=now, updated_at=now,
        )
        session.add(record)
        session.flush()
        return record, candidate

    def _revalidate_record(self, session, record: DeliveryRecordModel) -> bool:
        try:
            package = G14ApprovalPackage.model_validate(record.package)
            if package.package_checksum != record.package_checksum or package.artifact_set_checksum != record.artifact_set_checksum:
                return False
            run = session.get(MigrationRunModel, record.run_id)
            if run is None or not run.artifact_root:
                return False
            metadata = {row.id.removeprefix("metadata-"): row for row in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == record.run_id))}
            store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
            for ref in package.artifacts:
                row = metadata.get(ref.artifact_id)
                if row is None or row.checksum != ref.checksum:
                    return False
                stored = store.read_artifact_by_id(ref.artifact_id)
                if stored.ref.checksum != ref.checksum or f"sha256:{hashlib.sha256(stored.content.encode('utf-8')).hexdigest()}" != ref.checksum:
                    return False
            rebuilt = G14ApprovalPackageBuilder().build(
                run_id=package.run_id, state_version=package.state_version, actor=package.actor,
                gate_version=package.gate_version, candidate=package.candidate, artifacts=tuple(package.artifacts),
            )
            return rebuilt.package_checksum == package.package_checksum and rebuilt.artifact_set_checksum == package.artifact_set_checksum
        except (OSError, ValueError, AttributeError):
            return False

    def _mark_stale(self, session, run, record, reason: str) -> None:
        if record.status == "stale":
            return
        transition = StateTransitionService(session).apply_transition(TransitionRequest(
            run_id=run.id, expected_state_version=run.state_version,
            idempotency_key=f"g14-stale-{record.id}", event_type=WorkflowEventType.G14_STALE,
            actor="delivery-application-service", reason=reason, occurred_at=self._now(),
            payload={"package_checksum": record.package_checksum},
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
        from app.api.delivery_contracts import DeliveryResponse
        return DeliveryResponse(run_id=record.run_id, gate_id=record.gate_id, gate_version=record.gate_version,
            status=record.status, decision=record.decision, candidate=record.package,
            state_version=record.state_version, event_sequence=record.event_sequence,
            idempotent_replay=replay, stale_reason=record.stale_reason, comment=record.comment)
