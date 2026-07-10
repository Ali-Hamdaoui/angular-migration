# ADR-0004: Internal Workspace and Atomic Delivery

## Status

Accepted for Sprint 0.

## Context

Writing directly to a final `migrated-app` directory can expose partial or
failed work as complete output and can mutate the original source by mistake.

## Decision

The original source is immutable. Snapshot and manifest services capture source
evidence. All mutation happens only in an internal run workspace. Final output
is published to `migrated-app` only after the delivery gate passes, using a
temporary destination and atomic rename where supported.

Forbidden shortcuts:

- Mutating the original source path.
- Using `migrated-app` as the active working directory.
- Publishing failed, cancelled, or partially validated work.
- Silently overwriting an existing `migrated-app`.
- Letting source, snapshot, workspace, artifact, and delivery paths overlap.

## Rationale

The layout separates evidence, mutable work, and final delivery so cancellation,
resume, audit, and rollback remain understandable.

## Consequences

Delivery code must check source integrity, workspace integrity, conflict policy,
and delivery manifest checksums before publication. Failed and cancelled tests
must assert that `migrated-app` is not created.
