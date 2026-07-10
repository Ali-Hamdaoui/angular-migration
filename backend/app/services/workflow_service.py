"""Workflow service that runs the mock orchestrator graph.

The service is the boundary between the orchestrator and the rest of
the backend. It exposes a synchronous ``run_mock_workflow`` for tests
and a ``run_mock_workflow_async`` for future SSE integration. Graph
nodes never bypass this service to write to the frontend or database.
"""

from app.domain.contracts import ApprovalDecision, MigrationEventDto, MigrationRunDto
from app.orchestration.mock_graph import build_mock_graph
from app.orchestration.state import OrchestratorState, create_initial_state, state_to_run_dto


def run_mock_workflow(
    run_id: str = "mock-run-angular-18-to-21",
    approvals: dict[str, ApprovalDecision] | None = None,
) -> OrchestratorState:
    """Run the mock graph end-to-end with pre-seeded approval decisions.

    Pass ``approvals={"analysis": ApprovalDecision.APPROVED, "plan": ...}``
    to auto-approve gates. Without approvals the graph pauses at the
    first approval gate and returns early.
    """
    state = create_initial_state(run_id)
    if approvals:
        state["approval_decisions"] = approvals
    graph = build_mock_graph()
    return graph.invoke(state)


def run_mock_workflow_step(
    state: OrchestratorState,
    approval_gate: str,
    decision: ApprovalDecision,
) -> OrchestratorState:
    """Resume a paused graph after injecting an approval decision."""
    state.setdefault("approval_decisions", {})[approval_gate] = decision
    state["paused"] = False
    graph = build_mock_graph()
    return graph.invoke(state)


def get_emitted_events(state: OrchestratorState) -> list[MigrationEventDto]:
    """Return the events emitted by the graph during its execution."""
    return list(state.get("emitted_events", []))


def get_run_dto(state: OrchestratorState) -> MigrationRunDto:
    """Project the orchestrator state into a backend-owned read model."""
    return state_to_run_dto(state)
