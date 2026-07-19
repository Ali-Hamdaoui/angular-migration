# MT-003 — S4-F03 Authoritative Manual Scenario

## Metadata

- Goal: `G05`
- Feature/Jira: `S4-F03` / `AMFA-213`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/05-failure-diagnostics-context`

## User-observable outcome

A reviewer can see exactly which evidence excerpts and files will be model-visible, why each was selected, checksums, redactions, token budget, and forbidden capabilities.

## Exact backlog manual scenario

**Preconditions:** S4-F01, S4-F02; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Context inspector with selected files/excerpts, reasons, checksums, redaction indicators, budget meter, and blocked-sensitive-content state.**.
3. Trigger the primary action for **Build and inspect a bounded sanitized RepairContextPack** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can see exactly which evidence excerpts and files will be model-visible, why each was selected, checksums, redactions, token budget, and forbidden capabilities. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `repair_attempts, context-pack metadata, selection reasons, checksums, sanitizer record, artifact refs.` are retrievable through `POST /api/v1/runs/{id}/failures/{failureId}/repair-context; GET /api/v1/runs/{id}/repair-contexts/{contextId}` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Sanitized context pack, selection manifest, redaction report, token estimate, and forbidden-action policy.

**Expected durable event:** REPAIR_CONTEXT_CREATED or REPAIR_CONTEXT_BLOCKED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
