"""Mock LangGraph node functions for the Sprint 0 orchestrator skeleton.

Every node reads and mutates ``OrchestratorState`` only. Nodes emit
``MigrationEventDto`` entries into ``state["emitted_events"]`` so the
backend service layer can persist and stream them — nodes never write
to the frontend or bypass state services.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.domain.contracts import (
    AgentExecutionDto,
    AgentStatus,
    ApprovalDecision,
    ApprovalEventDto,
    ArtifactRefDto,
    ArtifactType,
    MigrationEventDto,
    RunStatus,
    StageStatus,
    ValidationGateDto,
    ValidationStatus,
    WorkflowEventType,
)
from app.orchestration.state import OrchestratorState


def _now() -> datetime:
    return datetime.now(UTC)


def _emit(
    state: OrchestratorState,
    event_type: WorkflowEventType,
    payload: dict[str, Any],
    stage_id: str | None = None,
) -> MigrationEventDto:
    """Append a typed event to the state's emitted_events list."""
    event = MigrationEventDto(
        event_id=f"evt-{uuid4().hex[:12]}",
        run_id=state["run_id"],
        stage_id=stage_id,
        event_type=event_type,
        occurred_at=_now(),
        payload=payload,
    )
    state.setdefault("emitted_events", []).append(event)
    return event


def _add_agent(
    state: OrchestratorState,
    execution_id: str,
    agent_name: str,
    status: AgentStatus,
    stage_id: str | None = None,
) -> AgentExecutionDto:
    agent = AgentExecutionDto(
        execution_id=execution_id,
        run_id=state["run_id"],
        stage_id=stage_id,
        agent_name=agent_name,
        status=status,
        started_at=_now(),
        finished_at=_now() if status in (AgentStatus.COMPLETED, AgentStatus.SKIPPED) else None,
        summary=None,
    )
    state.setdefault("agent_executions", []).append(agent)
    return agent


def create_run_mock(state: OrchestratorState) -> dict[str, Any]:
    state["run_status"] = RunStatus.ELIGIBILITY_RUNNING
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.ELIGIBILITY_RUNNING.value})
    return {"next_node": "eligibility_mock"}


def eligibility_mock(state: OrchestratorState) -> dict[str, Any]:
    _add_agent(state, "agent-eligibility", "Eligibility Agent", AgentStatus.COMPLETED)
    _emit(
        state,
        WorkflowEventType.AGENT_STATE_CHANGED,
        {"execution_id": "agent-eligibility", "agent_name": "Eligibility Agent", "status": AgentStatus.COMPLETED.value},
    )
    state["run_status"] = RunStatus.BASELINE_RUNNING
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.BASELINE_RUNNING.value})
    return {"next_node": "baseline_mock"}


def baseline_mock(state: OrchestratorState) -> dict[str, Any]:
    _add_agent(state, "agent-baseline", "Baseline Agent", AgentStatus.COMPLETED)
    _emit(
        state,
        WorkflowEventType.AGENT_STATE_CHANGED,
        {"execution_id": "agent-baseline", "agent_name": "Baseline Agent", "status": AgentStatus.COMPLETED.value},
    )
    state["run_status"] = RunStatus.ANALYSIS_RUNNING
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.ANALYSIS_RUNNING.value})
    return {"next_node": "analysis_mock"}


def analysis_mock(state: OrchestratorState) -> dict[str, Any]:
    _add_agent(state, "agent-analysis", "Analysis Agent", AgentStatus.COMPLETED)
    _emit(
        state,
        WorkflowEventType.AGENT_STATE_CHANGED,
        {"execution_id": "agent-analysis", "agent_name": "Analysis Agent", "status": AgentStatus.COMPLETED.value},
    )
    state["run_status"] = RunStatus.WAITING_ANALYSIS_APPROVAL
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.WAITING_ANALYSIS_APPROVAL.value})
    return {"next_node": "wait_analysis_approval_mock"}


def wait_analysis_approval_mock(state: OrchestratorState) -> dict[str, Any]:
    decision = state.get("approval_decisions", {}).get("analysis")
    if decision == ApprovalDecision.APPROVED:
        state["run_status"] = RunStatus.PLANNING_RUNNING
        _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.PLANNING_RUNNING.value})
        return {"next_node": "planning_mock", "paused": False}
    if decision == ApprovalDecision.REJECTED:
        state["run_status"] = RunStatus.FAILED
        _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.FAILED.value})
        return {"next_node": "__end__", "paused": False}
    state["paused"] = True
    state["run_status"] = RunStatus.WAITING_ANALYSIS_APPROVAL
    _emit(
        state,
        WorkflowEventType.APPROVAL_REQUIRED,
        {"approval_id": "approval-analysis", "decision": ApprovalDecision.PENDING.value, "rationale": "Mock analysis approval required."},
    )
    return {"next_node": "__end__", "paused": True}


