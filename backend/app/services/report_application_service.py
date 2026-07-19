"""Durable application service for the S4-F14 G15 report boundary."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactRefDto, ArtifactType, WorkflowEventType
from app.domain.report import (
    FinalReportRecord,
    G15ApprovalPackage,
    G15ApprovalPackageBuilder,
    G15ApprovalResult,
    G15ApprovalService,
    G15Decision,
)
from app.repositories.report_models import ReportRecordModel
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel, RunAssuranceStatusModel
from app.repositories.session import session_scope
from app.state.transition_service import StateTransitionService, TransitionRequest


class ReportApplicationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ReportApplicationService:
    GATE_ID = "G15"
    GATE_VERSION = "g15-v1"

    def __init__(
        self,
        *,
        session_scope_factory=session_scope,
        now_provider=None,
    ) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))

    def get(self, run_id: str, gate_id: str):
        """Retrieve the most recent report record for a run and gate."""
        if gate_id != self.GATE_ID:
            return None
        with self._scope() as session:
            record = session.scalar(
                select(ReportRecordModel)
                .where(ReportRecordModel.run_id == run_id)
                .order_by(ReportRecordModel.created_at.desc())
            )
            if record is not None and record.status != "stale" and not self._revalidate_record(session, record):
                run = session.get(MigrationRunModel, run_id)
                if run is not None:
                    self._mark_stale(session, run, record, "G15 evidence or report checksum is stale.")
            return self._dto(record) if record else None

    def initialize(self, run_id: str, request) -> object:
        """Generate the G15 report evidence package."""
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise ReportApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            existing = session.scalar(
                select(ReportRecordModel)
                .where(ReportRecordModel.run_id == run_id)
                .order_by(ReportRecordModel.created_at.desc())
            )
            if existing is not None:
                return self._dto(existing, replay=True)
            if run.state_version != request.expected_state_version:
                raise ReportApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)
            record = self._create_report(session, run, request.actor, request.idempotency_key, request.generate_narrative, now)
            return self._dto(record)

    def decide(self, run_id: str, request) -> object:
        """Record a G15 decision on a report package."""
        if request.gate_id != self.GATE_ID:
            raise ReportApplicationError("GATE_NOT_FOUND", "Only G15 is supported by this endpoint.", status_code=404)
        now = self._now()
        with self._scope() as session:
            existing_event = self._find_event(session, run_id, request.idempotency_key)
            if existing_event:
                record = session.scalar(
                    select(ReportRecordModel)
                    .where(ReportRecordModel.run_id == run_id)
                    .order_by(ReportRecordModel.created_at.desc())
                )
                if record is None or not self._revalidate_record(session, record):
                    if record is not None:
                        run = session.get(MigrationRunModel, run_id)
                        if run is not None:
                            self._mark_stale(session, run, record, "G15 evidence or report checksum is stale.")
                            session.commit()
                    raise ReportApplicationError("STALE_EVIDENCE", "The G15 evidence or package checksum is stale.", status_code=409)
                return self._dto(record, replay=True)
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise ReportApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)
            if run.state_version != request.expected_state_version:
                raise ReportApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)
            record = session.scalar(
                select(ReportRecordModel)
                .where(ReportRecordModel.run_id == run_id)
                .order_by(ReportRecordModel.created_at.desc())
            )
            if record is None:
                raise ReportApplicationError(
                    "REPORT_NOT_FOUND",
                    "A report must be generated before a decision can be recorded.",
                    status_code=409,
                )
            if not self._revalidate_record(session, record):
                self._mark_stale(session, run, record, "G15 evidence or report checksum is stale.")
                return self._dto(record)
            package = G15ApprovalPackage.model_validate(record.package)
            result: G15ApprovalResult = G15ApprovalService().decide(package, request.decision, comment=request.comment)
            event_type = (
                WorkflowEventType.G15_APPROVED
                if result.decision in {G15Decision.APPROVED, G15Decision.APPROVED_WITH_COMMENT}
                else WorkflowEventType.G15_REJECTED
            )
            if result.stale:
                event_type = WorkflowEventType.G15_STALE
            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id, expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key, event_type=event_type,
                    actor=request.actor, reason=result.reason or "G15 decision recorded", occurred_at=now,
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

    def _create_report(
        self, session, run: MigrationRunModel, actor: str, idempotency_key: str, generate_narrative: bool, now: datetime,
    ) -> ReportRecordModel:
        """Generate the G15 deterministic report and evidence package."""
        store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
        artifact_refs: list[ArtifactRefDto] = []

        def write_evidence(name: str, payload: dict) -> None:
            stored = store.write_text_artifact(
                run.id, f"final_report/{uuid4().hex[:8]}/{name}",
                json.dumps(payload, sort_keys=True, indent=2),
                ArtifactType.REPORT, created_by="report-application-service", created_at=now,
            )
            artifact_refs.append(stored.ref)
            session.add(ArtifactMetadataModel(
                id=f"metadata-{stored.ref.artifact_id}", run_id=run.id,
                stage_id=None, artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path, checksum=stored.ref.checksum,
                created_at=now,
            ))

        # Build deterministic report content from assurance status, run metadata, and artifacts
        assurance_status = session.get(RunAssuranceStatusModel, run.id)

        # Collect all run artifacts for evidence reference
        artifact_rows = list(
            session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run.id))
        )
        run_artifact_refs: list[ArtifactRefDto] = []
        for row in artifact_rows:
            artifact_id = row.id.removeprefix("metadata-")
            run_artifact_refs.append(ArtifactRefDto(
                artifact_id=artifact_id, run_id=run.id, stage_id=row.stage_id,
                artifact_type=ArtifactType(row.artifact_type), relative_path=row.relative_path,
                created_at=row.created_at, checksum=row.checksum,
            ))

        report_content = {
            "run_id": run.id,
            "run_status": run.status,
            "run_phase": run.run_phase,
            "assurance": {
                "technical_upgrade_status": assurance_status.technical_upgrade_status,
                "functional_parity_status": assurance_status.functional_parity_status,
                "security_assurance_status": assurance_status.security_assurance_status,
                "quality_assurance_status": assurance_status.quality_assurance_status,
                "delivery_readiness": assurance_status.delivery_readiness,
            } if assurance_status else None,
            "actor": actor,
            "generated_at": now.isoformat(),
            "artifacts": [{"artifact_id": r.artifact_id, "checksum": r.checksum} for r in run_artifact_refs],
        }
        report_checksum = "sha256:" + hashlib.sha256(
            json.dumps(report_content, sort_keys=True).encode("utf-8")
        ).hexdigest()

        write_evidence("deterministic_report.json", report_content)
        write_evidence("report_checksum.json", {
            "checksum": report_checksum,
            "narrative_status": "generated" if generate_narrative else "not_requested",
        })

        proof_labels = {
            "assurance_technical": "PROVEN" if (assurance_status and assurance_status.technical_upgrade_status == "passed") else "NOT_PROVEN",
            "assurance_parity": "PROVEN" if (assurance_status and assurance_status.functional_parity_status == "passed") else "NOT_PROVEN",
            "source_integrity": "INFERRED",
        }

        report_record = FinalReportRecord(
            report_id=f"report-{uuid4().hex[:12]}", run_id=run.id,
            deterministic_report_checksum=report_checksum,
            narrative_status="generated" if generate_narrative else "not_requested",
            proof_labels=proof_labels,
            artifact_refs=tuple(artifact_refs),
        )

        package = G15ApprovalPackageBuilder().build(
            run_id=run.id, state_version=run.state_version, actor=actor,
            gate_version=self.GATE_VERSION, report=report_record, artifacts=artifact_refs,
        )

        started_event = StateTransitionService(session).apply_transition(
            TransitionRequest(
                run_id=run.id, expected_state_version=run.state_version,
                idempotency_key=f"{idempotency_key}:started",
                event_type=WorkflowEventType.REPORT_GENERATION_STARTED,
                actor=actor, reason="Report generation started", occurred_at=now,
            )
        )
        completed_event = StateTransitionService(session).apply_transition(
            TransitionRequest(
                run_id=run.id, expected_state_version=started_event.next_state_version,
                idempotency_key=f"{idempotency_key}:completed",
                event_type=WorkflowEventType.REPORT_GENERATION_COMPLETED,
                actor=actor, reason="Report generation completed", occurred_at=now,
                payload={"report_checksum": report_checksum},
            )
        )
        created_event = StateTransitionService(session).apply_transition(
            TransitionRequest(
                run_id=run.id, expected_state_version=completed_event.next_state_version,
                idempotency_key=f"{idempotency_key}:created",
                event_type=WorkflowEventType.G15_CREATED,
                actor=actor, reason="G15 evidence package created", occurred_at=now,
                payload={"report_checksum": report_checksum, "package_checksum": package.package_checksum},
            )
        )

        record = ReportRecordModel(
            id=f"g15-{uuid4().hex[:12]}", run_id=run.id, gate_id=self.GATE_ID,
            gate_version=package.gate_version, idempotency_key=idempotency_key, actor=actor,
            status="pending", package=package.model_dump(mode="json"),
            package_checksum=package.package_checksum, artifact_set_checksum=package.artifact_set_checksum,
            report_checksum=report_checksum, narrative_generated=generate_narrative,
            state_version=created_event.next_state_version, event_sequence=created_event.event_sequence,
            artifact_ids=[r.artifact_id for r in artifact_refs],
            created_at=now, updated_at=now,
        )
        session.add(record)
        session.flush()
        return record

    def _revalidate_record(self, session, record: ReportRecordModel) -> bool:
        """Verify the record's package checksum and report content are still current."""
        try:
            package = G15ApprovalPackage.model_validate(record.package)
            if package.package_checksum != record.package_checksum or package.artifact_set_checksum != record.artifact_set_checksum:
                return False
            run = session.get(MigrationRunModel, record.run_id)
            if run is None or not run.artifact_root:
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
            rebuilt = G15ApprovalPackageBuilder().build(
                run_id=package.run_id, state_version=package.state_version, actor=package.actor,
                gate_version=package.gate_version, report=package.report,
                artifacts=list(package.artifacts),
            )
            return (
                rebuilt.package_checksum == package.package_checksum
                and rebuilt.artifact_set_checksum == package.artifact_set_checksum
            )
        except (OSError, ValueError, AttributeError):
            return False

    def _mark_stale(
        self, session, run: MigrationRunModel, record: ReportRecordModel, reason: str,
    ) -> None:
        if record.status == "stale":
            return
        transition = StateTransitionService(session).apply_transition(
            TransitionRequest(
                run_id=run.id, expected_state_version=run.state_version,
                idempotency_key=f"g15-stale-{record.id}",
                event_type=WorkflowEventType.G15_STALE, actor="report-application-service",
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

    def _dto(self, record: ReportRecordModel, *, replay: bool = False):
        from app.api.report_contracts import ReportResponse
        return ReportResponse(
            run_id=record.run_id,
            gate_id=record.gate_id,
            gate_version=record.gate_version,
            status=record.status,
            decision=record.decision,
            report=record.package,
            state_version=record.state_version,
            event_sequence=record.event_sequence,
            idempotent_replay=replay,
            stale_reason=record.stale_reason,
            comment=record.comment,
        )
