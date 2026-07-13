"""Tests for the optimized mock LangGraph orchestrator graph and state transitions."""

from pathlib import Path

import pytest

from app.artifact_store import ARTIFACT_LAYOUT
from app.core.config import get_settings
from app.domain.contracts import (
    ApprovalDecision,
    RunPhase,
    RunStatus,
    StageStatus,
    ValidationStatus,
    WorkflowEventType,
)
from app.orchestration.mock_graph import EXPECTED_NODE_NAMES, build_mock_graph
from app.orchestration.state import create_initial_state
from app.services.workflow_service import (
    get_emitted_events,
    get_run_dto,
    resume_mock_workflow_from_checkpoint,
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


@pytest.fixture(autouse=True)
def isolated_artifact_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    artifact_root = tmp_path / "runs"
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifact_root))
    get_settings.cache_clear()
    yield artifact_root
    get_settings.cache_clear()


def test_graph_contains_optimized_mock_nodes() -> None:
    assert EXPECTED_NODE_NAMES == [
        "create_run_mock",
        "snapshot_topology_mock",
        "source_runtime_resolution_mock",
        "parallel_discovery_fanout_mock",
        "parallel_discovery_join_mock",
        "baseline_qualification_mock",
        "analysis_feasibility_mock",
        "wait_analysis_approval_mock",
        "planning_mock",
        "wait_plan_approval_mock",
        "stage_loop_mock",
        "final_assurance_mock",
        "delivery_gate_mock",
        "report_mock",
    ]


def test_graph_compiles_successfully() -> None:
    graph = build_mock_graph()
    assert graph is not None


def test_mock_graph_runs_end_to_end_through_six_phases() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    assert state["run_status"] == RunStatus.COMPLETED
    assert state["run_phase"] == RunPhase.DELIVERY_REPORTING
    assert state["paused"] is False
    phases = [event.payload.get("phase") for event in get_emitted_events(state)]
    assert RunPhase.PREFLIGHT_SNAPSHOT.value in phases
    assert RunPhase.DISCOVERY_BASELINE.value in phases
    assert RunPhase.FEASIBILITY_PLANNING.value in phases
    assert RunPhase.STAGED_MIGRATION.value in phases
    assert RunPhase.FINAL_ASSURANCE.value in phases
    assert RunPhase.DELIVERY_REPORTING.value in phases


def test_mock_workflow_creates_artifact_run_layout(isolated_artifact_root: Path) -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    run_root = isolated_artifact_root / state["run_id"]

    assert run_root.is_dir()
    assert all((run_root / folder).is_dir() for folder in ARTIFACT_LAYOUT)


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
    assert all(s["status"] == StageStatus.PASSED for s in stages)


def test_parallel_discovery_fanout_and_join_complete() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    assert state["parallel_discovery"] == {
        "source_scan": "completed",
        "dependency_audit": "completed",
        "topology_scan": "completed",
    }
    summaries = [execution.summary for execution in state["component_executions"]]
    assert "Joined source, dependency, and topology discovery branches." in summaries


def test_all_stages_are_committed_after_full_run() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    assert all(stage["status"] == StageStatus.PASSED for stage in state["stages"])
    checkpoint_ids = {checkpoint["checkpoint_id"] for checkpoint in state["checkpoints"]}
    assert "angular-18-to-19-committed" in checkpoint_ids
    assert "angular-19-to-20-committed" in checkpoint_ids
    assert "angular-20-to-21-committed" in checkpoint_ids


def test_graph_emits_all_seven_event_types() -> None:
    full_state = run_mock_workflow(approvals=ALL_APPROVALS)
    full_types = {e.event_type.value for e in get_emitted_events(full_state)}
    paused_state = run_mock_workflow()
    paused_types = {e.event_type.value for e in get_emitted_events(paused_state)}
    combined = full_types | paused_types
    assert EXPECTED_EVENT_TYPES.issubset(combined)


def test_graph_emits_ordered_events() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    sequences = [event.sequence for event in get_emitted_events(state)]
    assert sequences == list(range(1, len(sequences) + 1))


def test_graph_emits_workflow_completed_event() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    events = get_emitted_events(state)
    completed_events = [e for e in events if e.event_type == WorkflowEventType.WORKFLOW_COMPLETED]
    assert len(completed_events) == 1
    assert completed_events[0].payload["status"] == RunStatus.COMPLETED.value


