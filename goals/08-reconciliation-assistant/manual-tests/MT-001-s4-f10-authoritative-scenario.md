# MT-001 — S4-F10 Authoritative Manual Scenario

## Metadata

- Goal: `G08`
- Feature/Jira: `S4-F10` / `AMFA-220`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/08-reconciliation-assistant`

## User-observable outcome

After a controlled backend restart, an operator can see stale ownership and artifact inconsistencies reconciled, waiting approvals preserved, and work resumed/reconstructed only from a proven boundary.

## Exact backlog manual scenario

**Preconditions:** S3-F04, S3-F14, S4-F09; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Operator recovery dashboard and run resume panel with proven boundary, preserved approval, quarantine links, and blocked/failure states.**.
3. Trigger the primary action for **Reconcile interrupted commands, leases, artifacts, and graph state on startup** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** After a controlled backend restart, an operator can see stale ownership and artifact inconsistencies reconciled, waiting approvals preserved, and work resumed/reconstructed only from a proven boundary. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Reconciliation run/results, interrupted statuses, lease updates, artifact integrity findings, transitions/events.` are retrievable through `POST /api/v1/operator/reconciliation; GET /api/v1/operator/reconciliation/latest; POST /api/v1/runs/{id}/resume` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Startup reconciliation report, artifact mismatch list, workspace recovery decision, and graph reconstruction summary.

**Expected durable event:** RECONCILIATION_STARTED/COMPLETED, COMMAND_INTERRUPTED, ARTIFACT_INTEGRITY_FAILED, RUN_RECOVERY_READY/DIAGNOSTIC_HOLD.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
