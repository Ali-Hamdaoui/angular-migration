"""Governed repair proposal-cycle service (V2 F21)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.proposal_cycle import ProposalCycle
from app.repositories.models import MigrationRunModel, ProposalCycleModel, RepairAttemptModel
from app.repositories.session import session_scope


class ProposalCycleError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ProposalCycleService:
    """Record and govern immutable proposal cycles (F21)."""

    def __init__(
        self,
        *,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def create_cycle(self, run_id: str, attempt_id: str, proposal_checksum: str, *, parent_cycle_id: str | None = None) -> ProposalCycle:
        """Record a new proposal cycle for a repair attempt (F21-01)."""
        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise ProposalCycleError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            if session.get(RepairAttemptModel, attempt_id) is None:
                raise ProposalCycleError("ATTEMPT_NOT_FOUND", f"Repair attempt {attempt_id} not found")
            existing = session.scalar(
                select(ProposalCycleModel).where(
                    ProposalCycleModel.attempt_id == attempt_id,
                    ProposalCycleModel.proposal_checksum == proposal_checksum,
                )
            )
            if existing is not None:
                return self._from_model(existing)
            count = session.execute(
                select(ProposalCycleModel).where(ProposalCycleModel.attempt_id == attempt_id)
            ).scalars().all()
            cycle_number = len(count) + 1
            cycle = ProposalCycle(
                cycle_id=_cycle_id(attempt_id, proposal_checksum),
                run_id=run_id,
                attempt_id=attempt_id,
                cycle_number=cycle_number,
                proposal_checksum=proposal_checksum,
                parent_cycle_id=parent_cycle_id,
            ).bind_checksum()
            session.add(
                ProposalCycleModel(
                    id=cycle.cycle_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    cycle_number=cycle_number,
                    proposal_checksum=proposal_checksum,
                    decision=cycle.decision,
                    hints=list(cycle.hints),
                    parent_cycle_id=parent_cycle_id,
                    checksum=cycle.checksum,
                    created_at=self._now_provider(),
                )
            )
            session.commit()
            return cycle

    def decide(self, cycle_id: str, decision: str, *, reviewer: str | None = None, hints: list[str] | None = None) -> ProposalCycle:
        """Governed reviewer action: accept / reject / request-changes (F21-03).

        request_changes creates a child cycle (new-cycle lineage) via the
        request-change path.
        """
        if decision not in {"accepted", "rejected", "request_changes"}:
            raise ProposalCycleError("INVALID_DECISION", f"decision {decision!r} is not a governed reviewer action")
        with self._session_scope() as session:
            row = session.get(ProposalCycleModel, cycle_id)
            if row is None:
                raise ProposalCycleError("CYCLE_NOT_FOUND", f"proposal cycle {cycle_id} not found")
            if row.decision != "pending":
                raise ProposalCycleError("CYCLE_ALREADY_DECIDED", f"proposal cycle {cycle_id} was already decided ({row.decision})")
            row.decision = decision
            row.reviewer = reviewer
            row.hints = list(hints or [])
            row.updated_at = self._now_provider()
            session.commit()
            session.refresh(row)
        cycle = self._from_model(row)
        if decision == "request_changes":
            # request-change creates a new cycle carrying the reviewer hints;
            # the parent cycle returns as decided.
            child = self.create_cycle(row.run_id, row.attempt_id, _child_proposal_key(row.proposal_checksum), parent_cycle_id=row.id)
            self.decide_child(child.cycle_id, hints)
        return cycle

    def decide_child(self, child_cycle_id: str, hints: list[str] | None) -> ProposalCycle:
        """A request-change child cycle is created pending with the reviewer hints."""
        with self._session_scope() as session:
            row = session.get(ProposalCycleModel, child_cycle_id)
            if row is None:
                raise ProposalCycleError("CYCLE_NOT_FOUND", f"proposal cycle {child_cycle_id} not found")
            if row.decision != "pending":
                raise ProposalCycleError("CYCLE_ALREADY_DECIDED", f"proposal cycle {child_cycle_id} was already decided")
            row.hints = list(hints or [])
            row.updated_at = self._now_provider()
            session.commit()
            session.refresh(row)
            return self._from_model(row)

    def list_lineage(self, attempt_id: str) -> list[ProposalCycle]:
        """Return the full proposal-cycle lineage for an attempt (F21-05)."""
        with self._session_scope() as session:
            rows = session.scalars(
                select(ProposalCycleModel)
                .where(ProposalCycleModel.attempt_id == attempt_id)
                .order_by(ProposalCycleModel.cycle_number.asc())
            ).all()
            return [self._from_model(row) for row in rows]

    @staticmethod
    def _from_model(row: ProposalCycleModel) -> ProposalCycle:
        cycle = ProposalCycle(
            cycle_id=row.id,
            run_id=row.run_id,
            attempt_id=row.attempt_id,
            cycle_number=row.cycle_number,
            proposal_checksum=row.proposal_checksum,
            decision=row.decision,
            reviewer=row.reviewer,
            hints=tuple(row.hints or []),
            parent_cycle_id=row.parent_cycle_id,
        )
        return cycle.bind_checksum()


def _cycle_id(attempt_id: str, proposal_checksum: str) -> str:
    return "pc-" + hashlib.sha256(f"{attempt_id}:{proposal_checksum}".encode()).hexdigest()[:24]


def _child_proposal_key(parent_checksum: str) -> str:
    return hashlib.sha256(f"{parent_checksum}:revision".encode()).hexdigest()
