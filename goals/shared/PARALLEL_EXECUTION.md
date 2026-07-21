# Ten-Session Parallel Execution V3

All ten Hermes sessions may start from the same immutable `goal` SHA recorded in `.base-lock.json`.

## Contract-first rule

Downstream code consumes frozen schemas under `shared/contracts/`. It may define a local Protocol/port and test fake when upstream code is not integrated, but must not implement/copy the upstream production authority. Test fakes never activate in production configuration.

## Branch-local completion

G01–G09 may become `branch_ready` when their owned code/contracts/tests/manual evidence/docs/audits pass. Missing integrated dependencies are recorded in `blocked_integrated_criteria` and dependency evidence.

G10 Phase A may become `harness_ready` when its acceptance harness is green. It cannot mark AMFA-225/Jira complete.

## Integration completion

The integration coordinator merges in `INTEGRATION_ORDER.md`, resolves Alembic heads and shared generators, connects real adapters, and runs cross-goal tests. Goal 10 Phase B owns the final integrated product proof. Only that evidence sets `integration_verified=true` for AMFA-225.

## Shared state

Each session uses the local terminal backend, one writer at a time, unique runtime resources, and declared shared-file edits. Aggregate OpenAPI/TypeScript/event outputs are regenerated once during integration unless a goal explicitly owns generator source.