def planning_mock(state: OrchestratorState) -> dict[str, Any]:
    _add_agent(state, "agent-planning", "Planning Agent", AgentStatus.COMPLETED)
    _emit(
        state,
        WorkflowEventType.AGENT_STATE_CHANGED,
        {"execution_id": "agent-planning", "agent_name": "Planning Agent", "status": AgentStatus.COMPLETED.value},
    )
    state["run_status"] = RunStatus.WAITING_PLAN_APPROVAL
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.WAITING_PLAN_APPROVAL.value})
    return {"next_node": "wait_plan_approval_mock"}


def wait_plan_approval_mock(state: OrchestratorState) -> dict[str, Any]:
    decision = state.get("approval_decisions", {}).get("plan")
    if decision == ApprovalDecision.APPROVED:
        state["run_status"] = RunStatus.STAGE_RUNNING
        _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.STAGE_RUNNING.value})
        return {"next_node": "stage_18_to_19_mock", "paused": False}
    if decision == ApprovalDecision.REJECTED:
        state["run_status"] = RunStatus.FAILED
        _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.FAILED.value})
        return {"next_node": "__end__", "paused": False}
    state["paused"] = True
    state["run_status"] = RunStatus.WAITING_PLAN_APPROVAL
    _emit(
        state,
        WorkflowEventType.APPROVAL_REQUIRED,
        {"approval_id": "approval-plan", "decision": ApprovalDecision.PENDING.value, "rationale": "Mock plan approval required."},
    )
    return {"next_node": "__end__", "paused": True}


def _run_stage(state: OrchestratorState, stage_index: int, next_node: str) -> dict[str, Any]:
    stage = state["stages"][stage_index]
    stage_id = stage["stage_id"]

    stage["status"] = StageStatus.STAGE_RUNNING
    _emit(state, WorkflowEventType.STAGE_STATE_CHANGED, {"status": StageStatus.STAGE_RUNNING.value}, stage_id=stage_id)

    _add_agent(state, f"agent-transform-{stage_id}", "Transformation Agent", AgentStatus.RUNNING, stage_id=stage_id)
    _emit(
        state,
        WorkflowEventType.AGENT_STATE_CHANGED,
        {"execution_id": f"agent-transform-{stage_id}", "agent_name": "Transformation Agent", "status": AgentStatus.RUNNING.value},
        stage_id=stage_id,
    )

    _add_agent(state, f"agent-build-{stage_id}", "Build Agent", AgentStatus.COMPLETED, stage_id=stage_id)
    _emit(
        state,
        WorkflowEventType.AGENT_STATE_CHANGED,
        {"execution_id": f"agent-build-{stage_id}", "agent_name": "Build Agent", "status": AgentStatus.COMPLETED.value},
        stage_id=stage_id,
    )

    gate = ValidationGateDto(
        gate_id=f"gate-build-{stage_id}",
        run_id=state["run_id"],
        stage_id=stage_id,
        name="build",
        status=ValidationStatus.PASSED,
        checked_at=_now(),
        details=None,
    )
    state.setdefault("validation_gates", []).append(gate)
    _emit(
        state,
        WorkflowEventType.VALIDATION_GATE_CHANGED,
        {"gate_id": gate.gate_id, "name": "build", "status": ValidationStatus.PASSED.value},
        stage_id=stage_id,
    )

    artifact = ArtifactRefDto(
        artifact_id=f"artifact-diff-{stage_id}",
        run_id=state["run_id"],
        stage_id=stage_id,
        artifact_type=ArtifactType.DIFF,
        relative_path=f"05_sandbox_transform/{stage_id}_diff.patch",
        created_at=_now(),
        checksum=f"mock-checksum-{stage_id}",
    )
    state.setdefault("artifacts", []).append(artifact)
    _emit(
        state,
        WorkflowEventType.ARTIFACT_CREATED,
        {"artifact_id": artifact.artifact_id, "artifact_type": ArtifactType.DIFF.value, "relative_path": artifact.relative_path, "checksum": artifact.checksum},
        stage_id=stage_id,
    )

    stage["status"] = StageStatus.STAGE_COMMITTED
    _emit(state, WorkflowEventType.STAGE_STATE_CHANGED, {"status": StageStatus.STAGE_COMMITTED.value}, stage_id=stage_id)

    state["current_stage_index"] = stage_index + 1
    return {"next_node": next_node}


def stage_18_to_19_mock(state: OrchestratorState) -> dict[str, Any]:
    return _run_stage(state, 0, "stage_19_to_20_mock")


def stage_19_to_20_mock(state: OrchestratorState) -> dict[str, Any]:
    return _run_stage(state, 1, "stage_20_to_21_mock")


def stage_20_to_21_mock(state: OrchestratorState) -> dict[str, Any]:
    return _run_stage(state, 2, "report_mock")


def report_mock(state: OrchestratorState) -> dict[str, Any]:
    _add_agent(state, "agent-report", "Report Agent", AgentStatus.COMPLETED)
    _emit(
        state,
        WorkflowEventType.AGENT_STATE_CHANGED,
        {"execution_id": "agent-report", "agent_name": "Report Agent", "status": AgentStatus.COMPLETED.value},
    )
    state["run_status"] = RunStatus.COMPLETED
    _emit(state, WorkflowEventType.WORKFLOW_COMPLETED, {"status": RunStatus.COMPLETED.value})
    return {"next_node": "__end__", "paused": False}
