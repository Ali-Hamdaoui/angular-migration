# MT-002 — S3-F11 Authoritative Manual Scenario

## Metadata

- Goal: `G04`
- Feature/Jira: `S3-F11` / `AMFA-150`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/04-stage-validation-seal`

## User-observable outcome

A reviewer can execute all approved required build targets for the stage and inspect per-target compilation evidence and failure diagnostics.

## Exact backlog manual scenario

**Preconditions:** S3-F10; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Build matrix with project/configuration, mandatory/conditional labels, progress, diagnostic drill-down, and immutable evidence links.**.
3. Trigger the primary action for **Run and inspect the required stage build matrix** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can execute all approved required build targets for the stage and inspect per-target compilation evidence and failure diagnostics. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Per-target statuses, command records, diagnostics, artifact references.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/validation/builds; GET /api/v1/runs/{id}/stages/{stageId}/validation/builds` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Build matrix, full logs, compiler diagnostics, output manifest/budget evidence where configured.

**Expected durable event:** STAGE_BUILD_STARTED/TARGET_COMPLETED/COMPLETED/FAILED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