def test_graph_records_deterministic_components_and_ai_agents() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    agent_names = [a.agent_name for a in state["agent_executions"]]
    component_names = [c.component_name for c in state["component_executions"]]
    for expected in [
        "Eligibility and Constraint Agent",
        "Analysis Agent",
        "Planning Agent",
        "Transformation Agent",
        "Build / Validation Agent",
        "Repair Agent",
        "Report Agent",
    ]:
        assert expected in agent_names
    for expected in [
        "Snapshot Service",
        "Workspace Topology Classifier",
        "Toolchain Runtime Manager",
        "Compatibility Resolver",
        "Baseline Qualification Service",
        "Checkpoint Service",
        "Static Symbol Gate",
        "Command Policy Engine",
        "Parity Evidence Engine",
        "Delivery Service",
    ]:
        assert expected in component_names

def test_graph_records_stage_validation_gates_for_cheap_and_expensive_checks() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    assert len(state["validation_gates"]) == 6
    assert {gate.name for gate in state["validation_gates"]} == {"cheap_validation", "expensive_validation"}
    assert all(gate.status == ValidationStatus.PASSED for gate in state["validation_gates"])


def test_graph_creates_artifacts_for_each_stage() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    stage_artifacts = [a for a in state["artifacts"] if a.stage_id is not None]
    stage_ids = {a.stage_id for a in stage_artifacts}
    assert stage_ids == {"angular-18-to-19", "angular-19-to-20", "angular-20-to-21"}


def test_state_to_run_dto_projects_stages_and_phase() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS)
    dto = get_run_dto(state)
    assert dto.run_id == state["run_id"]
    assert dto.status == RunStatus.COMPLETED
    assert dto.run_phase == RunPhase.DELIVERY_REPORTING
    assert len(dto.stages) == 3
    assert dto.stages[0].stage_id == "angular-18-to-19"


def test_graph_pauses_at_analysis_approval_without_decisions() -> None:
    state = run_mock_workflow()
    assert state["paused"] is True
    assert state["run_status"] == RunStatus.WAITING
    events = get_emitted_events(state)
    approval_events = [e for e in events if e.event_type == WorkflowEventType.APPROVAL_REQUIRED]
    assert len(approval_events) == 1
    assert approval_events[0].payload["approval_id"] == "approval-analysis"


def test_graph_pauses_at_plan_approval_after_analysis_approved() -> None:
    state = run_mock_workflow(approvals={"analysis": ApprovalDecision.APPROVED})
    assert state["paused"] is True
    assert state["run_status"] == RunStatus.WAITING
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


def test_auto_approval_completes_and_remains_active() -> None:
    state = run_mock_workflow(auto_approval_enabled=True)
    assert state["run_status"] == RunStatus.COMPLETED
    assert state["auto_approval_enabled"] is True
    assert state["approval_decisions"] == ALL_APPROVALS


def test_mock_cancellation_prevents_future_stage_nodes() -> None:
    state = run_mock_workflow(approvals=ALL_APPROVALS, cancel_requested=True)
    assert state["run_status"] == RunStatus.CANCELLED
    assert state["current_stage_index"] == 0
    assert all(stage["status"] == StageStatus.PENDING for stage in state["stages"])


def test_resume_continues_from_last_safe_checkpoint() -> None:
    state = run_mock_workflow(approvals={"analysis": ApprovalDecision.APPROVED})
    assert state["paused"] is True
    assert state["checkpoints"]
    state.setdefault("approval_decisions", {})["plan"] = ApprovalDecision.APPROVED
    resumed = resume_mock_workflow_from_checkpoint(state)
    assert resumed["run_status"] == RunStatus.COMPLETED
    assert resumed["checkpoints"][-1]["checkpoint_id"] == "workflow-completed"


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
    assert state["run_phase"] == RunPhase.PREFLIGHT_SNAPSHOT
    assert len(state["stages"]) == 3
    assert state["stages"][0]["stage_id"] == "angular-18-to-19"
    assert state["stages"][1]["stage_id"] == "angular-19-to-20"
    assert state["stages"][2]["stage_id"] == "angular-20-to-21"
    assert all(s["status"] == StageStatus.PENDING for s in state["stages"])
