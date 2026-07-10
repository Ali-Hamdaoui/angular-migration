"""Tests for the common agent contract and mock agents."""

import pytest
from pydantic import ValidationError

from app.agents.base import BaseMockAgent
from app.agents.mock_agents import MOCK_AGENTS, MOCK_AGENT_NAMES
from app.agents.registry import get_agent, list_agent_names
from app.domain.contracts import (
    AgentInputEnvelope,
    AgentOutputEnvelope,
    AgentStatus,
    AllowedAction,
    RunStatus,
)
from app.orchestration.state import create_initial_state
from app.services.workflow_service import (
    get_emitted_events,
    run_mock_workflow,
)
from app.domain.contracts import ApprovalDecision


# ── Contract model tests ───────────────────────────────────────────


def test_agent_input_envelope_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AgentInputEnvelope(
            run_id="run-001",
            current_workflow_state=RunStatus.CREATED,
            unknown_field=True,  # type: ignore[arg-type]
        )


def test_agent_output_envelope_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AgentOutputEnvelope(
            agent_name="test",
            run_id="run-001",
            status=AgentStatus.COMPLETED,
            summary="test",
            next_recommended_state=RunStatus.COMPLETED,
            unknown_field=True,  # type: ignore[arg-type]
        )


def test_agent_output_envelope_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        AgentOutputEnvelope(
            agent_name="test",
            run_id="run-001",
            status="UNKNOWN",  # type: ignore[arg-type]
            summary="test",
            next_recommended_state=RunStatus.COMPLETED,
        )


# ── Mock agent contract tests ──────────────────────────────────────


def _make_input(stage_id: str | None = None) -> AgentInputEnvelope:
    return AgentInputEnvelope(
        run_id="test-run-001",
        stage_id=stage_id,
        current_workflow_state=RunStatus.CREATED,
        allowed_actions=[AllowedAction.READ_FILE],
    )


@pytest.mark.parametrize("agent", MOCK_AGENTS, ids=MOCK_AGENT_NAMES)
def test_every_mock_agent_uses_the_same_envelope(agent: BaseMockAgent) -> None:
    output = agent.execute(_make_input())
    assert isinstance(output, AgentOutputEnvelope)
    assert output.agent_name == agent.name
    assert output.run_id == "test-run-001"
    assert isinstance(output.status, AgentStatus)
    assert isinstance(output.summary, str)
    assert isinstance(output.artifacts_created, list)
    assert isinstance(output.risks, list)
    assert isinstance(output.requires_human_action, bool)
    assert isinstance(output.next_recommended_state, RunStatus)


@pytest.mark.parametrize("agent", MOCK_AGENTS, ids=MOCK_AGENT_NAMES)
def test_every_mock_agent_returns_a_valid_status(agent: BaseMockAgent) -> None:
    output = agent.execute(_make_input())
    assert output.status in (
        AgentStatus.COMPLETED,
        AgentStatus.FAILED,
        AgentStatus.BLOCKED,
        AgentStatus.SKIPPED,
        AgentStatus.REQUIRES_APPROVAL,
    )


@pytest.mark.parametrize("agent", MOCK_AGENTS, ids=MOCK_AGENT_NAMES)
def test_mock_agent_artifacts_are_relative_paths(agent: BaseMockAgent) -> None:
    output = agent.execute(_make_input("angular-18-to-19"))
    for path in output.artifacts_created:
        assert isinstance(path, str)
        assert "/" in path or path.endswith(".json") or path.endswith(".md")


def test_eight_mock_agents_exist() -> None:
    assert len(MOCK_AGENTS) == 8


def test_mock_agent_names_match_catalog() -> None:
    assert MOCK_AGENT_NAMES == [
        "AI Assistant Agent",
        "Eligibility and Constraint Agent",
        "Analysis Agent",
        "Planning Agent",
        "Transformation Agent",
        "Build / Validation Agent",
        "Repair Agent",
        "Report Agent",
    ]


# ── Registry tests ─────────────────────────────────────────────────


def test_registry_lists_all_eight_agents() -> None:
    assert len(list_agent_names()) == 8


def test_registry_returns_agent_by_name() -> None:
    agent = get_agent("Analysis Agent")
    assert agent is not None
    assert agent.name == "Analysis Agent"


def test_registry_returns_none_for_unknown_agent() -> None:
    assert get_agent("Nonexistent Agent") is None


# ── Individual agent behavior tests ────────────────────────────────


def test_eligibility_agent_recommends_baseline_running() -> None:
    agent = get_agent("Eligibility and Constraint Agent")
    assert agent is not None
    output = agent.execute(_make_input())
    assert output.status == AgentStatus.COMPLETED
    assert output.next_recommended_state == RunStatus.BASELINE_RUNNING
    assert "00_job_setup/eligibility_result.json" in output.artifacts_created


