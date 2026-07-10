# Sprint 0 Demo Notes

The Sprint 0 demo should call out these architecture boundaries before showing
mock workflow behavior:

1. Backend state is authoritative; the frontend renders snapshots and ordered events.
2. Agents and LLMs propose structured outputs only; the backend validates and executes.
3. The source project is immutable; mutation happens only in the internal workspace.
4. Artifacts are immutable evidence with checksums and approved lookup paths.
5. `migrated-app` appears only after the delivery gate succeeds.
6. SQLite is a single-host MVP store, not the future distributed production store.

Reference the ADR index at [docs/adr/README.md](adr/README.md) during review.
