"""Separate durable Transformer and command worker process."""

from __future__ import annotations

import logging
import os
import threading
import traceback
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, or_, select

from app.core.config import get_settings
from app.repositories.session import session_scope
from app.repositories.models import CommandExecutionModel, TransformationContinuationModel
from app.services.command_executor_service import CommandExecutorService
from app.services.transformation_continuation_service import (
    TransformationContinuationService,
    append_continuation_event,
)
from app.services.factory_runtime_service import FactoryRuntimeService, StaleFactoryRuntimeError
from app.orchestration.transformer_graph import TransformerWorkflow
from app.domain.contracts import WorkflowEventType

LOGGER = logging.getLogger(__name__)

_TERMINAL_COMMAND_STATUSES = frozenset(
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
        self.factory_runtime = FactoryRuntimeService()
        self.worker_id = worker_id or (
            f"transformer-{self.factory_runtime.worker_identity}-{os.getpid()}-{uuid4().hex[:8]}"
        )
        self.command_executor = command_executor or CommandExecutorService()
        self.continuations = continuation_service or TransformationContinuationService()
        self.workflow = workflow or TransformerWorkflow()
        self._scope = scope
        self.poll_seconds = poll_seconds or settings.transformer_worker_poll_seconds

    def run_once(self) -> bool:
        now = datetime.now(UTC)
        with self._scope() as session:
            self.factory_runtime.assert_active(session)
            self.command_executor.reconcile_expired_executions(session, now)
            self.reconcile_stuck_command_waiters(session, now)
            self._wake_terminal_command_waiters(session, now)
            execution_id = self.command_executor.claim_next_execution(
                session,
                self.worker_id,
                now,
                lease_seconds=get_settings().worker_lease_seconds,
            )
        if execution_id is not None:
            with self._scope() as session:
                self.factory_runtime.assert_active(session)
            self.command_executor.execute_claimed_execution(execution_id, self.worker_id)
            self._wake_command_waiter(execution_id)
            return True
        with self._scope() as session:
            self.factory_runtime.assert_active(session)
            continuation = self.continuations.claim_next(session, self.worker_id, now)
            if continuation is None:
                continuation_id = None
                claim_snapshot = None
            else:
                continuation_id = continuation.id
                claim_snapshot = {
                    "continuation_id": continuation.id,
                    "run_id": continuation.run_id,
                    "stage_id": continuation.current_stage_id,
                    "current_node": continuation.current_node,
                    "state_version": continuation.state_version,
                    "worker_id": continuation.worker_id,
                    "claim_count": continuation.claim_count,
                    "claimed_at": now.isoformat(),
                }
        if continuation_id is None:
            return False
        try:
            with self._scope() as session:
                self.factory_runtime.assert_active(session)
            self.workflow.invoke(continuation_id, self.worker_id)
        except Exception as exc:
            LOGGER.exception(
                "Transformer workflow invocation failed",
                extra={"continuation_id": continuation_id, "worker_id": self.worker_id},
            )
            try:
                with self._scope() as session:
                    self.continuations.record_unhandled_workflow_fault(
                        session,
                        continuation_id=continuation_id,
                        claimed_worker_id=self.worker_id,
                        claim_snapshot=claim_snapshot or {},
                        exception_type=type(exc).__name__,
                        sanitized_message=" ".join(str(exc).split())[:2000],
                        traceback_text=traceback.format_exc(),
                    )
            except StaleFactoryRuntimeError:
                raise
            except Exception:
                LOGGER.exception(
                    "Failed to persist Transformer workflow fault",
                    extra={"continuation_id": continuation_id, "worker_id": self.worker_id},
                )
        return True

    def reconcile_stuck_command_waiters(self, session, now: datetime | None = None) -> list[str]:
        """Reclaim continuations parked on commands whose terminal evidence committed.

        The worker wakes command waiters only after it personally persists a
        terminal command result. If the worker dies between that commit and the
        wake, the continuation would otherwise stay ``waiting_command`` forever.
        This reconciliation reruns the wake decision from durable state:
        terminal referenced execution -> requeue (RESUMED); referenced execution
        row missing -> deterministic block (BLOCKED).

        Waiters whose ``waiting_execution_id`` is NULL (pre-linkage rows) are
        resolved against the stage's command history: exactly one terminal
        execution -> requeue; zero command rows -> deterministic block; several
        terminal executions -> deterministic block (ambiguous); only in-flight
        commands -> still waiting, not stuck.
        """
        checked_at = now or datetime.now(UTC)
        waiters = list(
            session.scalars(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.status == "waiting_command"
                )
            )
        )
        reconciled: list[str] = []
        for continuation in waiters:
            if continuation.waiting_execution_id is not None:
                execution = session.get(
                    CommandExecutionModel, continuation.waiting_execution_id
                )
                if execution is None:
                    self._block_command_waiter(
                        session,
                        continuation,
                        checked_at,
                        code="COMMAND_LOST_AFTER_RESTART",
                        message=(
                            "The command this continuation waits on is no longer "
                            "tracked; worker restart lost the referenced execution."
                        ),
                    )
                    reconciled.append(continuation.id)
                elif (
                    execution.status in _TERMINAL_COMMAND_STATUSES
                    and execution.run_id == continuation.run_id
                    and execution.stage_id == continuation.current_stage_id
                ):
                    self._wake_continuation(
                        session, continuation, execution.id, checked_at, reason="command reached terminal state"
                    )
                    reconciled.append(continuation.id)
                continue
            self._reconcile_null_linkage_waiter(
                session, continuation, checked_at, reconciled
            )
        session.flush()
        return reconciled

    def _reconcile_null_linkage_waiter(
        self,
        session,
        continuation: TransformationContinuationModel,
        now: datetime,
        reconciled: list[str],
    ) -> None:
        """Resolve a NULL-linkage waiter from the stage's command executions.

        The codebase enforces one active workflow command per run (partial
        unique index), so a single terminal candidate is unambiguous. Multiple
        terminal candidates are never guessed between; the waiter is blocked
        instead.
        """
        terminal = list(
            session.scalars(
                select(CommandExecutionModel)
                .where(
                    CommandExecutionModel.run_id == continuation.run_id,
                    CommandExecutionModel.stage_id == continuation.current_stage_id,
                    CommandExecutionModel.status.in_(_TERMINAL_COMMAND_STATUSES),
                )
                .order_by(
                    CommandExecutionModel.finished_at.desc(),
                    CommandExecutionModel.id.desc(),
                )
            )
        )
        if len(terminal) == 1:
            self._wake_continuation(
                session,
                continuation,
                terminal[0].id,
                now,
                reason="command reached terminal state",
            )
            reconciled.append(continuation.id)
            return
        command_count = session.scalar(
            select(func.count())
            .select_from(CommandExecutionModel)
            .where(
                CommandExecutionModel.run_id == continuation.run_id,
                CommandExecutionModel.stage_id == continuation.current_stage_id,
            )
        )
        if len(terminal) > 1:
            self._block_command_waiter(
                session,
                continuation,
                now,
                code="COMMAND_WAIT_AMBIGUOUS",
                message=(
                    "Multiple terminal command executions exist for this stage; "
                    "the waited-on command cannot be resolved unambiguously."
                ),
            )
            reconciled.append(continuation.id)
        elif command_count == 0:
            self._block_command_waiter(
                session,
                continuation,
                now,
                code="COMMAND_LOST_AFTER_RESTART",
                message=(
                    "The command this continuation waits on is no longer tracked; "
                    "worker restart lost the referenced execution."
                ),
            )
            reconciled.append(continuation.id)

    def _wake_terminal_command_waiters(self, session, now: datetime) -> None:
        """Deterministically release waiters whose latest command reached a terminal state.

        Reconcile terminalises an expired mutating claim to ``interrupted``
        without ever executing it, and any terminal command whose wake was
        lost (worker crash between execution and wake, cancellation of a
        queued command) otherwise parks the continuation forever. The
        single-active-command-per-run invariant makes the latest command for
        (run_id, stage_id) the unambiguous wait target.
        """
        waiters = list(
            session.scalars(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.status == "waiting_command"
                )
            )
        )
        for continuation in waiters:
            latest = session.scalar(
                select(CommandExecutionModel)
                .where(
                    CommandExecutionModel.run_id == continuation.run_id,
                    CommandExecutionModel.stage_id == continuation.current_stage_id,
                )
                .order_by(
                    CommandExecutionModel.requested_at.desc(),
                    CommandExecutionModel.id.desc(),
                )
                .limit(1)
            )
            if (
                latest is not None
                and latest.status in _TERMINAL_COMMAND_STATUSES
                and (
                    continuation.waiting_execution_id is None
                    or continuation.waiting_execution_id == latest.id
                )
            ):
                self._wake_continuation(
                    session,
                    continuation,
                    latest.id,
                    now,
                    reason="command reached terminal state",
                )

    def _wake_command_waiter(self, execution_id: str) -> None:
        with self._scope() as session:
            execution = session.get(CommandExecutionModel, execution_id)
            if execution is None or execution.status not in _TERMINAL_COMMAND_STATUSES:
                return
            continuation = session.scalar(
                select(TransformationContinuationModel).where(
                    TransformationContinuationModel.run_id == execution.run_id,
                    TransformationContinuationModel.current_stage_id == execution.stage_id,
                    TransformationContinuationModel.status == "waiting_command",
                    or_(
                        TransformationContinuationModel.waiting_execution_id.is_(None),
                        TransformationContinuationModel.waiting_execution_id == execution.id,
                    ),
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
        if continuation.waiting_execution_id == execution_id:
            continuation.waiting_execution_id = None
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
    def _block_command_waiter(
        session,
        continuation: TransformationContinuationModel,
        now: datetime,
        *,
        code: str,
        message: str,
    ) -> None:
        expected_state_version = continuation.state_version
        continuation.status = "blocked"
        continuation.last_error_code = code
        continuation.last_error_message = message
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = now
        session.flush()
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED,
            key=f"block:{expected_state_version}:{code}",
            reason=message,
            payload={
                "last_error_code": code,
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
            except StaleFactoryRuntimeError:
                LOGGER.error("STALE_FACTORY_RUNTIME: worker is fenced and will stop")
                return
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
