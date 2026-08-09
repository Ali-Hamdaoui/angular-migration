"""Atomic per-run workflow-event sequence allocation.

All per-run workflow-event writers allocate their sequence through this
single module, so exactly one writer wins each sequence number for a run
and no IntegrityError on uq_workflow_events_run_sequence can surface to
callers under concurrent append.

Mechanism: a dedicated per-run counter row (run_event_sequences) seeded
self-healingly from MAX(sequence) of the run's existing events, followed by
an atomic UPDATE ... RETURNING. SQLite serializes writers, and the write
statement's snapshot is refreshed at upgrade time, so two concurrent
sessions appending for the same run always observe distinct sequences.
Gaps are allowed; the sequence is monotonic per run.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from typing import Any

from sqlalchemy import func, literal, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.repositories.models import RunEventSequenceModel, WorkflowEventModel


def allocate_event_sequence(session: Session, run_id: str) -> int:
    """Atomically allocate the next workflow-event sequence for a run.

    The counter row is (re)seeded from the run's committed event MAX on the
    first append for a run, healing legacy runs that predate the counter
    table. The UPDATE ... RETURNING executes atomically against the current
    snapshot, so concurrent writers receive distinct, monotonic sequences.
    """
    session.execute(
        insert(RunEventSequenceModel)
        .from_select(
            [RunEventSequenceModel.run_id, RunEventSequenceModel.last_sequence],
            select(
                literal(run_id),
                func.coalesce(func.max(WorkflowEventModel.sequence), 0),
            ).where(WorkflowEventModel.run_id == run_id),
        )
        .on_conflict_do_nothing(index_elements=[RunEventSequenceModel.run_id])
    )
    sequence = session.scalar(
        update(RunEventSequenceModel)
        .where(RunEventSequenceModel.run_id == run_id)
        .values(
            last_sequence=func.max(
                RunEventSequenceModel.last_sequence + 1,
                select(func.coalesce(func.max(WorkflowEventModel.sequence), 0) + 1)
                .where(WorkflowEventModel.run_id == run_id)
                .scalar_subquery(),
            )
        )
        .returning(RunEventSequenceModel.last_sequence)
    )
    if sequence is None:
        raise RuntimeError(f"run event sequence counter missing for run {run_id}")
    return int(sequence)


def append_workflow_event(
    session: Session,
    *,
    run_id: str,
    event_type: str,
    occurred_at: datetime,
    stage_id: str | None = None,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    actor: str | None = None,
    reason: str | None = None,
    event_id: str | None = None,
) -> WorkflowEventModel:
    """Allocate a per-run sequence and append one workflow event in-session."""
    event = WorkflowEventModel(
        id=event_id or f"event-{uuid4().hex[:12]}",
        run_id=run_id,
        stage_id=stage_id,
        event_type=event_type,
        idempotency_key=idempotency_key,
        actor=actor,
        reason=reason,
        sequence=allocate_event_sequence(session, run_id),
        payload=payload or {},
        occurred_at=occurred_at,
    )
    session.add(event)
    return event
