"""Separate durable Transformer and command worker process."""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from uuid import uuid4

from app.core.config import get_settings
from app.repositories.session import session_scope
from app.services.command_executor_service import CommandExecutorService

LOGGER = logging.getLogger(__name__)


class TransformerWorker:
    def __init__(
        self,
        *,
        worker_id: str | None = None,
        command_executor: CommandExecutorService | None = None,
        poll_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.worker_id = worker_id or f"transformer-{os.getpid()}-{uuid4().hex[:8]}"
        self.command_executor = command_executor or CommandExecutorService()
        self.poll_seconds = poll_seconds or settings.transformer_worker_poll_seconds

    def run_once(self) -> bool:
        now = datetime.now(UTC)
        with session_scope() as session:
            self.command_executor.reconcile_expired_executions(session, now)
            execution_id = self.command_executor.claim_next_execution(
                session,
                self.worker_id,
                now,
                lease_seconds=get_settings().worker_lease_seconds,
            )
        if execution_id is None:
            return False
        self.command_executor.execute_claimed_execution(execution_id, self.worker_id)
        return True

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
