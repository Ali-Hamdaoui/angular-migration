"""Repository for failure evidence persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.domain.failure import FailureDiagnostic, FailureEvidence
from app.repositories.models.workflow import FailureDiagnosticModel, FailureModel


class FailureRepository:
    """Repository for FailureModel and FailureDiagnosticModel."""

    def save_failure(
        self,
        session: Session,
        evidence: FailureEvidence,
        idempotency_key: str,
        state_version: int,
    ) -> FailureModel:
        """Persist a new failure evidence record and return the ORM model."""
        now = datetime.now(UTC)
        model = FailureModel(
            id=evidence.failure_id,
            run_id=evidence.run_id,
            stage_id=evidence.stage_id,
            execution_id=evidence.execution_id,
            failure_fingerprint=evidence.failure_fingerprint,
            origin=evidence.origin.value if hasattr(evidence.origin, "value") else evidence.origin,
            workspace_fingerprint=evidence.workspace_fingerprint,
            status=evidence.status.value if hasattr(evidence.status, "value") else evidence.status,
            state_version=state_version,
            idempotency_key=idempotency_key,
            failure_json=evidence.model_dump_json(indent=2),
            created_at=now,
        )
        session.add(model)
        session.flush()
        return model

    def save_diagnostics(
        self,
        session: Session,
        failure_id: str,
        diagnostics: list[FailureDiagnostic],
    ) -> list[FailureDiagnosticModel]:
        """Persist diagnostic entries for a failure."""
        models: list[FailureDiagnosticModel] = []
        for idx, d in enumerate(diagnostics):
            model = FailureDiagnosticModel(
                id=f"diag-{failure_id}-{idx}",
                failure_id=failure_id,
                parser_type=d.parser_type.value if hasattr(d.parser_type, "value") else str(d.parser_type),
                parser_confidence=d.parser_confidence,
                message=d.message,
                code=d.code,
                file_path=d.file_path,
                line_number=d.line_number,
                column=d.column,
                severity=d.severity,
            )
            session.add(model)
            models.append(model)
        session.flush()
        return models

    def get_failure(self, session: Session, run_id: str, failure_id: str) -> FailureModel | None:
        """Retrieve a failure by its ID, scoped to run."""
        return session.query(FailureModel).filter(
            FailureModel.id == failure_id,
            FailureModel.run_id == run_id,
        ).first()

    def get_failures_by_run(self, session: Session, run_id: str) -> list[FailureModel]:
        """Retrieve all failures for a run."""
        return session.query(FailureModel).filter(
            FailureModel.run_id == run_id,
        ).order_by(FailureModel.created_at.desc()).all()

    def get_diagnostics(self, session: Session, failure_id: str) -> list[FailureDiagnosticModel]:
        """Retrieve all diagnostics for a failure."""
        return session.query(FailureDiagnosticModel).filter(
            FailureDiagnosticModel.failure_id == failure_id,
        ).all()
