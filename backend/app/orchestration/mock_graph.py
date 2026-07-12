"""Optimized mock LangGraph orchestrator for Sprint 0 workflow validation.

The graph models the six macro phases, deterministic pre-stage components,
parallel discovery fan-out/fan-in, durable approval pauses, a stage loop,
final assurance, delivery gating, and reporting. Nodes mutate only
``OrchestratorState`` and emit backend-owned events.
"""

from langgraph.graph import END, StateGraph

from app.orchestration.mock_nodes import (
    analysis_feasibility_mock,
    baseline_qualification_mock,
    create_run_mock,
    delivery_gate_mock,
    final_assurance_mock,
    parallel_discovery_fanout_mock,
    parallel_discovery_join_mock,
    planning_mock,
    report_mock,
    snapshot_topology_mock,
    source_runtime_resolution_mock,
    stage_loop_mock,
    wait_analysis_approval_mock,
    wait_plan_approval_mock,
)
from app.orchestration.state import OrchestratorState

MOCK_NODES = {
    "create_run_mock": create_run_mock,
    "snapshot_topology_mock": snapshot_topology_mock,
    "source_runtime_resolution_mock": source_runtime_resolution_mock,
    "parallel_discovery_fanout_mock": parallel_discovery_fanout_mock,
    "parallel_discovery_join_mock": parallel_discovery_join_mock,
    "baseline_qualification_mock": baseline_qualification_mock,
    "analysis_feasibility_mock": analysis_feasibility_mock,
    "wait_analysis_approval_mock": wait_analysis_approval_mock,
    "planning_mock": planning_mock,
    "wait_plan_approval_mock": wait_plan_approval_mock,
    "stage_loop_mock": stage_loop_mock,
    "final_assurance_mock": final_assurance_mock,
    "delivery_gate_mock": delivery_gate_mock,
    "report_mock": report_mock,
}

EXPECTED_NODE_NAMES = list(MOCK_NODES.keys())


def _route_by_next_node(state: OrchestratorState) -> str:
    next_node = state.get("next_node", "__end__")
    if next_node == "__end__":
        return END
    return next_node


def build_mock_graph():
    """Construct and compile the optimized mock orchestrator graph."""
    graph = StateGraph(OrchestratorState)

    for name, fn in MOCK_NODES.items():
        graph.add_node(name, fn)

    graph.set_entry_point("create_run_mock")
    graph.add_edge("create_run_mock", "snapshot_topology_mock")
    graph.add_edge("snapshot_topology_mock", "source_runtime_resolution_mock")
    graph.add_edge("source_runtime_resolution_mock", "parallel_discovery_fanout_mock")
    graph.add_edge("parallel_discovery_fanout_mock", "parallel_discovery_join_mock")
    graph.add_edge("parallel_discovery_join_mock", "baseline_qualification_mock")
    graph.add_edge("baseline_qualification_mock", "analysis_feasibility_mock")
    graph.add_edge("analysis_feasibility_mock", "wait_analysis_approval_mock")
    graph.add_conditional_edges("wait_analysis_approval_mock", _route_by_next_node)
    graph.add_edge("planning_mock", "wait_plan_approval_mock")
    graph.add_conditional_edges("wait_plan_approval_mock", _route_by_next_node)
    graph.add_conditional_edges("stage_loop_mock", _route_by_next_node)
    graph.add_edge("final_assurance_mock", "delivery_gate_mock")
    graph.add_edge("delivery_gate_mock", "report_mock")
    graph.add_edge("report_mock", END)

    return graph.compile()
