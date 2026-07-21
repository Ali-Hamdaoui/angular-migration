# MT-001 — S4-F04 Authoritative Manual Scenario

## Metadata

- Goal: `G06`
- Feature/Jira: `S4-F04` / `AMFA-214`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/06-repair-agents-g10`

## User-observable outcome

A reviewer can invoke the Proposer on one eligible FailureEvidence/ContextPack and inspect its evidence-backed diagnosis, minimal strategy, exact unified diff, changed files, risks, and usage.

## Exact backlog manual scenario

**Preconditions:** S4-F03, S2-F03; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Proposer viewer with diagnosis, evidence refs, strategy, read-only diff, risk notes, validation errors, model provenance, and usage.**.
3. Trigger the primary action for **Generate and review a Proposer repair candidate** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can invoke the Proposer on one eligible FailureEvidence/ContextPack and inspect its evidence-backed diagnosis, minimal strategy, exact unified diff, changed files, risks, and usage. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Proposer invocation/result metadata, status, context lineage, usage/cost, artifact refs.` are retrievable through `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Structured Proposer response, exact proposed diff, semantic validation report, changed-file inventory, usage/cost.

**Expected durable event:** PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
