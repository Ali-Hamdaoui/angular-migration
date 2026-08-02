"""Separate durable Transformer and command worker process."""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.core.config import get_settings
from app.repositories.session import session_scope
from app.repositories.models import CommandExecutionModel, TransformationContinuationModel
from app.services.command_executor_service import CommandExecutorService
from app.services.transformation_continuation_service import (
    TransformationContinuationService,
    append_continuation_event,
)
from app.orchestration.transformer_graph import TransformerWorkflow
from app.domain.contracts import WorkflowEventType

LOGGER = logging.getLogger(__name__)

TERMINAL_EXECUTION_STATUSES = frozenset(
    {"succeeded", "failed", "timed_out", "cancelled", "interrupted"}
)


class TransformerWorker:
    def __init__(
        self,
        *,
        worker_id: str | None = None,
        command_executor: CommandExecutorService | None = None,
        continuation_service: TransformationContinuationService | None = None,
        workflow: TransformerWorkflow | None = None,
        scope=session_scope,
        poll_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.worker_id = worker_id or f"transformer-{os.getpid()}-{uuid4().hex[:8]}"
        self.command_executor = command_executor or CommandExecutorService()
        self.continuations = continuation_service or TransformationContinuationService()
        self.workflow = workflow or TransformerWorkflow()
        self._scope = scope
        self.poll_seconds = poll_seconds or settings.transformer_worker_poll_seconds

    def run_once(self) -> bool:
        now = datetime.now(UTC)
        with self._scope() as session:
            self.command_executor.reconcile_expired_executions(session, now)
            self.reconcile_stuck_command_waiters(session, now)
            execution_id = self.command_executor.claim_next_execution(
                session,
                self.worker_id,
                now,
                lease_seconds=get_settings().worker_lease_seconds,
            )
        if execution_id is not None:
            self.command_executor.execute_claimed_execution(execution_id, self.worker_id)
            self._wake_command_waiter(execution_id)
            return True
        with self._scope() as session:
            continuation = self.continuations.claim_next(session, self.worker_id, now)
            continuation_id = continuation.id if continuation else None
        if continuation_id is None:
            return False
        self.workflow.invoke(continuation_id, self.worker_id)
        return True

    def reconcile_stuck_command_waiters(self, session, now: datetime | None = None) -> list[str]:
        """Reclaim continuations parked on commands whose terminal evidence committed.

        The worker wakes command waiters only after it personally persists a
        terminal command result. If the worker dies between that commit and the
        wake, the continuation would otherwise stay ``waiting_command`` forever.
        This reconciliation reruns the wake decision from durable state:
        terminal referenced execution -> requeue (RESUMED); referenced execution
        row missing -> deterministic block (BLOCKED).
        """
        checked_at = now or datetime.now(UTC)
        waiters = list(
            session.scalars(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.status == "waiting_command",
                    TransformationContinuationModel.waiting_execution_id.is_not(None),
                )
            )
        )
        reconciled: list[str] = []
        for continuation in waiters:
            execution = session.get(
                CommandExecutionModel, continuation.waiting_execution_id
            )
            if execution is None:
                self._block_lost_command_waiter(session, continuation, checked_at)
                reconciled.append(continuation.id)
            elif execution.status in TERMINAL_EXECUTION_STATUSES:
                self._wake_continuation(
                    session, continuation, execution.id, checked_at, reason="command reached terminal state"
                )
                reconciled.append(continuation.id)
        session.flush()
        return reconciled

    def _wake_command_waiter(self, execution_id: str) -> None:
        with self._scope() as session:
            execution = session.get(CommandExecutionModel, execution_id)
            if execution is None or execution.status not in TERMINAL_EXECUTION_STATUSES:
                return
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == execution.run_id,
                    TransformationContinuationModel.current_stage_id == execution.stage_id,
                    TransformationContinuationModel.status == "waiting_command",
                    TransformationContinuationModel.waiting_execution_id == execution.id,
                )
            )
            if continuation is not None:
                self._wake_continuation(
                    session,
                    continuation,
                    execution.id,
                    datetime.now(UTC),
                    reason="command reached terminal state",
                )

    @staticmethod
    def _wake_continuation(
        session,
        continuation: TransformationContinuationModel,
        execution_id: str,
        now: datetime,
        *,
        reason: str,
    ) -> None:
        previous_wake = continuation.wake_sequence
        continuation.status = "queued"
        continuation.wake_sequence += 1
        continuation.state_version += 1
        continuation.updated_at = now
        session.flush()
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
            key=f"wake:{previous_wake + 1}",
            reason=reason,
            payload={
                "execution_id": execution_id,
                "expected_state_version": continuation.state_version - 1,
            },
            occurred_at=now,
            actor="transformer-worker",
        )

    @staticmethod
    def _block_lost_command_waiter(
        session,
        continuation: TransformationContinuationModel,
        now: datetime,
    ) -> None:
        expected_state_version = continuation.state_version
        continuation.status = "blocked"
        continuation.last_error_code = "COMMAND_LOST_AFTER_RESTART"
        continuation.last_error_message = (
            "The command this continuation waits on is no longer tracked; "
            "worker restart lost the referenced execution."
        )
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = now
        session.flush()
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED,
            key=f"block:{expected_state_version}:COMMAND_LOST_AFTER_RESTART",
            reason="referenced command execution is missing after worker restart",
            payload={
                "last_error_code": "COMMAND_LOST_AFTER_RESTART",
                "expected_state_version": expected_state_version,
            },
            occurred_at=now,
            actor="transformer-worker",
        )

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        stop = stop_event or threading.Event()
        while not stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                LOGGER.exception("Transformer worker iteration failed")
                worked = False
            if not worked:
                stop.wait(self.poll_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    TransformerWorker().run_forever()


if __name__ == "__main__":
    main()
