# Events

Owns ordered workflow event persistence, replay, heartbeat coordination, and SSE
delivery helpers.

Events are delivery evidence, not the authoritative workflow state. This module
must not decide state transitions, execute commands, mutate workspaces, or let
the frontend invent progress.