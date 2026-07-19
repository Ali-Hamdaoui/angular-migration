# Manual Runtime Test Standards

Manual validation follows automated green and uses the real isolated application. Each case records metadata, preconditions, fixture, exact steps, expected and actual outcomes, backend/database/event/artifact/source-safety evidence, cleanup, verdict, commit SHA, screenshots, network/SSE captures, logs, and traces.

Required categories when applicable: happy path, invalid/stale/tampered input, idempotency/double action, failure, cancellation/timeout, backend restart/recovery, approval pause/resume/reject/stale, SSE reconnect/replay, source/workspace safety, security negatives, keyboard/accessibility, observability, and limitations.

The manual tester is independent and cannot edit code/tests. A failure returns to implementation and related regression.
