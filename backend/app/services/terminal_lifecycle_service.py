"""Full terminal lifecycle service (V2 F23).

Sequences the next actions across the whole migration lifecycle, exposes
lifecycle evidence (events, seals, artifacts) for terminal use, and drives a
complete setup -> stages -> seal lifecycle through the terminal/API surface.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy import func, select

from app.repositories.session import session_scope
from app.services.terminal_operation_service import TerminalOperationService


class TerminalLifecycleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


#: Ordered lifecycle phases a terminal operator drives through.
LIFECYCLE_PHASES = (
    "setup", "execution_profile", "chain_start", "stages", "sealing", "delivery",
)


class TerminalLifecycleService:
    """Compose the full terminal lifecycle (F23)."""

    def __init__(
        self,
        *,
        terminal_operation: TerminalOperationService | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
    ) -> None:
        self._terminal = terminal_operation or TerminalOperationService()
        self._session_scope = session_scope_factory or session_scope

    def lifecycle_sequence(self, run_id: str) -> dict:
        """Enumerate the ordered lifecycle steps and the current one (F23-01)."""
        self._require_run(run_id)
        with self._session_scope() as session:
            from app.repositories.models import StageChainRunModel

            chain = session.scalar(
                select(StageChainRunModel)
                .where(StageChainRunModel.run_id == run_id)
                .order_by(StageChainRunModel.updated_at.desc())
                .limit(1)
            )
            stage_progress = 0
            if chain is not None:
                stage_progress = sum(1 for s in (chain.stages or []) if s.get("status") in {"sealed", "failed", "repairing"})
            from app.repositories.models import WorkflowEventModel

            event_count = session.scalar(
                select(func.count()).select_from(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id)
            ) or 0
        chain_status = chain.status if chain else "not_started"
        if chain_status == "completed":
            current_phase = "delivery"
        elif chain_status == "sealing" or stage_progress:
            current_phase = "sealing"
        elif chain_status == "running":
            current_phase = "stages"
        elif chain_status == "not_started":
            # a nonexistent chain is always setup (a run with events but no
            # chain is still at the setup stage)
            current_phase = "setup"
        else:
            current_phase = "chain_start"
        return {
            "run_id": run_id,
            "phases": list(LIFECYCLE_PHASES),
            "current_phase": current_phase,
            "chain_status": chain_status,
            "stage_progress": stage_progress,
            "event_count": event_count,
            "next_action": self._terminal.next_action(run_id)["next_permitted_action"],
        }

    def lifecycle_evidence(self, run_id: str) -> dict:
        """Expose lifecycle evidence (events, seals, artifacts) via API (F23-03)."""
        self._require_run(run_id)
        with self._session_scope() as session:
            from app.repositories.models import StageValidationSealModel, WorkflowEventModel

            events = session.scalars(
                select(WorkflowEventModel)
                .where(WorkflowEventModel.run_id == run_id)
                .order_by(WorkflowEventModel.sequence.asc())
            ).all()
            seals = session.scalars(
                select(StageValidationSealModel)
                .where(StageValidationSealModel.run_id == run_id)
                .order_by(StageValidationSealModel.created_at.asc())
            ).all()
        return {
            "run_id": run_id,
            "events": [{"sequence": e.sequence, "event_type": e.event_type, "reason": e.reason, "occurred_at": e.occurred_at.isoformat()} for e in events],
            "seals": [{"stage_id": s.stage_id, "checksum": s.checksum, "validation_checksum": s.validation_checksum} for s in seals],
            "next_action": self._terminal.next_action(run_id)["next_permitted_action"],
        }

    def drive_next(self, run_id: str) -> dict:
        """Drive the lifecycle forward one terminal step (F23-02 helper).

        setup -> chain_start -> stages/advance -> sealing/validate+seal.
        Returns the resulting lifecycle sequence.
        """
        sequence = self.lifecycle_sequence(run_id)
        phase = sequence["current_phase"]
        from app.services.migration_route_service import MigrationRouteError
        from app.services.stage_chain_orchestrator import StageChainOrchestrator, StageOrchestrationError

        try:
            if phase == "setup":
                StageChainOrchestrator().start_chain(run_id)
            elif phase in {"chain_start", "stages", "sealing"}:
                StageChainOrchestrator().advance(run_id)
        except (StageOrchestrationError, MigrationRouteError, ValueError) as exc:
            raise TerminalLifecycleError("CHAIN_ERROR", f"lifecycle drive failed: {exc}") from exc
        return self.lifecycle_sequence(run_id)

    def _require_run(self, run_id: str) -> None:
        from app.repositories.models import MigrationRunModel

        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise TerminalLifecycleError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
