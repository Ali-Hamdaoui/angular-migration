# Orchestration

Owns LangGraph graph definitions, mock workflow node wiring, and orchestration
control flow.

Nodes must call state, event, artifact, workspace, command, and policy services
instead of implementing those concerns inline. This module must not write
repositories directly, execute shell commands, or expose frontend APIs.

## Sprint 0 Optimized Mock Graph

AMF-S0-09 models the production workflow shape with mock-only behavior:

1. `create_run_mock`
2. `snapshot_topology_mock`
3. `source_runtime_resolution_mock`
4. `parallel_discovery_fanout_mock`
5. `parallel_discovery_join_mock`
6. `baseline_qualification_mock`
7. `analysis_feasibility_mock`
8. `wait_analysis_approval_mock`
9. `planning_mock`
10. `wait_plan_approval_mock`
11. `stage_loop_mock`
12. `final_assurance_mock`
13. `delivery_gate_mock`
14. `report_mock`

The graph emits ordered backend events, records mock checkpoints, preserves
parallel discovery branch state, and separates deterministic components in `component_executions` from
AI-assisted agents in `agent_executions`. Approval gates pause durably when no
approval decision is present. Auto-approval can immediately approve eligible
mock gates and remains active across the stage loop. Mock cancellation stops
before stage execution and preserves evidence checkpoints. Resume continues from
the last safe mock checkpoint by reinvoking the graph with preserved state.

Every mock stage records checkpoint creation, transformation, cheap validation,
build/expensive validation, repair decision, repair agent execution, risk
approval decision, and stage commit. Sprint 0 does not run real Angular analysis,
commands, repair, or delivery publication.
