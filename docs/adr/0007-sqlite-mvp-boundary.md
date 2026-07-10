# ADR-0007: SQLite Single-Host MVP Operating Boundary

## Status

Accepted for Sprint 0.

## Context

Sprint 0 targets a local, single-host MVP. SQLite is simple and adequate for
that scope, but it is not the right boundary for distributed workers or high
concurrency.

## Decision

SQLite with WAL, busy timeout, small transactions, optimistic state versions,
and artifacts stored outside the database is accepted for the single-host MVP.
PostgreSQL is required before multiple backend instances, distributed workers,
enterprise multi-user operation, high write concurrency, or production HA.

Forbidden shortcuts:

- Storing large artifact blobs or full logs in SQLite.
- Running multiple backend instances against SQLite as a production pattern.
- Treating SQLite locks as a distributed lease mechanism.
- Hiding write contention or retry exhaustion.
- Migrating to production without a PostgreSQL decision and migration plan.

## Rationale

SQLite keeps Sprint 0 reproducible while preserving a clear upgrade trigger for
future production architecture.

## Consequences

State transitions must remain short and transactional. Observability must record
SQLite contention. Any move to distributed execution must first introduce a
PostgreSQL ADR, migration, and operational checklist.
