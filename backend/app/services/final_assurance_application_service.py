"""Durable application service for the S4-F12 G13 final-assurance boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactRefDto, ArtifactType, WorkflowEventType
from app.domain.final_assurance import (
    FinalAssuranceSummary,
    G13ApprovalPackage,
    G13ApprovalPackageBuilder,
    G13ApprovalResult,
    G13ApprovalService,
    G13Decision,
)
from app.repositories.final_assurance_models import FinalAssuranceRecordModel
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel, RunAssuranceStatusModel
from app.repositories.session import session_scope
from app.state.transition_service import StateTransitionService, TransitionRequest


class FinalAssuranceApplicationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class FinalAssuranceApplicationService:
    GATE_ID = "G13"
    GATE_VERSION = "g13-v1"

    def __init__(
        self,
        *,
        session_scope_factory=session_scope,
        now_provider=None,
    ) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))

    def get(self, run_id: str, gate_id: str):
        """Retrieve the most recent final-assurance record for a run and gate."""
        if gate_id != self.GATE_ID:
            return None
        with self._scope() as session:
            record = session.scalar(
                select(FinalAssuranceRecordModel)
                .where(FinalAssuranceRecordModel.run_id == run_id)
                .order_by(FinalAssuranceRecordModel.created_at.desc())
            )
            if record is not None and record.status != "stale" and not self._revalidate_record(session, record):
                run = session.get(MigrationRunModel, run_id)
                if run is not None:
                    self._mark_stale(session, run, record, "G13 evidence or run assurance status is stale.")
            return self._dto(record) if record else None

    def initialize(self, run_id: str, request) -> object:
        """Create the final-assurance review package without recording a decision."""
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise FinalAssuranceApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            existing = session.scalar(
                select(FinalAssuranceRecordModel)
                .where(FinalAssuranceRecordModel.run_id == run_id)
                .order_by(FinalAssuranceRecordModel.created_at.desc())
            )
            if existing is not None:
                return self._dto(existing, replay=True)
            if run.state_version != request.expected_state_version:
                raise FinalAssuranceApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)
            record = self._create_pending_record(session, run, request.actor, request.idempotency_key, now)
            return self._dto(record)

    def decide(self, run_id: str, request) -> object:
        """Record a G13 decision on a final-assurance package."""
        if request.gate_id != self.GATE_ID:
            raise FinalAssuranceApplicationError("GATE_NOT_FOUND", "Only G13 is supported by this endpoint.", status_code=404)
        now = self._now()
        with self._scope() as session:
            existing_event = self._find_event(session, run_id, request.idempotency_key)
            if existing_event:
                record = session.scalar(
                    select(FinalAssuranceRecordModel)
                    .where(FinalAssuranceRecordModel.run_id == run_id)
                    .order_by(FinalAssuranceRecordModel.created_at.desc())
                )
                if record is None or not self._revalidate_record(session, record):
                    if record is not None:
                        run = session.get(MigrationRunModel, run_id)
                        if run is not None:
                            self._mark_stale(session, run, record, "G13 evidence or run assurance status is stale.")
                            session.commit()
                    raise FinalAssuranceApplicationError("STALE_EVIDENCE", "The G13 evidence or package checksum is stale.", status_code=409)
                return self._dto(record, replay=True)
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise FinalAssuranceApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            if run.state_version != request.expected_state_version:
                raise FinalAssuranceApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)
            record = session.scalar(
                select(FinalAssuranceRecordModel)
                .where(FinalAssuranceRecordModel.run_id == run_id)
                .order_by(FinalAssuranceRecordModel.created_at.desc())
            )
            if record is None:
                package, artifact_ids = self._create_package(session, run, request.actor, now)
                started = StateTransitionService(session).apply_transition(
                    TransitionRequest(
                        run_id=run_id, expected_state_version=run.state_version,
                        idempotency_key=f"{request.idempotency_key}:created",
                        event_type=WorkflowEventType.G13_CREATED, actor=request.actor,
                        reason="G13 evidence package created", occurred_at=now,
                        payload={"package_checksum": package.package_checksum},
                    )
                )
                record = FinalAssuranceRecordModel(
                    id=f"g13-{uuid4().hex[:12]}", run_id=run_id, gate_id=self.GATE_ID,
                    gate_version=package.gate_version, idempotency_key=request.idempotency_key,
                    actor=request.actor, status="pending", package=package.model_dump(mode="json"),
                    package_checksum=package.package_checksum, artifact_set_checksum=package.artifact_set_checksum,
                    state_version=started.next_state_version,
                    event_sequence=started.event_sequence, artifact_ids=artifact_ids,
                    created_at=now, updated_at=now,
                )
                session.add(record)
                session.flush()
            elif not self._revalidate_record(session, record):
                self._mark_stale(session, run, record, "G13 evidence or run assurance status is stale.")
                return self._dto(record)
            package = G13ApprovalPackage.model_validate(record.package)
            result: G13ApprovalResult = G13ApprovalService().decide(package, request.decision, comment=request.comment)
            event_type = (
                WorkflowEventType.G13_APPROVED
                if result.decision in {G13Decision.APPROVED, G13Decision.APPROVED_WITH_COMMENT}
                else WorkflowEventType.G13_REJECTED
            )
            if result.stale:
                event_type = WorkflowEventType.G13_STALE
            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id, expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key, event_type=event_type,
                    actor=request.actor, reason=result.reason or "G13 decision recorded", occurred_at=now,
                    payload={"package_checksum": package.package_checksum, "decision": result.decision.value},
                )
            )
            record.status = "stale" if result.stale else result.decision.value
            record.decision = result.decision.value
            record.stale_reason = result.reason if result.stale else None
            record.comment = request.comment
            record.state_version = transition.next_state_version
            record.event_sequence = transition.event_sequence
            record.updated_at = now
            session.flush()
            return self._dto(record)

    def _create_pending_record(
        self, session, run: MigrationRunModel, actor: str, idempotency_key: str, now: datetime,
    ) -> FinalAssuranceRecordModel:
        """Create a pending (undecided) final-assurance record."""
        package, artifact_ids = self._create_package(session, run, actor, now)
        started = StateTransitionService(session).apply_transition(
            TransitionRequest(
                run_id=run.id, expected_state_version=run.state_version,
                idempotency_key=f"{idempotency_key}:started",
                event_type=WorkflowEventType.FINAL_ASSURANCE_STARTED, actor=actor,
                reason="Final assurance started", occurred_at=now,
                payload={"package_checksum": package.package_checksum},
            )
        )
        created = StateTransitionService(session).apply_transition(
            TransitionRequest(
                run_id=run.id, expected_state_version=started.next_state_version,
                idempotency_key=f"{idempotency_key}:created",
                event_type=WorkflowEventType.G13_CREATED, actor=actor,
                reason="G13 evidence package created", occurred_at=now,
                payload={"package_checksum": package.package_checksum},
            )
        )
        record = FinalAssuranceRecordModel(
            id=f"g13-{uuid4().hex[:12]}", run_id=run.id, gate_id=self.GATE_ID,
            gate_version=package.gate_version, idempotency_key=idempotency_key, actor=actor,
            status="pending", package=package.model_dump(mode="json"),
            package_checksum=package.package_checksum, artifact_set_checksum=package.artifact_set_checksum,
            state_version=created.next_state_version,
            event_sequence=created.event_sequence, artifact_ids=artifact_ids,
            created_at=now, updated_at=now,
        )
        session.add(record)
        session.flush()
        return record

    def _create_package(
        self, session, run: MigrationRunModel, actor: str, now: datetime,
    ) -> tuple[G13ApprovalPackage, list[str]]:
        """Build the G13 approval package from run assurance state."""
        assurance = session.get(RunAssuranceStatusModel, run.id)
        if assurance is None:
            raise FinalAssuranceApplicationError(
                "ASSURANCE_NOT_FOUND",
                "Run assurance status is required for final assurance.",
                status_code=409,
            )

        # Collect all run artifacts for evidence reference
        artifact_rows = list(
            session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run.id))
        )
        refs: list[ArtifactRefDto] = []
        for row in artifact_rows:
            artifact_id = row.id.removeprefix("metadata-")
            refs.append(ArtifactRefDto(
                artifact_id=artifact_id, run_id=run.id, stage_id=row.stage_id,
                artifact_type=ArtifactType(row.artifact_type), relative_path=row.relative_path,
                created_at=row.created_at, checksum=row.checksum,
            ))

        # Build a deterministic candidate fingerprint from assurance state and run metadata
        candidate_data = json.dumps({
            "run_id": run.id,
            "state_version": run.state_version,
            "updated_at": run.updated_at.isoformat() if run.updated_at else now.isoformat(),
            "technical_status": assurance.technical_upgrade_status,
            "parity_status": assurance.functional_parity_status,
            "source_integrity_status": assurance.delivery_readiness,
            "security_status": assurance.security_assurance_status,
            "quality_status": assurance.quality_assurance_status,
        }, sort_keys=True, separators=(",", ":"), default=str)
        candidate_fingerprint = "sha256:" + hashlib.sha256(candidate_data.encode("utf-8")).hexdigest()

        summary = FinalAssuranceSummary(
            run_id=run.id,
            candidate_fingerprint=candidate_fingerprint,
            technical_status=assurance.technical_upgrade_status,
            parity_status=assurance.functional_parity_status,
            source_integrity_status=assurance.delivery_readiness,
            security_status=assurance.security_assurance_status,
            quality_status=assurance.quality_assurance_status,
            artifact_refs=tuple(refs),
        )

        # Write evidence artifacts under final_assurance/
        store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
        evidence_refs: list[ArtifactRefDto] = []

        def write_evidence(name: str, payload: dict) -> None:
            stored = store.write_text_artifact(
                run.id, f"final_assurance/{name}",
                json.dumps(payload, sort_keys=True, indent=2),
                ArtifactType.JSON, created_by="g13-approval-service", created_at=now,
                input_hashes={"candidate_fingerprint": candidate_fingerprint},
                policy_version="g13-v1",
            )
            evidence_refs.append(stored.ref)
            session.add(ArtifactMetadataModel(
                id=f"metadata-{stored.ref.artifact_id}", run_id=run.id,
                stage_id=None, artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path, checksum=stored.ref.checksum,
                created_at=now,
            ))

        write_evidence("assurance_summary.json", summary.model_dump(mode="json"))
        write_evidence("candidate_fingerprint.json", {
            "candidate_fingerprint": candidate_fingerprint,
            "assurance": {
                "technical": assurance.technical_upgrade_status,
                "parity": assurance.functional_parity_status,
                "source_integrity": assurance.delivery_readiness,
                "security": assurance.security_assurance_status,
                "quality": assurance.quality_assurance_status,
            },
        })
        write_evidence("run_metadata.json", {
            "run_id": run.id,
            "state_version": run.state_version,
            "status": run.status,
            "run_phase": run.run_phase,
            "phase_status": run.phase_status,
        })

        all_refs = refs + evidence_refs
        package = G13ApprovalPackageBuilder().build(
            run_id=run.id,
            state_version=run.state_version,
            actor=actor,
            gate_version=self.GATE_VERSION,
            summary=summary,
            artifacts=all_refs,
        )
        return package, [item.artifact_id for item in all_refs]

    def _revalidate_record(self, session, record: FinalAssuranceRecordModel) -> bool:
        """Verify the record's package checksum and assurance state are still current."""
        try:
            package = G13ApprovalPackage.model_validate(record.package)
            if package.package_checksum != record.package_checksum or package.artifact_set_checksum != record.artifact_set_checksum:
                return False
            run = session.get(MigrationRunModel, record.run_id)
            if run is None or not run.artifact_root:
                return False
            assurance = session.get(RunAssuranceStatusModel, record.run_id)
            if assurance is None:
                return False
            # Recompute candidate fingerprint and compare
            now = self._now()
            candidate_data = json.dumps({
                "run_id": run.id,
                "state_version": run.state_version,
                "updated_at": run.updated_at.isoformat() if run.updated_at else now.isoformat(),
                "technical_status": assurance.technical_upgrade_status,
                "parity_status": assurance.functional_parity_status,
                "source_integrity_status": assurance.delivery_readiness,
                "security_status": assurance.security_assurance_status,
                "quality_status": assurance.quality_assurance_status,
            }, sort_keys=True, separators=(",", ":"), default=str)
            current_fingerprint = "sha256:" + hashlib.sha256(candidate_data.encode("utf-8")).hexdigest()
            if package.summary.candidate_fingerprint != current_fingerprint:
                return False
            # Verify stored artifact checksums
            metadata = {
                row.id.removeprefix("metadata-"): row
                for row in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == record.run_id))
            }
            store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
            for ref in package.artifacts:
                row = metadata.get(ref.artifact_id)
                if row is None or row.checksum != ref.checksum:
                    return False
                stored = store.read_artifact_by_id(ref.artifact_id)
                if stored.ref.checksum != ref.checksum or f"sha256:{hashlib.sha256(stored.content.encode('utf-8')).hexdigest()}" != ref.checksum:
                    return False
            # Rebuild package and verify checksums match
            rebuilt = G13ApprovalPackageBuilder().build(
                run_id=package.run_id, state_version=package.state_version, actor=package.actor,
                gate_version=package.gate_version, summary=package.summary,
                artifacts=list(package.artifacts),
            )
            return (
                rebuilt.package_checksum == package.package_checksum
                and rebuilt.artifact_set_checksum == package.artifact_set_checksum
            )
        except (OSError, ValueError, AttributeError):
            return False

    def _mark_stale(
        self, session, run: MigrationRunModel, record: FinalAssuranceRecordModel, reason: str,
    ) -> None:
        if record.status == "stale":
            return
        transition = StateTransitionService(session).apply_transition(
            TransitionRequest(
                run_id=run.id, expected_state_version=run.state_version,
                idempotency_key=f"g13-stale-{record.id}",
                event_type=WorkflowEventType.G13_STALE, actor="g13-approval-service",
                reason=reason, occurred_at=self._now(),
                payload={"package_checksum": record.package_checksum},
            )
        )
        record.status = "stale"
        record.stale_reason = reason
        record.state_version = transition.next_state_version
        record.event_sequence = transition.event_sequence
        record.updated_at = self._now()
        session.flush()

    def _find_event(self, session, run_id: str, key: str):
        from app.repositories.models import WorkflowEventModel
        return session.scalar(
            select(WorkflowEventModel).where(
                WorkflowEventModel.run_id == run_id,
                WorkflowEventModel.idempotency_key == key,
            )
        )

    def _dto(self, record: FinalAssuranceRecordModel, *, replay: bool = False):
        from app.api.final_assurance_contracts import FinalAssuranceResponse
        package = record.package or {}
        summary = package.get("summary")
        return FinalAssuranceResponse(
            run_id=record.run_id,
            gate_id=record.gate_id,
            gate_version=record.gate_version,
            status=record.status,
            decision=record.decision,
            summary=summary,
            state_version=record.state_version,
            event_sequence=record.event_sequence,
            idempotent_replay=replay,
            stale_reason=record.stale_reason,
            comment=record.comment,
        )
