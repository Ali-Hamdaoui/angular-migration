# AI Frontend Migration Factory

The AI Frontend Migration Factory is a platform for controlled Angular frontend migrations. Its MVP reference path is Angular 18.x to Angular 21.x, using strict compatibility and functional-parity rules.

The product is deliberately split into independent workspaces. The frontend provides the Control Tower experience; the backend is the only execution and workflow authority. Agents may analyse and propose work, but they never execute commands or mutate a migration workspace directly.

## Workspace map

```text
backend/    Backend execution authority: APIs, state, orchestration, policies,
            artifact access, command execution, and the LLM Gateway.
frontend/   Next.js Control Tower UI. It renders backend-owned state only.
shared/     Contract references, schema documentation, and generated shared types.
demo-apps/  Fixture applications used for demos and later migration scenarios.
scripts/    Local developer and repository automation scripts.
docs/       Product, architecture, ADR, setup, and sprint documentation.
tests/      Cross-workspace and end-to-end test suites.
```