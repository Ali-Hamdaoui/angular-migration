# MT-001 — S3-F07 Authoritative Manual Scenario

## Metadata

- Goal: `G03`
- Feature/Jira: `S3-F07` / `AMFA-146`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/03-angular-transform-review`

## User-observable outcome

A user can run the exact approved Angular core/CLI update for one stage and see the target exact version verified against package manifest, lockfile, dependency tree, and local CLI evidence.

## Exact backlog manual scenario

**Preconditions:** S3-F06; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Angular update step with exact versions/argv, live logs, migration list, prompt blocker, and target verification matrix.**.
3. Trigger the primary action for **Execute the exact Angular update and verify the target version** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can run the exact approved Angular core/CLI update for one stage and see the target exact version verified against package manifest, lockfile, dependency tree, and local CLI evidence. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Step/command results, version verification metadata, state/events.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/angular-update; GET /api/v1/runs/{id}/stages/{stageId}/target-version` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Exact update command/logs, migration output, target-version report, package/lockfile/dependency evidence, and prompt evidence if interrupted.

**Expected durable event:** ANGULAR_UPDATE_STARTED/COMPLETED/FAILED, INTERACTIVE_DECISION_REQUIRED, TARGET_VERSION_VERIFIED/FAILED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
