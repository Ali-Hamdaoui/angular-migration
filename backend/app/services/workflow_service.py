"""Workflow service that runs the optimized mock orchestrator graph."""

from app.artifact_store import LocalFilesystemArtifactStore
from app.core.config import get_settings
from app.domain.contracts import ApprovalDecision, MigrationEventDto, MigrationRunDto
from app.orchestration.mock_graph import build_mock_graph
from app.orchestration.state import OrchestratorState, create_initial_state, state_to_run_dto


def get_workflow_artifact_store() -> LocalFilesystemArtifactStore:
    """Create the artifact store used by mock workflow runs."""
    return LocalFilesystemArtifactStore(get_settings().artifact_root)


def run_mock_workflow(
    run_id: str = "mock-run-angular-18-to-21",
    approvals: dict[str, ApprovalDecision] | None = None,
    artifact_store: LocalFilesystemArtifactStore | None = None,
    *,
    auto_approval_enabled: bool = False,
    cancel_requested: bool = False,
) -> OrchestratorState:
    """Run the mock graph with optional approvals, auto-approval, or cancellation."""
    store = artifact_store or get_workflow_artifact_store()
    store.ensure_run_layout(run_id)

    state = create_initial_state(run_id)
    state["auto_approval_enabled"] = auto_approval_enabled
    state["cancel_requested"] = cancel_requested
    if approvals:
        state["approval_decisions"] = approvals
    graph = build_mock_graph()
    return graph.invoke(state)


def run_mock_workflow_step(
    state: OrchestratorState,
    approval_gate: str,
    decision: ApprovalDecision,
    artifact_store: LocalFilesystemArtifactStore | None = None,
) -> OrchestratorState:
    """Resume a paused graph after injecting an approval decision."""
    store = artifact_store or get_workflow_artifact_store()
    store.ensure_run_layout(state["run_id"])

    state.setdefault("approval_decisions", {})[approval_gate] = decision
    state["paused"] = False
    graph = build_mock_graph()
    return graph.invoke(state)


def resume_mock_workflow_from_checkpoint(state: OrchestratorState, artifact_store: LocalFilesystemArtifactStore | None = None) -> OrchestratorState:
    """Resume from the last safe mock checkpoint without changing approval policy."""
    store = artifact_store or get_workflow_artifact_store()
    store.ensure_run_layout(state["run_id"])
    state["paused"] = False
    state["cancel_requested"] = False
    graph = build_mock_graph()
    return graph.invoke(state)


def get_emitted_events(state: OrchestratorState) -> list[MigrationEventDto]:
    """Return the events emitted by the graph during its execution."""
    return list(state.get("emitted_events", []))


def get_run_dto(state: OrchestratorState) -> MigrationRunDto:
    """Project the orchestrator state into a backend-owned read model."""
    return state_to_run_dto(state)
