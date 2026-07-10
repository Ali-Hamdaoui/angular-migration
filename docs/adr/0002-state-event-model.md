# ADR-0002: Backend-Owned State and Ordered Events

## Status

Accepted for Sprint 0.

## Context

Long-running migrations can experience retries, browser refresh, SSE reconnects,
duplicate submissions, stale workers, cancellation, and resume. The UI must not
become a second workflow engine.

## Decision

Backend persisted state is authoritative. Ordered events describe accepted
transitions and support SSE replay, but they do not replace the state snapshot.
All accepted workflow changes must go through the transition service with state
version checks, idempotency keys, actor, reason, and event emission.

Forbidden shortcuts:

- Updating run, stage, or step status directly in repositories.
- Letting the frontend infer progress from timers or local event counts.
- Emitting an event without the corresponding state change.
- Changing state without an ordered event for accepted transitions.
- Treating SSE delivery as durable state.

## Rationale

One transition boundary prevents invalid combinations and keeps replay,
cancellation, approval, and resume behavior auditable.

## Consequences

Tests for state-changing code must verify stale-version rejection, idempotency,
and event consistency. UI code must recover from snapshots when event replay is
missing or duplicated.
