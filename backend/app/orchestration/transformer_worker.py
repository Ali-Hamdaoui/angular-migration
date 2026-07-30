"""Separate durable Transformer and command worker process."""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from uuid import uuid4

from app.core.config import get_settings
from app.repositories.session import session_scope
from app.repositories.models import CommandExecutionModel, TransformationContinuationModel
from app.services.command_executor_service import CommandExecutorService
from app.services.transformation_continuation_service import TransformationContinuationService
from app.orchestration.transformer_graph import TransformerWorkflow

LOGGER = logging.getLogger(__name__)


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

    def _wake_command_waiter(self, execution_id: str) -> None:
        with self._scope() as session:
            execution = session.get(CommandExecutionModel, execution_id)
            if execution is None or execution.status not in {
                "succeeded", "failed", "timed_out", "cancelled", "interrupted"
            }:
                return
            continuation = session.query(TransformationContinuationModel).filter_by(
                run_id=execution.run_id,
                current_stage_id=execution.stage_id,
                status="waiting_command",
            ).one_or_none()
            if continuation is not None:
                continuation.status = "queued"
                continuation.wake_sequence += 1
                continuation.state_version += 1
                continuation.updated_at = datetime.now(UTC)

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
