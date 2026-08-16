"""Terminal operation facade: next-action, diagnostics, approval, resume (V2 F06)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from app.repositories.session import session_scope
from app.services.failure_intelligence_service import FailureIntelligenceService
from app.services.workflow_projection_service import WorkflowProjectionService


class TerminalOperationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TerminalOperationService:
    """Compose the terminal/API-only operation surface (F06)."""

    def __init__(
        self,
        *,
        projection_service: WorkflowProjectionService | None = None,
        intelligence_service: FailureIntelligenceService | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
    ) -> None:
        self._projection = projection_service or WorkflowProjectionService()
        self._intelligence = intelligence_service or FailureIntelligenceService()
        self._session_scope = session_scope_factory or session_scope

    def _require_run(self, run_id: str) -> None:
        from app.repositories.models import MigrationRunModel

        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise TerminalOperationError("RUN_NOT_FOUND", f"Migration run {run_id} not found")

    def next_action(self, run_id: str) -> dict:
        """Return the next permitted action for a run (F06-01)."""
        self._require_run(run_id)
        with self._session_scope() as session:
            projection = self._projection.build(session, run_id)
        return {
            "run_id": run_id,
            "status": projection.status.value if hasattr(projection.status, "value") else projection.status,
            "next_permitted_action": projection.next_permitted_action.value if hasattr(projection.next_permitted_action, "value") else projection.next_permitted_action,
            "remaining_work": list(projection.remaining_work),
            "gate": {"availability": projection.gate.availability.value if hasattr(projection.gate.availability, "value") else projection.gate.availability,
                     "value": projection.gate.value.value if hasattr(projection.gate.value, "value") else projection.gate.value},
        }

    def terminal_diagnostics(self, run_id: str) -> dict:
        """Compose structured diagnostics for terminal use (F06-02)."""
        self._require_run(run_id)
        with self._session_scope() as session:
            from sqlalchemy import select

            from app.repositories.models import FailureDiagnosticPackModel

            packs = session.scalars(
                select(FailureDiagnosticPackModel)
                .where(FailureDiagnosticPackModel.run_id == run_id)
                .order_by(FailureDiagnosticPackModel.created_at.asc())
            ).all()
            pack_ids = [p.id for p in packs]
        intelligence = self._intelligence.intelligence_for_run(run_id)
        return {
            "run_id": run_id,
            "diagnostic_packs": pack_ids,
            "failure_groups": [g.model_dump(mode="json") for g in intelligence["groups"]],
            "root_causes": {k: v.model_dump(mode="json") for k, v in intelligence["root_causes"].items()},
        }

    def terminal_resume(self, run_id: str) -> dict:
        """Resume the run through the terminal (F06-04)."""
        self._require_run(run_id)
        from app.services.stage_chain_orchestrator import StageChainOrchestrator, StageOrchestrationError

        try:
            chain = StageChainOrchestrator().resume(run_id)
        except StageOrchestrationError:
            chain = None
        return {
            "run_id": run_id,
            "chain_status": chain.status if chain else "not_started",
            "next": self.next_action(run_id),
        }
