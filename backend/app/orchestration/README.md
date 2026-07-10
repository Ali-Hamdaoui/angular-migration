# Orchestration

Owns LangGraph graph definitions, mock workflow node wiring, and orchestration
control flow.

Nodes must call state, event, artifact, workspace, command, and policy services
instead of implementing those concerns inline. This module must not write
repositories directly, execute shell commands, or expose frontend APIs.