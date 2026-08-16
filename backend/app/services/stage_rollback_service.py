"""Stage rollback and resume service (V2 F25)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.stage_rollback import StageRollbackDecision
from app.repositories.models import MigrationRunModel, StageRollbackModel, StageValidationSealModel
from app.repositories.session import session_scope


class StageRollbackError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StageRollbackService:
    """Deterministic rollback to the last sealed stage and resume (F25)."""

    def __init__(
        self,
        *,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def find_rollback_point(self, run_id: str) -> int | None:
        """The highest sealed stage order for a run (F25-03, deterministic)."""
        with self._session_scope() as session:
            rows = session.scalars(
                select(StageValidationSealModel).where(StageValidationSealModel.run_id == run_id)
            ).all()
        if not rows:
            return None
        return max(row.stage_order for row in rows)

    def rollback(self, run_id: str) -> StageRollbackDecision:
        """Roll a failed chain back to the last sealed stage (F25-01).

        Stages after the sealed rollback point are reset to pending; the sealed
        evidence itself is preserved immutably (F25-04).
        """
        self._require_run(run_id)
        rollback_point = self.find_rollback_point(run_id)
        if rollback_point is None:
            decision = StageRollbackDecision(
                run_id=run_id, rollback_point_stage_order=None, sealed_stage_count=0,
                evidence_preserved=True, status="no_rollback_point",
            ).bind_checksum()
            self._persist(run_id, decision)
            return decision
        from app.services.stage_chain_orchestrator import StageChainOrchestrator, StageOrchestrationError

        try:
            chain = StageChainOrchestrator().current_state(run_id)
        except StageOrchestrationError as exc:
            raise StageRollbackError("CHAIN_NOT_STARTED", f"no chain to roll back for run {run_id}") from exc
        updated_stages = tuple(
            s.model_copy(update={"status": "pending", "gate_passed": False, "failure_code": None})
            if s.stage_order > rollback_point
            else s
            for s in chain.stages
        )
        resumed = chain.model_copy(update={"status": "running", "stages": updated_stages}).bind_checksum()
        StageChainOrchestrator()._persist_state(run_id, resumed)
        sealed_count = len(self._list_seals(run_id))
        decision = StageRollbackDecision(
            run_id=run_id, rollback_point_stage_order=rollback_point,
            sealed_stage_count=sealed_count, evidence_preserved=True, status="rolled_back",
        ).bind_checksum()
        self._persist(run_id, decision)
        return decision

    def resume_from_sealed(self, run_id: str) -> dict:
        """Resume deterministically from the last sealed stage (F25-02).

        The rollback point is the highest sealed stage; the next runnable stage
        is its successor (or sealing completion when the chain is fully sealed).
        """
        rollback_point = self.find_rollback_point(run_id)
        if rollback_point is None:
            raise StageRollbackError("NO_ROLLBACK_POINT", f"run {run_id} has no sealed stage to resume from")
        from app.services.stage_chain_orchestrator import StageChainOrchestrator, StageOrchestrationError

        try:
            chain = StageChainOrchestrator().current_state(run_id)
        except StageOrchestrationError as exc:
            raise StageRollbackError("CHAIN_NOT_STARTED", f"no chain to resume for run {run_id}") from exc
        next_stage = next(
            (s for s in chain.stages if s.stage_order > rollback_point and s.status == "pending"), None
        )
        return {
            "run_id": run_id,
            "rollback_point_stage_order": rollback_point,
            "next_stage_order": next_stage.stage_order if next_stage else None,
            "resume_action": "advance_next_stage" if next_stage else "sealing_complete",
        }

    def _persist(self, run_id: str, decision: StageRollbackDecision) -> None:
        with self._session_scope() as session:
            existing = session.scalar(
                select(StageRollbackModel).where(
                    StageRollbackModel.run_id == run_id,
                    StageRollbackModel.checksum == decision.checksum,
                )
            )
            if existing is not None:
                return
            session.add(
                StageRollbackModel(
                    id="rb-" + hashlib.sha256(f"{run_id}:{decision.checksum}".encode()).hexdigest()[:24],
                    run_id=run_id,
                    rollback_point_stage_order=decision.rollback_point_stage_order,
                    sealed_stage_count=decision.sealed_stage_count,
                    evidence_preserved=decision.evidence_preserved,
                    status=decision.status,
                    checksum=decision.checksum,
                    created_at=self._now_provider(),
                )
            )
            session.commit()

    def list_rollbacks(self, run_id: str) -> list[StageRollbackModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(StageRollbackModel)
                    .where(StageRollbackModel.run_id == run_id)
                    .order_by(StageRollbackModel.created_at.asc())
                ).all()
            )

    def _list_seals(self, run_id: str) -> list[StageValidationSealModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(StageValidationSealModel).where(StageValidationSealModel.run_id == run_id)
                ).all()
            )

    def _require_run(self, run_id: str) -> None:
        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise StageRollbackError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
