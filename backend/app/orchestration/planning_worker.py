"""Application-owned planning worker loop for due durable continuations."""

from __future__ import annotations

import asyncio
import logging

from app.orchestration.planning import dispatch_due_planning_jobs

logger = logging.getLogger(__name__)


def run_planning_worker_iteration(*, worker_id: str = "planning-worker") -> int:
    return dispatch_due_planning_jobs(worker_id=worker_id)


async def planning_worker_loop(*, poll_seconds: float, worker_id: str = "planning-worker") -> None:
    while True:
        try:
            run_planning_worker_iteration(worker_id=worker_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("planning worker iteration failed", extra={"worker_id": worker_id})
        await asyncio.sleep(poll_seconds)
