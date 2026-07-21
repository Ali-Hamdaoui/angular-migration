# MT-001 — S3-F10 Authoritative Manual Scenario

## Metadata

- Goal: `G04`
- Feature/Jira: `S3-F10` / `AMFA-149`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/04-stage-validation-seal`

## User-observable outcome

A user can run a fresh final dependency install after G08 and inspect static TypeScript/template/import checks with precise pass, failure, not-configured, or blocked statuses.

## Exact backlog manual scenario

**Preconditions:** S3-F09; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Install/static validation panel with step timeline, diagnostics grouped by file/code, logs, retry/reconstruct guidance, and honest statuses.**.
3. Trigger the primary action for **Run final clean install and deterministic static checks** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can run a fresh final dependency install after G08 and inspect static TypeScript/template/import checks with precise pass, failure, not-configured, or blocked statuses. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Validation step results, command records, diagnostics, artifact references.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/validation/install-static; GET /api/v1/runs/{id}/stages/{stageId}/validation/install-static` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Final install logs/result, static diagnostic reports, exact dependency tree evidence, and validation summary fragment.

**Expected durable event:** VALIDATION_FINAL_INSTALL_* and STATIC_CHECKS_*.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
