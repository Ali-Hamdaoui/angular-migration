"""Mock LangGraph node functions for the Sprint 0 orchestrator skeleton.

Every node reads and mutates ``OrchestratorState`` only. Nodes call mock
agents through the shared ``AgentInputEnvelope`` / ``AgentOutputEnvelope``
contract, record the result as an ``AgentExecutionDto``, and emit
``MigrationEventDto`` entries into ``state["emitted_events"]``. Nodes
never write to the frontend or bypass state services.

LangGraph applies only the returned dict to the state, so every node
must return all fields it mutated via ``_result``.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.agents.registry import get_agent
from app.domain.contracts import (
    AgentExecutionDto,
    AgentInputEnvelope,
    AgentOutputEnvelope,
    AgentStatus,
    AllowedAction,
    ApprovalDecision,
    ArtifactLocations,
    ArtifactRefDto,
    ArtifactType,
    ClientConstraints,
    MigrationEventDto,
    RunStatus,
    StageStatus,
    ValidationGateDto,
    ValidationStatus,
    WorkflowEventType,
    WorkspaceRef,
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


def _build_input_envelope(
    state: OrchestratorState,
    stage_id: str | None,
    allowed_actions: list[AllowedAction],
) -> AgentInputEnvelope:
    """Build a shared input envelope from the orchestrator state."""
    run_id = state["run_id"]
    return AgentInputEnvelope(
        run_id=run_id,
        stage_id=stage_id,
        workspace=WorkspaceRef(
            sandbox_path=f"sandbox://runs/{run_id}/app",
            sandbox_branch=f"migration/{run_id}",
        ),
        client_constraints=ClientConstraints(),
        current_workflow_state=state["run_status"],
        allowed_actions=allowed_actions,
        artifact_locations=ArtifactLocations(
            analysis=f"runs/{run_id}/02_analysis/",
            planning=f"runs/{run_id}/03_planning/",
            validation=f"runs/{run_id}/06_validation/",
            transform=f"runs/{run_id}/05_sandbox_transform/",
            repair=f"runs/{run_id}/07_repair/",
            final=f"runs/{run_id}/08_final/",
        ),
    )


def _run_agent(
    state: OrchestratorState,
    agent_name: str,
    stage_id: str | None,
    allowed_actions: list[AllowedAction],
) -> AgentOutputEnvelope:
    """Call a mock agent through the shared contract and record the result."""
    agent = get_agent(agent_name)
    assert agent is not None, f"Agent '{agent_name}' not found in registry"
    envelope = _build_input_envelope(state, stage_id, allowed_actions)
    output = agent.execute(envelope)

    execution = AgentExecutionDto(
        execution_id=f"agent-exec-{uuid4().hex[:12]}",
        run_id=state["run_id"],
        stage_id=stage_id,
        agent_name=output.agent_name,
        status=output.status,
        started_at=_now(),
        finished_at=_now(),
        summary=output.summary,
    )
    state.setdefault("agent_executions", []).append(execution)

    _emit(
        state,
        WorkflowEventType.AGENT_STATE_CHANGED,
        {
            "execution_id": execution.execution_id,
            "agent_name": output.agent_name,
            "status": output.status.value,
        },
        stage_id=stage_id,
    )

    for artifact_path in output.artifacts_created:
        artifact = ArtifactRefDto(
            artifact_id=f"artifact-{uuid4().hex[:12]}",
            run_id=state["run_id"],
            stage_id=stage_id,
            artifact_type=ArtifactType.JSON,
            relative_path=artifact_path,
            created_at=_now(),
            checksum=None,
        )
        state.setdefault("artifacts", []).append(artifact)
        _emit(
            state,
            WorkflowEventType.ARTIFACT_CREATED,
            {
                "artifact_id": artifact.artifact_id,
                "artifact_type": artifact.artifact_type.value,
                "relative_path": artifact.relative_path,
                "checksum": artifact.checksum,
            },
            stage_id=stage_id,
        )

    return output


def _result(state: OrchestratorState, next_node: str, paused: bool = False) -> dict[str, Any]:
    """Return all mutable state fields so LangGraph applies every change."""
    return {
        "run_status": state.get("run_status"),
        "stages": list(state.get("stages", [])),
        "agent_executions": list(state.get("agent_executions", [])),
        "validation_gates": list(state.get("validation_gates", [])),
        "artifacts": list(state.get("artifacts", [])),
        "approval_events": list(state.get("approval_events", [])),
        "emitted_events": list(state.get("emitted_events", [])),
        "approval_decisions": dict(state.get("approval_decisions", {})),
        "current_stage_index": state.get("current_stage_index", 0),
        "paused": paused,
        "next_node": next_node,
    }


_READ_ONLY = [AllowedAction.READ_FILE, AllowedAction.READ_ARTIFACT_SUMMARY]
_READ_AND_ARTIFACT = [AllowedAction.READ_FILE, AllowedAction.READ_ARTIFACT_SUMMARY, AllowedAction.CREATE_ARTIFACT]


def create_run_mock(state: OrchestratorState) -> dict[str, Any]:
    state["run_status"] = RunStatus.ELIGIBILITY_RUNNING
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.ELIGIBILITY_RUNNING.value})
    return _result(state, "eligibility_mock")


def eligibility_mock(state: OrchestratorState) -> dict[str, Any]:
    _run_agent(state, "Eligibility and Constraint Agent", None, _READ_ONLY)
    state["run_status"] = RunStatus.BASELINE_RUNNING
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.BASELINE_RUNNING.value})
    return _result(state, "baseline_mock")


def baseline_mock(state: OrchestratorState) -> dict[str, Any]:
    state["run_status"] = RunStatus.BASELINE_COMPLETED
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.BASELINE_COMPLETED.value})
    state["run_status"] = RunStatus.ANALYSIS_RUNNING
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.ANALYSIS_RUNNING.value})
    return _result(state, "analysis_mock")


def analysis_mock(state: OrchestratorState) -> dict[str, Any]:
    _run_agent(state, "Analysis Agent", None, _READ_AND_ARTIFACT)
    state["run_status"] = RunStatus.WAITING_ANALYSIS_APPROVAL
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.WAITING_ANALYSIS_APPROVAL.value})
    return _result(state, "wait_analysis_approval_mock")


def wait_analysis_approval_mock(state: OrchestratorState) -> dict[str, Any]:
    decision = state.get("approval_decisions", {}).get("analysis")
    if decision == ApprovalDecision.APPROVED:
        state["run_status"] = RunStatus.PLANNING_RUNNING
        _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.PLANNING_RUNNING.value})
        return _result(state, "planning_mock", paused=False)
    if decision == ApprovalDecision.REJECTED:
        state["run_status"] = RunStatus.FAILED
        _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.FAILED.value})
        return _result(state, "__end__", paused=False)
    state["paused"] = True
    state["run_status"] = RunStatus.WAITING_ANALYSIS_APPROVAL
    _emit(
        state,
        WorkflowEventType.APPROVAL_REQUIRED,
        {"approval_id": "approval-analysis", "decision": ApprovalDecision.PENDING.value, "rationale": "Mock analysis approval required."},
    )
    return _result(state, "__end__", paused=True)


def planning_mock(state: OrchestratorState) -> dict[str, Any]:
    _run_agent(state, "Planning Agent", None, _READ_AND_ARTIFACT)
    state["run_status"] = RunStatus.WAITING_PLAN_APPROVAL
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.WAITING_PLAN_APPROVAL.value})
    return _result(state, "wait_plan_approval_mock")


def wait_plan_approval_mock(state: OrchestratorState) -> dict[str, Any]:
    decision = state.get("approval_decisions", {}).get("plan")
    if decision == ApprovalDecision.APPROVED:
        state["run_status"] = RunStatus.STAGE_RUNNING
        _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.STAGE_RUNNING.value})
        return _result(state, "stage_18_to_19_mock", paused=False)
    if decision == ApprovalDecision.REJECTED:
        state["run_status"] = RunStatus.FAILED
        _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.FAILED.value})
        return _result(state, "__end__", paused=False)
    state["paused"] = True
    state["run_status"] = RunStatus.WAITING_PLAN_APPROVAL
    _emit(
        state,
        WorkflowEventType.APPROVAL_REQUIRED,
        {"approval_id": "approval-plan", "decision": ApprovalDecision.PENDING.value, "rationale": "Mock plan approval required."},
    )
    return _result(state, "__end__", paused=True)


def _run_stage(state: OrchestratorState, stage_index: int, next_node: str) -> dict[str, Any]:
    stage = state["stages"][stage_index]
    stage_id = stage["stage_id"]

    stage["status"] = StageStatus.STAGE_RUNNING
    _emit(state, WorkflowEventType.STAGE_STATE_CHANGED, {"status": StageStatus.STAGE_RUNNING.value}, stage_id=stage_id)

    _run_agent(state, "Transformation Agent", stage_id, _READ_AND_ARTIFACT)
    _run_agent(state, "Build / Validation Agent", stage_id, _READ_AND_ARTIFACT)
    _run_agent(state, "Repair Agent", stage_id, _READ_ONLY)

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

    stage["status"] = StageStatus.STAGE_COMMITTED
    _emit(state, WorkflowEventType.STAGE_STATE_CHANGED, {"status": StageStatus.STAGE_COMMITTED.value}, stage_id=stage_id)

    state["current_stage_index"] = stage_index + 1
    return _result(state, next_node)


def stage_18_to_19_mock(state: OrchestratorState) -> dict[str, Any]:
    return _run_stage(state, 0, "stage_19_to_20_mock")


def stage_19_to_20_mock(state: OrchestratorState) -> dict[str, Any]:
    return _run_stage(state, 1, "stage_20_to_21_mock")


def stage_20_to_21_mock(state: OrchestratorState) -> dict[str, Any]:
    return _run_stage(state, 2, "report_mock")


def report_mock(state: OrchestratorState) -> dict[str, Any]:
    _run_agent(state, "Report Agent", None, _READ_AND_ARTIFACT)
    state["run_status"] = RunStatus.COMPLETED
    _emit(state, WorkflowEventType.WORKFLOW_COMPLETED, {"status": RunStatus.COMPLETED.value})
    return _result(state, "__end__", paused=False)
