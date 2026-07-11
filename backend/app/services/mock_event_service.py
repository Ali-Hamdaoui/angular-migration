"""Ordered mock Server-Sent Events generator for Sprint 0 workflow validation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.domain.contracts import (
    AgentStatus,
    ArtifactType,
    MigrationEventDto,
    RunStatus,
    StageStatus,
    ValidationStatus,
    WorkflowEventType,
)

MOCK_EVENT_DELAY_SECONDS = 1.0
_MOCK_STAGE_ID = "angular-18-to-19"
_RETAINED_EVENTS: dict[str, list[MigrationEventDto]] = {}


class ReplayUnavailableError(ValueError):
    """Raised when requested Last-Event-ID falls before retained history."""


def _build_mock_event_sequence(run_id: str) -> list[MigrationEventDto]:
    """Build and retain a deterministic, ordered sequence covering Sprint 0 event types."""
    if run_id in _RETAINED_EVENTS:
        return _RETAINED_EVENTS[run_id]

    now = datetime.now(UTC)
    events = [
        MigrationEventDto(
            event_id="evt-run-stage-running",
            run_id=run_id,
            event_type=WorkflowEventType.RUN_STATE_CHANGED,
            occurred_at=now,
            payload={"status": RunStatus.RUNNING.value},
        ),
        MigrationEventDto(
            event_id="evt-stage-running",
            run_id=run_id,
            stage_id=_MOCK_STAGE_ID,
            event_type=WorkflowEventType.STAGE_STATE_CHANGED,
            occurred_at=now,
            payload={"status": StageStatus.RUNNING.value},
        ),
        MigrationEventDto(
            event_id="evt-agent-transformation-running",
            run_id=run_id,
            stage_id=_MOCK_STAGE_ID,
            event_type=WorkflowEventType.AGENT_STATE_CHANGED,
            occurred_at=now,
            payload={
                "execution_id": "agent-execution-transformation",
                "agent_name": "Transformation Agent",
                "status": AgentStatus.RUNNING.value,
            },
        ),
        MigrationEventDto(
            event_id="evt-gate-static-symbol",
            run_id=run_id,
            stage_id=_MOCK_STAGE_ID,
            event_type=WorkflowEventType.VALIDATION_GATE_CHANGED,
            occurred_at=now,
            payload={
                "gate_id": "gate-static-symbol-check",
                "name": "static_symbol_check",
                "status": ValidationStatus.PASSED.value,
            },
        ),
        MigrationEventDto(
            event_id="evt-artifact-patch-ledger",
            run_id=run_id,
            stage_id=_MOCK_STAGE_ID,
            event_type=WorkflowEventType.ARTIFACT_CREATED,
            occurred_at=now,
            payload={
                "artifact_id": "artifact-patch-ledger",
                "artifact_type": ArtifactType.PATCH.value,
                "relative_path": "05_sandbox_transform/patch_ledger.json",
                "checksum": "mock-checksum-patch-ledger",
            },
        ),
        MigrationEventDto(
            event_id="evt-agent-transformation-completed",
            run_id=run_id,
            stage_id=_MOCK_STAGE_ID,
            event_type=WorkflowEventType.AGENT_STATE_CHANGED,
            occurred_at=now,
            payload={
                "execution_id": "agent-execution-transformation",
                "agent_name": "Transformation Agent",
                "status": AgentStatus.COMPLETED.value,
            },
        ),
        MigrationEventDto(
            event_id="evt-stage-committed",
            run_id=run_id,
            stage_id=_MOCK_STAGE_ID,
            event_type=WorkflowEventType.STAGE_STATE_CHANGED,
            occurred_at=now,
            payload={"status": StageStatus.PASSED.value},
        ),
        MigrationEventDto(
            event_id="evt-approval-required-stage-2",
            run_id=run_id,
            stage_id="angular-19-to-20",
            event_type=WorkflowEventType.APPROVAL_REQUIRED,
            occurred_at=now,
            payload={
                "approval_id": "approval-stage-2",
                "decision": "PENDING",
                "rationale": "Mock approval required before Stage 2.",
            },
        ),
        MigrationEventDto(
            event_id="evt-workflow-completed",
            run_id=run_id,
            event_type=WorkflowEventType.WORKFLOW_COMPLETED,
            occurred_at=now,
            payload={"status": RunStatus.COMPLETED.value},
        ),
    ]
    ordered = [event.model_copy(update={"sequence": index}) for index, event in enumerate(events, start=1)]
    _RETAINED_EVENTS[run_id] = ordered
    return ordered


def get_retained_events(run_id: str) -> list[MigrationEventDto]:
    return list(_build_mock_event_sequence(run_id))


def replay_events(run_id: str, *, last_event_id: int | None = None, retention: int = 1_000) -> list[MigrationEventDto]:
    events = _build_mock_event_sequence(run_id)[-retention:]
    if not events:
        return []
    first_sequence = events[0].sequence
    if last_event_id is not None and last_event_id < first_sequence - 1:
        raise ReplayUnavailableError("Requested event replay is outside retained history")
    if last_event_id is None:
        return events
    return [event for event in events if event.sequence > last_event_id]


async def generate_mock_events(
    run_id: str,
    delay: float | None = None,
    *,
    last_event_id: int | None = None,
    retention: int = 1_000,
    include_heartbeat: bool = True,
) -> AsyncIterator[MigrationEventDto | str]:
    """Yield retained ordered events, optional replay, and heartbeat frames."""
    if delay is None:
        delay = MOCK_EVENT_DELAY_SECONDS
    for event in replay_events(run_id, last_event_id=last_event_id, retention=retention):
        yield event
        if delay > 0:
            await asyncio.sleep(delay)
    if include_heartbeat:
        yield format_heartbeat(run_id)


def format_sse_event(event: MigrationEventDto) -> str:
    """Format a single event as an SSE text block with sequence ID."""
    return f"id: {event.sequence}\nevent: {event.event_type.value}\ndata: {event.model_dump_json()}\n\n"


def format_heartbeat(run_id: str) -> str:
    payload = json.dumps({"run_id": run_id, "occurred_at": datetime.now(UTC).isoformat()})
    return f"event: heartbeat\ndata: {payload}\n\n"


def format_replay_unavailable(run_id: str, last_event_id: int | None) -> str:
    payload = json.dumps({"run_id": run_id, "last_event_id": last_event_id, "recovery": "snapshot_required"})
    return f"event: replay_unavailable\ndata: {payload}\n\n"
