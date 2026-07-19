# MT-003 — S3-F12 Authoritative Manual Scenario

## Metadata

- Goal: `G04`
- Feature/Jira: `S3-F12` / `AMFA-151`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/04-stage-validation-seal`

## User-observable outcome

A reviewer can run the complete configured required test suite and lint, compare failures to baseline fingerprints, and see qualified or failed outcomes without weakening tests.

## Exact backlog manual scenario

**Preconditions:** S3-F11; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Tests/lint panel with full-suite proof, baseline/new/resolved grouping, not-configured state, test-change warnings, and logs.**.
3. Trigger the primary action for **Run complete stage tests and conditional lint** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can run the complete configured required test suite and lint, compare failures to baseline fingerprints, and see qualified or failed outcomes without weakening tests. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Command results, comparison results, step statuses, diagnostics and artifacts.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Full test/lint logs, structured results, baseline comparison, test-file change report, and known-failure delta.

**Expected durable event:** STAGE_TESTS_* and STAGE_LINT_* events.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
