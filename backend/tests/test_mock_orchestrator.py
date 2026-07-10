"""Tests for the mock LangGraph orchestrator graph and state transitions."""

from app.domain.contracts import (
    AgentStatus,
    ApprovalDecision,
    RunStatus,
    StageStatus,
    WorkflowEventType,
)
from app.orchestration.mock_graph import EXPECTED_NODE_NAMES, build_mock_graph
from app.orchestration.state import create_initial_state
from app.services.workflow_service import (
    get_emitted_events,
    get_run_dto,
    run_mock_workflow,
    run_mock_workflow_step,
)

ALL_APPROVALS = {
    "analysis": ApprovalDecision.APPROVED,
    "plan": ApprovalDecision.APPROVED,
}

EXPECTED_EVENT_TYPES = {
    WorkflowEventType.RUN_STATE_CHANGED.value,
    WorkflowEventType.STAGE_STATE_CHANGED.value,
    WorkflowEventType.AGENT_STATE_CHANGED.value,
    WorkflowEventType.VALIDATION_GATE_CHANGED.value,
    WorkflowEventType.ARTIFACT_CREATED.value,
    WorkflowEventType.APPROVAL_REQUIRED.value,
    WorkflowEventType.WORKFLOW_COMPLETED.value,
}


# ── Graph structure tests ──────────────────────────────────────────


def test_graph_contains_all_eleven_mock_nodes() -> None:
    assert len(EXPECTED_NODE_NAMES) == 11
    assert EXPECTED_NODE_NAMES == [
        "create_run_mock",
        "eligibility_mock",
        "baseline_mock",
        "analysis_mock",
        "wait_analysis_approval_mock",
        "planning_mock",
        "wait_plan_approval_mock",
        "stage_18_to_19_mock",
        "stage_19_to_20_mock",
        "stage_20_to_21_mock",
        "report_mock",
    ]


def test_graph_compiles_successfully() -> None:
    graph = build_mock_graph()
    assert graph is not None


# ── End-to-end run tests ───────────────────────────────────────────


def test_mock_graph_runs_end_to_end_with_approvals() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    assert state["run_status"] == RunStatus.COMPLETED
    assert state["paused"] is False


def test_stage_order_is_angular_18_to_19_then_19_to_20_then_20_to_21() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    stages = state["stages"]
    assert len(stages) == 3
    assert stages[0]["stage_id"] == "angular-18-to-19"
    assert stages[0]["source_angular_version"] == "18.x"
    assert stages[0]["target_angular_version"] == "19.x"
    assert stages[1]["stage_id"] == "angular-19-to-20"
    assert stages[1]["source_angular_version"] == "19.x"
    assert stages[1]["target_angular_version"] == "20.x"
    assert stages[2]["stage_id"] == "angular-20-to-21"
    assert stages[2]["source_angular_version"] == "20.x"
    assert stages[2]["target_angular_version"] == "21.x"
    assert all(s["status"] == StageStatus.STAGE_COMMITTED for s in stages)


def test_all_stages_are_committed_after_full_run() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    for stage in state["stages"]:
        assert stage["status"] == StageStatus.STAGE_COMMITTED


def test_graph_emits_all_seven_event_types() -> None:
    full_state = run_mock_workflow(approvals=ALL_APPROVALS)
    full_types = {e.event_type.value for e in get_emitted_events(full_state)}
    paused_state = run_mock_workflow()
    paused_types = {e.event_type.value for e in get_emitted_events(paused_state)}
    combined = full_types | paused_types
    assert EXPECTED_EVENT_TYPES.issubset(combined)


def test_graph_emits_workflow_completed_event() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    events = get_emitted_events(state)
    completed_events = [e for e in events if e.event_type == WorkflowEventType.WORKFLOW_COMPLETED]
    assert len(completed_events) == 1
    assert completed_events[0].payload["status"] == RunStatus.COMPLETED.value


def test_graph_creates_agents_for_every_phase() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    agent_names = [a.agent_name for a in state["agent_executions"]]
    assert "Eligibility Agent" in agent_names
    assert "Baseline Agent" in agent_names
    assert "Analysis Agent" in agent_names
    assert "Planning Agent" in agent_names
    assert "Transformation Agent" in agent_names
    assert "Build Agent" in agent_names
    assert "Report Agent" in agent_names


def test_graph_creates_validation_gates_for_each_stage() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    assert len(state["validation_gates"]) == 3
    for gate in state["validation_gates"]:
        assert gate.name == "build"
        assert gate.status.value == "passed"


def test_graph_creates_artifacts_for_each_stage() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    assert len(state["artifacts"]) == 3
    stage_ids = {a.stage_id for a in state["artifacts"]}
    assert stage_ids == {"angular-18-to-19", "angular-19-to-20", "angular-20-to-21"}


def test_state_to_run_dto_projects_stages_correctly() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    dto = get_run_dto(state)
    assert dto.run_id == state["run_id"]
    assert dto.status == RunStatus.COMPLETED
    assert len(dto.stages) == 3
    assert dto.stages[0].stage_id == "angular-18-to-19"


# ── State transition / approval pause tests ────────────────────────


def test_graph_pauses_at_analysis_approval_without_decisions() -> None:
    state = run_mock_workflow()
    assert state["paused"] is True
    assert state["run_status"] == RunStatus.WAITING_ANALYSIS_APPROVAL
    events = get_emitted_events(state)
    approval_events = [e for e in events if e.event_type == WorkflowEventType.APPROVAL_REQUIRED]
    assert len(approval_events) == 1
    assert approval_events[0].payload["approval_id"] == "approval-analysis"


def test_graph_pauses_at_plan_approval_after_analysis_approved() -> None:
    state = run_mock_workflow(approvals={"analysis": ApprovalDecision.APPROVED})
    assert state["paused"] is True
    assert state["run_status"] == RunStatus.WAITING_PLAN_APPROVAL
    events = get_emitted_events(state)
    approval_events = [e for e in events if e.event_type == WorkflowEventType.APPROVAL_REQUIRED]
    assert len(approval_events) == 1
    assert approval_events[0].payload["approval_id"] == "approval-plan"


def test_graph_completes_after_resume_with_plan_approval() -> None:
    state = run_mock_workflow(approvals={"analysis": ApprovalDecision.APPROVED})
    assert state["paused"] is True
    state = run_mock_workflow_step(state, "plan", ApprovalDecision.APPROVED)
    assert state["paused"] is False
    assert state["run_status"] == RunStatus.COMPLETED


def test_graph_fails_on_analysis_rejection() -> None:
    state = run_mock_workflow(approvals={"analysis": ApprovalDecision.REJECTED})
    assert state["paused"] is False
    assert state["run_status"] == RunStatus.FAILED


def test_graph_fails_on_plan_rejection() -> None:
    state = run_mock_workflow(approvals={"analysis": ApprovalDecision.APPROVED, "plan": ApprovalDecision.REJECTED})
    assert state["paused"] is False
    assert state["run_status"] == RunStatus.FAILED


def test_initial_state_has_three_stages_in_correct_order() -> None:
    state = create_initial_state("test-run")
    assert state["run_status"] == RunStatus.CREATED
    assert len(state["stages"]) == 3
    assert state["stages"][0]["stage_id"] == "angular-18-to-19"
    assert state["stages"][1]["stage_id"] == "angular-19-to-20"
    assert state["stages"][2]["stage_id"] == "angular-20-to-21"
    assert all(s["status"] == StageStatus.STAGE_CREATED for s in state["stages"])