def test_analysis_agent_reports_risks() -> None:
    agent = get_agent("Analysis Agent")
    assert agent is not None
    output = agent.execute(_make_input())
    assert output.status == AgentStatus.COMPLETED
    assert len(output.risks) > 0
    assert output.next_recommended_state == RunStatus.WAITING_ANALYSIS_APPROVAL


def test_planning_agent_recommends_plan_approval() -> None:
    agent = get_agent("Planning Agent")
    assert agent is not None
    output = agent.execute(_make_input())
    assert output.status == AgentStatus.COMPLETED
    assert output.next_recommended_state == RunStatus.WAITING_PLAN_APPROVAL


def test_transformation_agent_creates_stage_artifacts() -> None:
    agent = get_agent("Transformation Agent")
    assert agent is not None
    output = agent.execute(_make_input("angular-18-to-19"))
    assert output.status == AgentStatus.COMPLETED
    assert any("05_sandbox_transform" in p for p in output.artifacts_created)


def test_build_validation_agent_reports_manual_risk() -> None:
    agent = get_agent("Build / Validation Agent")
    assert agent is not None
    output = agent.execute(_make_input("angular-18-to-19"))
    assert output.status == AgentStatus.COMPLETED
    risk_ids = [r.risk_id for r in output.risks]
    assert "manual-browser-smoke-required" in risk_ids


def test_repair_agent_returns_skipped_status() -> None:
    agent = get_agent("Repair Agent")
    assert agent is not None
    output = agent.execute(_make_input("angular-18-to-19"))
    assert output.status == AgentStatus.SKIPPED


def test_report_agent_recommends_completed() -> None:
    agent = get_agent("Report Agent")
    assert agent is not None
    output = agent.execute(_make_input())
    assert output.status == AgentStatus.COMPLETED
    assert output.next_recommended_state == RunStatus.COMPLETED
    assert "08_final/final_evidence_report.md" in output.artifacts_created


def test_ai_assistant_does_not_create_artifacts() -> None:
    agent = get_agent("AI Assistant Agent")
    assert agent is not None
    output = agent.execute(_make_input())
    assert output.artifacts_created == []


# ── Orchestrator integration tests ─────────────────────────────────


def test_orchestrator_records_agent_executions_from_shared_contract() -> None:
    state = run_mock_workflow(
        approvals={"analysis": ApprovalDecision.APPROVED, "plan": ApprovalDecision.APPROVED}
    )
    agent_names = [a.agent_name for a in state["agent_executions"]]
    assert "Eligibility and Constraint Agent" in agent_names
    assert "Analysis Agent" in agent_names
    assert "Planning Agent" in agent_names
    assert "Transformation Agent" in agent_names
    assert "Build / Validation Agent" in agent_names
    assert "Repair Agent" in agent_names
    assert "Report Agent" in agent_names


def test_orchestrator_creates_artifacts_from_agent_outputs() -> None:
    state = run_mock_workflow(
        approvals={"analysis": ApprovalDecision.APPROVED, "plan": ApprovalDecision.APPROVED}
    )
    artifact_paths = [a.relative_path for a in state["artifacts"]]
    assert any("00_job_setup/eligibility_result.json" in p for p in artifact_paths)
    assert any("02_analysis/" in p for p in artifact_paths)
    assert any("03_planning/" in p for p in artifact_paths)
    assert any("05_sandbox_transform/" in p for p in artifact_paths)
    assert any("06_validation/" in p for p in artifact_paths)
    assert any("08_final/" in p for p in artifact_paths)


def test_orchestrator_repair_agent_is_skipped_in_mock_run() -> None:
    state = run_mock_workflow(
        approvals={"analysis": ApprovalDecision.APPROVED, "plan": ApprovalDecision.APPROVED}
    )
    repair_executions = [a for a in state["agent_executions"] if a.agent_name == "Repair Agent"]
    assert len(repair_executions) == 3
    for execution in repair_executions:
        assert execution.status == AgentStatus.SKIPPED


def test_orchestrator_emits_agent_state_changed_for_every_agent_call() -> None:
    state = run_mock_workflow(
        approvals={"analysis": ApprovalDecision.APPROVED, "plan": ApprovalDecision.APPROVED}
    )
    events = get_emitted_events(state)
    agent_events = [e for e in events if e.event_type.value == "agent_state_changed"]
    assert len(agent_events) == len(state["agent_executions"])


def test_orchestrator_emits_artifact_created_for_every_agent_artifact() -> None:
    state = run_mock_workflow(
        approvals={"analysis": ApprovalDecision.APPROVED, "plan": ApprovalDecision.APPROVED}
    )
    events = get_emitted_events(state)
    artifact_events = [e for e in events if e.event_type.value == "artifact_created"]
    assert len(artifact_events) == len(state["artifacts"])
