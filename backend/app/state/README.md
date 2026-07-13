# State

Owns the state transition service boundary, optimistic concurrency,
idempotency, worker lease coordination, cancellation, and resume invariants.

No caller should update run, stage, or step status directly outside this
boundary. This module must not contain API routing, frontend logic, raw command
execution, or LLM calls.

`StateTransitionService` applies accepted transitions in a single database
transaction: it checks `expected_state_version`, updates the run or step,
increments `state_version`, and appends exactly one ordered `workflow_events`
row carrying the idempotency key, actor, reason, and state-version payload.
Duplicate idempotency keys return the original transition result.

Worker completion of terminal step states requires a current lease. Cancellation
is represented as a request transition to `CANCELLING` followed by an
acknowledgement transition to `CANCELLED`, preserving event history. Resume uses
explicit checkpoint, workspace, and policy-compatibility placeholders before
returning a run to `RUNNING`.
