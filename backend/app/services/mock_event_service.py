"""Mock Server-Sent Events generator for Sprint 0 workflow validation."""

import asyncio
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
_MOCK_RUN_ID = "mock-run-angular-18-to-21"
_MOCK_STAGE_ID = "angular-18-to-19"


def _build_mock_event_sequence(run_id: str) -> list[MigrationEventDto]:
    """Build a deterministic sequence covering every Sprint 0 event type."""
    now = datetime.now(UTC)
    return [
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


async def generate_mock_events(
    run_id: str,
    delay: float | None = None,
) -> AsyncIterator[MigrationEventDto]:
    """Yield a fixed mock event sequence with pauses for SSE streaming.

    Tests may pass ``delay=0`` for instant iteration. The sequence is
    deterministic and covers every ``WorkflowEventType``.
    """
    if delay is None:
        delay = MOCK_EVENT_DELAY_SECONDS
    for event in _build_mock_event_sequence(run_id):
        yield event
        if delay > 0:
            await asyncio.sleep(delay)


def format_sse_event(event: MigrationEventDto) -> str:
    """Format a single event as an SSE text block."""
    return f"event: {event.event_type.value}\ndata: {event.model_dump_json()}\n\n"
