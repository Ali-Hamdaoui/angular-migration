"""Mock LangGraph orchestrator graph for Sprint 0 workflow validation.

The graph wires 11 mock nodes with fixed linear edges for pre-stage
phases and conditional edges at the two approval gates. The router
reads ``next_node`` from the state to decide whether to continue or
pause (route to END).

Nodes never write to the frontend or bypass state services; they only
mutate ``OrchestratorState`` and append to ``emitted_events``.
"""

from langgraph.graph import END, StateGraph

from app.orchestration.mock_nodes import (
    analysis_mock,
    baseline_mock,
    create_run_mock,
    eligibility_mock,
    planning_mock,
    report_mock,
    stage_18_to_19_mock,
    stage_19_to_20_mock,
    stage_20_to_21_mock,
    wait_analysis_approval_mock,
    wait_plan_approval_mock,
)
from app.orchestration.state import OrchestratorState

MOCK_NODES = {
    "create_run_mock": create_run_mock,
    "eligibility_mock": eligibility_mock,
    "baseline_mock": baseline_mock,
    "analysis_mock": analysis_mock,
    "wait_analysis_approval_mock": wait_analysis_approval_mock,
    "planning_mock": planning_mock,
    "wait_plan_approval_mock": wait_plan_approval_mock,
    "stage_18_to_19_mock": stage_18_to_19_mock,
    "stage_19_to_20_mock": stage_19_to_20_mock,
    "stage_20_to_21_mock": stage_20_to_21_mock,
    "report_mock": report_mock,
}

EXPECTED_NODE_NAMES = list(MOCK_NODES.keys())


def _route_by_next_node(state: OrchestratorState) -> str:
    next_node = state.get("next_node", "__end__")
    if next_node == "__end__":
        return END
    return next_node


def build_mock_graph():
    """Construct and compile the mock orchestrator graph."""
    graph = StateGraph(OrchestratorState)

    for name, fn in MOCK_NODES.items():
        graph.add_node(name, fn)

    graph.set_entry_point("create_run_mock")

    graph.add_edge("create_run_mock", "eligibility_mock")
    graph.add_edge("eligibility_mock", "baseline_mock")
    graph.add_edge("baseline_mock", "analysis_mock")
    graph.add_edge("analysis_mock", "wait_analysis_approval_mock")

    graph.add_conditional_edges("wait_analysis_approval_mock", _route_by_next_node)

    graph.add_edge("planning_mock", "wait_plan_approval_mock")
    graph.add_conditional_edges("wait_plan_approval_mock", _route_by_next_node)

    graph.add_edge("stage_18_to_19_mock", "stage_19_to_20_mock")
    graph.add_edge("stage_19_to_20_mock", "stage_20_to_21_mock")
    graph.add_edge("stage_20_to_21_mock", "report_mock")
    graph.add_edge("report_mock", END)

    return graph.compile()
