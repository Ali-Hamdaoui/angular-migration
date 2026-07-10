# State

Owns the state transition service boundary, optimistic concurrency,
idempotency, worker lease coordination, cancellation, and resume invariants.

No caller should update run, stage, or step status directly outside this
boundary. This module must not contain API routing, frontend logic, raw command
execution, or LLM calls.