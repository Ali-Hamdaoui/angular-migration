"""Mock LangGraph node functions for the optimized Sprint 0 orchestrator.

Nodes mutate only ``OrchestratorState`` and return the full changed state for
LangGraph. They model deterministic components and AI-assisted agents without
writing directly to repositories, frontend state, or arbitrary files.
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
    RunPhase,
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


def _emit(state: OrchestratorState, event_type: WorkflowEventType, payload: dict[str, Any], stage_id: str | None = None) -> MigrationEventDto:
    sequence = len(state.setdefault("emitted_events", [])) + 1
    event = MigrationEventDto(
        event_id=f"evt-{uuid4().hex[:12]}",
        run_id=state["run_id"],
        stage_id=stage_id,
        event_type=event_type,
        occurred_at=_now(),
        sequence=sequence,
        payload=payload,
    )
    state.setdefault("emitted_events", []).append(event)
    return event


def _set_phase(state: OrchestratorState, phase: RunPhase) -> None:
    state["run_phase"] = phase
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"phase": phase.value, "status": state["run_status"].value})


def _checkpoint(state: OrchestratorState, checkpoint_id: str, stage_id: str | None = None) -> None:
    state.setdefault("checkpoints", []).append({"checkpoint_id": checkpoint_id, "stage_id": stage_id, "created_at": _now().isoformat()})


def _record_component(state: OrchestratorState, component_name: str, summary: str, stage_id: str | None = None) -> None:
    execution = AgentExecutionDto(
        execution_id=f"component-exec-{uuid4().hex[:12]}",
        run_id=state["run_id"],
        stage_id=stage_id,
        agent_name=component_name,
        status=AgentStatus.COMPLETED,
        started_at=_now(),
        finished_at=_now(),
        summary=summary,
    )
    state.setdefault("agent_executions", []).append(execution)
    _emit(
        state,
        WorkflowEventType.AGENT_STATE_CHANGED,
        {"execution_id": execution.execution_id, "agent_name": component_name, "status": execution.status.value},
        stage_id=stage_id,
    )


def _build_input_envelope(state: OrchestratorState, stage_id: str | None, allowed_actions: list[AllowedAction]) -> AgentInputEnvelope:
    run_id = state["run_id"]
    return AgentInputEnvelope(
        run_id=run_id,
        stage_id=stage_id,
        workspace=WorkspaceRef(sandbox_path=f"sandbox://runs/{run_id}/app", sandbox_branch=f"migration/{run_id}"),
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


def _run_agent(state: OrchestratorState, agent_name: str, stage_id: str | None, allowed_actions: list[AllowedAction]) -> AgentOutputEnvelope:
    agent = get_agent(agent_name)
    assert agent is not None, f"Agent '{agent_name}' not found in registry"
    output = agent.execute(_build_input_envelope(state, stage_id, allowed_actions))

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
        {"execution_id": execution.execution_id, "agent_name": output.agent_name, "status": output.status.value},
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
            checksum="mock-checksum",
        )
        state.setdefault("artifacts", []).append(artifact)
        _emit(
            state,
            WorkflowEventType.ARTIFACT_CREATED,
            {"artifact_id": artifact.artifact_id, "artifact_type": artifact.artifact_type.value, "relative_path": artifact.relative_path, "checksum": artifact.checksum},
            stage_id=stage_id,
        )

    return output


def _result(state: OrchestratorState, next_node: str, paused: bool = False) -> dict[str, Any]:
    return {
        "run_status": state.get("run_status"),
        "run_phase": state.get("run_phase"),
        "stages": list(state.get("stages", [])),
        "agent_executions": list(state.get("agent_executions", [])),
        "validation_gates": list(state.get("validation_gates", [])),
        "artifacts": list(state.get("artifacts", [])),
        "approval_events": list(state.get("approval_events", [])),
        "emitted_events": list(state.get("emitted_events", [])),
        "approval_decisions": dict(state.get("approval_decisions", {})),
        "current_stage_index": state.get("current_stage_index", 0),
        "parallel_discovery": dict(state.get("parallel_discovery", {})),
        "checkpoints": list(state.get("checkpoints", [])),
        "auto_approval_enabled": state.get("auto_approval_enabled", False),
        "cancel_requested": state.get("cancel_requested", False),
        "paused": paused,
        "next_node": next_node,
    }


def _cancel_if_requested(state: OrchestratorState) -> dict[str, Any] | None:
    if not state.get("cancel_requested"):
        return None
    state["run_status"] = RunStatus.CANCELLED
    _checkpoint(state, "cancelled-preserved-evidence")
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.CANCELLED.value, "reason": "mock cancellation requested"})
    return _result(state, "__end__", paused=False)


_READ_ONLY = [AllowedAction.READ_FILE, AllowedAction.READ_ARTIFACT_SUMMARY]
_READ_AND_ARTIFACT = [AllowedAction.READ_FILE, AllowedAction.READ_ARTIFACT_SUMMARY, AllowedAction.CREATE_ARTIFACT]


def create_run_mock(state: OrchestratorState) -> dict[str, Any]:
    state["run_status"] = RunStatus.RUNNING
    _set_phase(state, RunPhase.PREFLIGHT_SNAPSHOT)
    _checkpoint(state, "run-created")
    return _result(state, "snapshot_topology_mock")


def snapshot_topology_mock(state: OrchestratorState) -> dict[str, Any]:
    _run_agent(state, "Eligibility and Constraint Agent", None, _READ_ONLY)
    _record_component(state, "Snapshot Service", "Created immutable source snapshot placeholder.")
    _record_component(state, "Workspace Topology Classifier", "Classified mock single-application Angular workspace.")
    _checkpoint(state, "snapshot-topology-ready")
    return _result(state, "source_runtime_resolution_mock")


def source_runtime_resolution_mock(state: OrchestratorState) -> dict[str, Any]:
    _record_component(state, "Toolchain Runtime Manager", "Resolved source-compatible runtime profile placeholder.")
    return _result(state, "parallel_discovery_fanout_mock")


def parallel_discovery_fanout_mock(state: OrchestratorState) -> dict[str, Any]:
    _set_phase(state, RunPhase.DISCOVERY_BASELINE)
    state["parallel_discovery"] = {
        "source_scan": "queued",
        "dependency_audit": "queued",
        "topology_scan": "queued",
    }
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"parallel_discovery": "fanout", "branches": list(state["parallel_discovery"].keys())})
    return _result(state, "parallel_discovery_join_mock")


def parallel_discovery_join_mock(state: OrchestratorState) -> dict[str, Any]:
    state["parallel_discovery"] = {key: "completed" for key in state.get("parallel_discovery", {}) or {"source_scan": "queued", "dependency_audit": "queued", "topology_scan": "queued"}}
    _record_component(state, "Discovery Join", "Joined source, dependency, and topology discovery branches.")
    _checkpoint(state, "discovery-joined")
    return _result(state, "baseline_qualification_mock")


def baseline_qualification_mock(state: OrchestratorState) -> dict[str, Any]:
    _record_component(state, "Baseline Qualification Service", "Recorded mock baseline qualification.")
    return _result(state, "analysis_feasibility_mock")


def analysis_feasibility_mock(state: OrchestratorState) -> dict[str, Any]:
    _set_phase(state, RunPhase.FEASIBILITY_PLANNING)
    _run_agent(state, "Analysis Agent", None, _READ_AND_ARTIFACT)
    state["run_status"] = RunStatus.WAITING
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.WAITING.value})
    return _result(state, "wait_analysis_approval_mock")


def wait_analysis_approval_mock(state: OrchestratorState) -> dict[str, Any]:
    decision = state.get("approval_decisions", {}).get("analysis")
    if state.get("auto_approval_enabled") and decision is None:
        state.setdefault("approval_decisions", {})["analysis"] = ApprovalDecision.APPROVED
        decision = ApprovalDecision.APPROVED
    if decision == ApprovalDecision.APPROVED:
        state["run_status"] = RunStatus.RUNNING
        _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.RUNNING.value, "approval": "analysis"})
        return _result(state, "planning_mock", paused=False)
    if decision == ApprovalDecision.REJECTED:
        state["run_status"] = RunStatus.FAILED
        _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.FAILED.value})
        return _result(state, "__end__", paused=False)
    state["run_status"] = RunStatus.WAITING
    _emit(state, WorkflowEventType.APPROVAL_REQUIRED, {"approval_id": "approval-analysis", "decision": ApprovalDecision.PENDING.value, "rationale": "Mock analysis approval required."})
    return _result(state, "__end__", paused=True)


def planning_mock(state: OrchestratorState) -> dict[str, Any]:
    _run_agent(state, "Planning Agent", None, _READ_AND_ARTIFACT)
    state["run_status"] = RunStatus.WAITING
    _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.WAITING.value})
    return _result(state, "wait_plan_approval_mock")


def wait_plan_approval_mock(state: OrchestratorState) -> dict[str, Any]:
    decision = state.get("approval_decisions", {}).get("plan")
    if state.get("auto_approval_enabled") and decision is None:
        state.setdefault("approval_decisions", {})["plan"] = ApprovalDecision.APPROVED
        decision = ApprovalDecision.APPROVED
    if decision == ApprovalDecision.APPROVED:
        state["run_status"] = RunStatus.RUNNING
        _set_phase(state, RunPhase.STAGED_MIGRATION)
        return _result(state, "stage_loop_mock", paused=False)
    if decision == ApprovalDecision.REJECTED:
        state["run_status"] = RunStatus.FAILED
        _emit(state, WorkflowEventType.RUN_STATE_CHANGED, {"status": RunStatus.FAILED.value})
        return _result(state, "__end__", paused=False)
    state["run_status"] = RunStatus.WAITING
    _emit(state, WorkflowEventType.APPROVAL_REQUIRED, {"approval_id": "approval-plan", "decision": ApprovalDecision.PENDING.value, "rationale": "Mock plan approval required."})
    return _result(state, "__end__", paused=True)


def stage_loop_mock(state: OrchestratorState) -> dict[str, Any]:
    cancelled = _cancel_if_requested(state)
    if cancelled is not None:
        return cancelled
    index = state.get("current_stage_index", 0)
    if index >= len(state.get("stages", [])):
        return _result(state, "final_assurance_mock")
    return _run_stage(state, index, "stage_loop_mock")


def _stage_gate(state: OrchestratorState, stage_id: str, name: str, status: ValidationStatus = ValidationStatus.PASSED) -> None:
    gate = ValidationGateDto(
        gate_id=f"gate-{name}-{stage_id}",
        run_id=state["run_id"],
        stage_id=stage_id,
        name=name,
        status=status,
        checked_at=_now(),
        details=None,
    )
    state.setdefault("validation_gates", []).append(gate)
    _emit(state, WorkflowEventType.VALIDATION_GATE_CHANGED, {"gate_id": gate.gate_id, "name": name, "status": status.value}, stage_id=stage_id)


def _run_stage(state: OrchestratorState, stage_index: int, next_node: str) -> dict[str, Any]:
    stage = state["stages"][stage_index]
    stage_id = stage["stage_id"]
    _checkpoint(state, f"{stage_id}-checkpoint-start", stage_id)
    stage["status"] = StageStatus.RUNNING
    _emit(state, WorkflowEventType.STAGE_STATE_CHANGED, {"status": StageStatus.RUNNING.value}, stage_id=stage_id)

    _record_component(state, "Checkpoint Service", "Created safe stage checkpoint.", stage_id)
    _run_agent(state, "Transformation Agent", stage_id, _READ_AND_ARTIFACT)
    _stage_gate(state, stage_id, "cheap_validation")
    _run_agent(state, "Build / Validation Agent", stage_id, _READ_AND_ARTIFACT)
    _stage_gate(state, stage_id, "expensive_validation")
    _record_component(state, "Repair Decision", "No repair required for mock stage.", stage_id)
    _run_agent(state, "Repair Agent", stage_id, _READ_ONLY)
    _record_component(state, "Risk Approval Decision", "Risk accepted by mock policy.", stage_id)

    stage["status"] = StageStatus.PASSED
    _emit(state, WorkflowEventType.STAGE_STATE_CHANGED, {"status": StageStatus.PASSED.value}, stage_id=stage_id)
    _checkpoint(state, f"{stage_id}-committed", stage_id)
    state["current_stage_index"] = stage_index + 1
    return _result(state, next_node)


def final_assurance_mock(state: OrchestratorState) -> dict[str, Any]:
    _set_phase(state, RunPhase.FINAL_ASSURANCE)
    _record_component(state, "Final Assurance", "Recorded mock final assurance evidence.")
    return _result(state, "delivery_gate_mock")


def delivery_gate_mock(state: OrchestratorState) -> dict[str, Any]:
    _set_phase(state, RunPhase.DELIVERY_REPORTING)
    _record_component(state, "Delivery Gate", "Delivery remains unpublished in Sprint 0 mock run.")
    return _result(state, "report_mock")


def report_mock(state: OrchestratorState) -> dict[str, Any]:
    _run_agent(state, "Report Agent", None, _READ_AND_ARTIFACT)
    state["run_status"] = RunStatus.COMPLETED
    _emit(state, WorkflowEventType.WORKFLOW_COMPLETED, {"status": RunStatus.COMPLETED.value})
    _checkpoint(state, "workflow-completed")
    return _result(state, "__end__", paused=False)
