"""LangGraph state for the mock migration orchestrator.

The state is the only mutable context the graph nodes read and write.
Nodes must not bypass this state to mutate frontend or database records
directly; they emit events through ``emitted_events`` so the backend
service layer can persist and stream them.
"""

from typing import Any, TypedDict

from app.domain.contracts import (
    AgentExecutionDto,
    ApprovalDecision,
    ApprovalEventDto,
    ArtifactRefDto,
    MigrationEventDto,
    MigrationRunDto,
    MigrationStageDto,
    RunStatus,
    StageStatus,
    ValidationGateDto,
)


class StageState(TypedDict, total=False):
    stage_id: str
    stage_order: int
    source_angular_version: str
    target_angular_version: str
    status: StageStatus


class OrchestratorState(TypedDict, total=False):
    """Mutable graph state shared across all mock nodes."""

    run_id: str
    run_status: RunStatus
    source_angular_version: str
    target_angular_version: str
    stages: list[StageState]
    agent_executions: list[AgentExecutionDto]
    validation_gates: list[ValidationGateDto]
    approval_events: list[ApprovalEventDto]
    artifacts: list[ArtifactRefDto]
    emitted_events: list[MigrationEventDto]
    approval_decisions: dict[str, ApprovalDecision]
    current_stage_index: int
    paused: bool
    next_node: str


def create_initial_state(run_id: str) -> OrchestratorState:
    """Build the entry-point state for a mock Angular 18 → 21 run."""
    return OrchestratorState(
        run_id=run_id,
        run_status=RunStatus.CREATED,
        source_angular_version="18.x",
        target_angular_version="21.x",
        stages=[
            StageState(
                stage_id="angular-18-to-19",
                stage_order=1,
                source_angular_version="18.x",
                target_angular_version="19.x",
                status=StageStatus.STAGE_CREATED,
            ),
            StageState(
                stage_id="angular-19-to-20",
                stage_order=2,
                source_angular_version="19.x",
                target_angular_version="20.x",
                status=StageStatus.STAGE_CREATED,
            ),
            StageState(
                stage_id="angular-20-to-21",
                stage_order=3,
                source_angular_version="20.x",
                target_angular_version="21.x",
                status=StageStatus.STAGE_CREATED,
            ),
        ],
        agent_executions=[],
        validation_gates=[],
        approval_events=[],
        artifacts=[],
        emitted_events=[],
        approval_decisions={},
        current_stage_index=0,
        paused=False,
        next_node="create_run_mock",
    )


def state_to_run_dto(state: OrchestratorState) -> MigrationRunDto:
    """Project the orchestrator state into a backend-owned read model."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    stages = [
        MigrationStageDto(
            stage_id=s["stage_id"],
            run_id=state["run_id"],
            stage_order=s["stage_order"],
            source_angular_version=s["source_angular_version"],
            target_angular_version=s["target_angular_version"],
            status=s["status"],
            created_at=now,
        )
        for s in state.get("stages", [])
    ]
    return MigrationRunDto(
        run_id=state["run_id"],
        status=state["run_status"],
        source_angular_version=state.get("source_angular_version", ""),
        target_angular_version=state.get("target_angular_version", ""),
        created_at=now,
        updated_at=now,
        stages=stages,
        agent_executions=state.get("agent_executions", []),
        validation_gates=state.get("validation_gates", []),
        approval_events=state.get("approval_events", []),
        artifacts=state.get("artifacts", []),
        command_requests=[],
        command_results=[],
        patch_ledger=[],
        repair_attempts=[],
        workflow_events=[],
    )
