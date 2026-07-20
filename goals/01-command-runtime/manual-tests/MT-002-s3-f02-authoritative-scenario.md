# MT-002 — S3-F02 Authoritative Manual Scenario

## Metadata

- Goal: `G01`
- Feature/Jira: `S3-F02` / `AMFA-141`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/01-command-runtime`

## User-observable outcome

A user can run one harmless approved diagnostic command inspect exact executable, argv, profile, working directory, timestamps, exit code, and immutable stdout/stderr evidence.

## Exact backlog manual scenario

**Preconditions:** S3-F01; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Command detail drawer with exact authorized command, lifecycle, evidence links, loading/running/success/failure states.**.
3. Trigger the primary action for **Execute one approved command and persist authoritative command evidence** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can run one harmless approved diagnostic command inspect exact executable, argv, profile, working directory, timestamps, exit code, and immutable stdout/stderr evidence. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** First obtain an accepted authorization decision. Submit only `authorization_decision_id`, `expected_state_version`, `idempotency_key`, and optional `requested_by` to `POST /api/v1/runs/{id}/commands`; retrieve the authoritative record with `GET /api/v1/runs/{id}/commands/{commandId}`. The backend reloads the approved executable, arguments, profile, workspace, and shell policy.

**Expected artifact:** Command manifest, full stdout, full stderr, combined ordered stream where available, and result report.

**Expected durable event:** COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.

## Finalization Task 2 execution record

- Automated frontend gates: PASS — typecheck, lint, 38 test files/104 tests, and production build.
- Backend collection: PASS — 476 tests collected from `backend` without import errors.
- Focused execution backend tests: PASS — 21 tests in `test_command_execution.py` and `test_command_execution_task2.py`.
- Browser happy path: BLOCKED — no supported browser/manual runtime was available; no screenshots, API captures, execution IDs, or artifact IDs are claimed.
- Browser negative path: BLOCKED for the same reason.
- Overall manual verdict: `BLOCKED` until MT-002 and one negative case are executed in the supported runtime.
