# Sprint 2 Upstream Boundary

Sprint 2 is owned by another developer. Sprint 3/4 branches audit but do not rebuild it.

Before stage mutation, verify on branch `goal`:

- current G04/G05/G06 decisions and bindings;
- immutable MigrationPlan and StageExecutionPlan;
- exact target versions and ExecutionProfiles;
- plan command references contain structured IDs, never shell strings;
- plan/artifact/workspace fingerprints are current.

Before Sprint 4 LLM calls, also verify:

- production Azure gateway, role router, prompt/schema registry, redaction, invocation/usage/cost ledger, bounded retry, provenance, and readiness;
- no mandatory production path uses `MockLlmGateway`;
- reviewer schemas are non-authoring;
- missing mandatory role configuration fails closed.

If absent or incompatible, use the frozen consuming contract in `shared/contracts/`, implement only the local port/fake needed for owned tests, and record `BLOCKED_UPSTREAM_INTEGRATION` or `CONTRACT_DRIFT`. Never add a second Sprint 2 implementation.
