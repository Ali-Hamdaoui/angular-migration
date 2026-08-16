"""Repair lifecycle reliability service (V2 F04-02/03/04/05).

Provides deterministic restart recovery for stranded in-flight repair attempts,
state reconciliation, optimistic-versioning transitions, and sealing guards —
all routed through the ``domain.repair_lifecycle`` state machine.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.domain.repair_lifecycle import (
    IN_FLIGHT_STATUSES,
    evaluate_transition,
    is_sealed,
    restart_recovery_target,
)
from app.repositories.models import RepairAttemptModel
from app.repositories.session import session_scope
from app.services.diagnostics_application_service import DiagnosticsApplicationService
from app.state.event_sequencer import append_workflow_event


class RepairLifecycleError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class RepairLifecycleReliabilityService:
    """Deterministic repair lifecycle authority."""

    def __init__(
        self,
        *,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def recover_in_flight_repairs(self, run_id: str | None = None) -> list[str]:
        """Restart recovery sweep for stranded in-flight repair attempts.

        Any attempt still in a worker-bound in-flight state after a restart is
        transitioned deterministically (via ``restart_recovery_target``) with an
        optimistic CAS on ``state_version``, a lifecycle-recovery event, and a
        diagnostic pack.  Sealed/terminal attempts are never touched.
        """
        now = self._now_provider()
        recovered: list[str] = []
        with self._session_scope() as session:
            query = select(RepairAttemptModel).where(RepairAttemptModel.status.in_(tuple(IN_FLIGHT_STATUSES)))
            if run_id:
                query = query.where(RepairAttemptModel.run_id == run_id)
            for attempt in session.scalars(query).all():
                target = restart_recovery_target(attempt.status)
                if target is None or attempt.status == target:
                    continue
                # The recovery mapping is the deterministic restart authority
                # (a recovery is not a forward workflow transition). Sealing is
                # already enforced by restart_recovery_target.
                expected = attempt.state_version
                updated = session.execute(
                    update(RepairAttemptModel)
                    .where(
                        RepairAttemptModel.id == attempt.id,
                        RepairAttemptModel.status == attempt.status,
                        RepairAttemptModel.state_version == expected,
                    )
                    .values(
                        status=target,
                        state_version=expected + 1,
                        updated_at=now,
                    )
                )
                if updated.rowcount != 1:
                    continue
                append_workflow_event(
                    session,
                    run_id=attempt.run_id,
                    stage_id=attempt.stage_id,
                    event_type="repair_lifecycle_recovered",
                    occurred_at=now,
                    idempotency_key=f"repair-lifecycle-recover:{attempt.id}:{target}",
                    reason=f"restart recovery: {attempt.status} -> {target}",
                    payload={"attempt_id": attempt.id, "from_status": attempt.status, "to_status": target},
                )
                recovered.append(attempt.id)
            session.commit()
        for attempt_id in recovered:
            self._record_recovery_pack(attempt_id)
        return recovered

    def _record_recovery_pack(self, attempt_id: str) -> None:
        try:
            with self._session_scope() as session:
                attempt = session.get(RepairAttemptModel, attempt_id)
                if attempt is None:
                    return
                from app.domain.diagnostics import PlatformFault

                DiagnosticsApplicationService().record_command_failure(
                    run_id=attempt.run_id,
                    execution_id=attempt_id,
                    correlation_id=None,
                    fault=PlatformFault(
                        fault_code="REPAIR_LIFECYCLE_RECOVERED",
                        message=f"repair attempt recovered deterministically after restart to status {attempt.status}",
                        occurred_at=self._now_provider(),
                    ),
                    stage_id=attempt.stage_id,
                    state_version=attempt.state_version,
                )
        except Exception:
            return

    def reconcile_attempt_status(self, attempt: RepairAttemptModel, observed_status: str) -> RepairAttemptModel:
        """Converge observed status to the persisted intended status (F04-03).

        Returns the reloaded attempt; the persisted status is authoritative.
        """
        with self._session_scope() as session:
            current = session.get(RepairAttemptModel, attempt.id)
            if current is None:
                raise RepairLifecycleError("ATTEMPT_NOT_FOUND", f"Repair attempt {attempt.id} not found")
            if current.status != observed_status:
                # Intended (persisted) state wins; a recovery event documents the drift.
                append_workflow_event(
                    session,
                    run_id=current.run_id,
                    stage_id=current.stage_id,
                    event_type="repair_lifecycle_reconciled",
                    occurred_at=self._now_provider(),
                    idempotency_key=f"repair-lifecycle-reconcile:{attempt.id}:{self._now_provider().timestamp():.0f}",
                    reason=f"observed {observed_status} reconciled to persisted {current.status}",
                    payload={"attempt_id": attempt.id, "observed": observed_status, "intended": current.status},
                )
                session.commit()
                session.refresh(current)
            return current

    def assert_mutable(self, attempt_id: str, *, status: str | None = None) -> RepairAttemptModel:
        """Sealing guard: a sealed/terminal lifecycle must not be mutated (F04-04)."""
        with self._session_scope() as session:
            attempt = session.get(RepairAttemptModel, attempt_id)
            if attempt is None:
                raise RepairLifecycleError("ATTEMPT_NOT_FOUND", f"Repair attempt {attempt_id} not found")
            if is_sealed(attempt.status):
                raise RepairLifecycleError(
                    "REPAIR_LIFECYCLE_SEALED",
                    f"Repair lifecycle for attempt {attempt_id} is sealed; no further mutation is allowed",
                    {"attempt_id": attempt_id, "status": attempt.status},
                )
            if status is not None and is_sealed(status):
                raise RepairLifecycleError(
                    "REPAIR_LIFECYCLE_SEALED",
                    f"Refusing to transition sealed lifecycle to {status}",
                    {"attempt_id": attempt_id},
                )
            return attempt

    def transition(self, attempt_id: str, to_status: str, *, expected_state_version: int) -> RepairAttemptModel:
        """Optimistic-versioning transition through the lifecycle state machine (F04-05)."""
        with self._session_scope() as session:
            attempt = session.get(RepairAttemptModel, attempt_id)
            if attempt is None:
                raise RepairLifecycleError("ATTEMPT_NOT_FOUND", f"Repair attempt {attempt_id} not found")
            transition = evaluate_transition(attempt_id, attempt.status, to_status)
            if not transition.allowed:
                raise RepairLifecycleError(
                    "REPAIR_TRANSITION_ILLEGAL",
                    transition.reason or "illegal repair lifecycle transition",
                    {"attempt_id": attempt_id, "from_status": attempt.status, "to_status": to_status},
                )
            if attempt.state_version != expected_state_version:
                raise RepairLifecycleError(
                    "REPAIR_STATE_VERSION_CONFLICT",
                    "repair lifecycle state changed concurrently",
                    {"attempt_id": attempt_id, "expected": expected_state_version, "actual": attempt.state_version},
                )
            attempt.status = to_status
            attempt.state_version += 1
            attempt.updated_at = self._now_provider()
            session.commit()
            session.refresh(attempt)
            return attempt
