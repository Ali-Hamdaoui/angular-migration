# S1-F01 Progress

Feature: Reconcile Sprint 0 contracts with the authoritative workflow.

## Completed issues

- S1-F01-I01 — authoritative state dimensions and production auto-approval rejection (`92c6840`).
- S1-F01-I02 — additive SQLite migration, repository updates, `/api/v1` compatibility surface, OpenAPI, and generated frontend contracts (`6a0d694`).
- S1-F01-I03 — Control Tower projection, authoritative SSE mapping, and removal of the auto-approval UI control (`2539202`).
- S1-F01-I04 — regression, security, and documentation coverage (in progress).

## Authority decisions

- SQLite remains the authoritative persisted state store.
- Transition Service remains the legal state-write boundary.
- LangGraph and SSE are projections/coordination mechanisms, not business-state authorities.
- Production auto-approval is disabled and returns `AUTO_APPROVAL_NOT_ALLOWED`.
- Sprint 0 coarse values remain readable for migration compatibility.

## Validation

- Backend persistence/API checks pass with a dedicated writable pytest base directory.
- Frontend type checking and Vitest checks pass.
- Full backend-suite runs may be affected by the host pytest temp/cache permission restrictions.