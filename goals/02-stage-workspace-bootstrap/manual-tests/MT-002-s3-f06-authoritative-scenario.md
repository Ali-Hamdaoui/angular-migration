# MT-002 — S3-F06 Authoritative Manual Scenario

## Metadata

- Goal: `G02`
- Feature/Jira: `S3-F06` / `AMFA-145`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/02-stage-workspace-bootstrap`

## User-observable outcome

A user can run the exact approved bootstrap install in the run-scoped stage sandbox and inspect its command, environment, lifecycle-script audit binding, logs, and result.

## Exact backlog manual scenario

**Preconditions:** S3-F05; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Stage pipeline step card with approved command, progress/log link, result, environment blocker, retry/reconstruct guidance.**.
3. Trigger the primary action for **Run the stage bootstrap clean install** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can run the exact approved bootstrap install in the run-scoped stage sandbox and inspect its command, environment, lifecycle-script audit binding, logs, and result. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Step state, command execution, stage fingerprint references, and events.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/bootstrap-install; GET /api/v1/runs/{id}/stages/{stageId}/steps/bootstrap-install` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Install command/logs/result, pre/post workspace fingerprints, and package-manager debug artifacts.

**Expected durable event:** STAGE_BOOTSTRAP_INSTALL_STARTED/COMPLETED/FAILED plus command events.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
