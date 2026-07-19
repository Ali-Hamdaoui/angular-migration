# MT-003 — S4-F09 Authoritative Manual Scenario

## Metadata

- Goal: `G07`
- Feature/Jira: `S4-F09` / `AMFA-219`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/07-patch-validation-loop`

## User-observable outcome

A reviewer can see attempt counts, patch/failure fingerprints, error deltas, duplicate/no-progress decisions, rollback or stage reconstruction, and diagnostic hold after policy limits.

## Exact backlog manual scenario

**Preconditions:** S4-F08; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Repair history view with attempts/revisions/transport retries separated, progress chart/table, stop reason, recovery action, and diagnostic-hold state.**.
3. Trigger the primary action for **Stop no-progress repair loops and reconstruct or roll back safely** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can see attempt counts, patch/failure fingerprints, error deltas, duplicate/no-progress decisions, rollback or stage reconstruction, and diagnostic hold after policy limits. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Attempt counters/outcomes, no-progress decisions, rollback/reconstruction records, state/events.` are retrievable through `GET /api/v1/runs/{id}/repair-chains/{chainId}; POST /api/v1/runs/{id}/repair-chains/{chainId}/recover` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Attempt lineage, fingerprint comparison, error-delta history, rollback/reconstruction report, and diagnostic-hold summary.

**Expected durable event:** DUPLICATE_PATCH_REJECTED, NO_PROGRESS_DETECTED, REPAIR_ROLLED_BACK, STAGE_RECONSTRUCTED, ATTEMPT_LIMIT_REACHED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
