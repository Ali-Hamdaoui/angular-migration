"""Replayable durable event projection for a production preflight."""

from __future__ import annotations

import json
from collections.abc import Iterator

from sqlalchemy import func, select

from app.repositories.preflight_models import PreflightEventModel


class PreflightReplayUnavailableError(ValueError):
    pass


def replay_preflight_events(session, preflight_id: str, *, last_event_id: int | None = None) -> list[dict]:
    rows = list(session.scalars(select(PreflightEventModel).where(PreflightEventModel.preflight_id == preflight_id).order_by(PreflightEventModel.sequence, PreflightEventModel.id)))
    events = [{"event_id": row.id, "preflight_id": row.preflight_id, "event_type": row.event_type, "occurred_at": row.occurred_at.isoformat(), "sequence": row.sequence or index, "payload": row.payload} for index, row in enumerate(rows, start=1)]
    if last_event_id is not None and last_event_id < 0:
        raise PreflightReplayUnavailableError("last event id must not be negative")
    return [event for event in events if last_event_id is None or event["sequence"] > last_event_id]


def format_preflight_sse(event: dict) -> str:
    return f"id: {event['sequence']}\nevent: {event['event_type']}\ndata: {json.dumps(event, sort_keys=True)}\n\n"

def append_preflight_event(session, *, preflight_id: str, event_type: str, actor: str | None, idempotency_key: str | None, payload: dict, occurred_at) -> PreflightEventModel:
    latest = session.scalar(select(func.max(PreflightEventModel.sequence)).where(PreflightEventModel.preflight_id == preflight_id)) or 0
    event = PreflightEventModel(id=f"event-{preflight_id}-{latest + 1}", preflight_id=preflight_id, event_type=event_type, actor=actor, idempotency_key=idempotency_key, payload=payload, occurred_at=occurred_at, sequence=latest + 1)
    session.add(event)
    return event
