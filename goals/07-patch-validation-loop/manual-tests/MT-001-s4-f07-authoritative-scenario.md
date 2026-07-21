# MT-001 — S4-F07 Authoritative Manual Scenario

## Metadata

- Goal: `G07`
- Feature/Jira: `S4-F07` / `AMFA-217`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/07-patch-validation-loop`

## User-observable outcome

After G10 Apply, a user can see checksum/fingerprint/path/scope/applicability checks and either an exact successful patch application with ledger or a fail-closed rejection.

## Exact backlog manual scenario

**Preconditions:** S4-F06; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Apply progress/results panel listing every safety check, exact outcome, stale/path/applicability errors, and immutable ledger link.**.
3. Trigger the primary action for **Validate and apply only the exact persisted repair diff** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** After G10 Apply, a user can see checksum/fingerprint/path/scope/applicability checks and either an exact successful patch application with ledger or a fail-closed rejection. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Patch apply metadata/idempotency, ledger, post-fingerprint, command/transition events.` are retrievable through `POST /api/v1/runs/{id}/repair-proposals/{proposalId}/apply; GET /api/v1/runs/{id}/repair-proposals/{proposalId}/apply-result` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Patch safety report, dry-run result, exact applied diff reference, patch ledger, pre/post fingerprints, and failure evidence.

**Expected durable event:** REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
