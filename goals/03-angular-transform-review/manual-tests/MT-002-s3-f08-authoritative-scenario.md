# MT-002 — S3-F08 Authoritative Manual Scenario

## Metadata

- Goal: `G03`
- Feature/Jira: `S3-F08` / `AMFA-147`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/03-angular-transform-review`

## User-observable outcome

A reviewer can inspect complete package/lockfile/source/config diffs, changed Angular migrations, content-aware risk, and forbidden-modernization findings.

## Exact backlog manual scenario

**Preconditions:** S3-F07; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Custom unified diff viewer with file tree, risk filters, package/source tabs, sensitive changes, large-diff handling, and blocked findings.**.
3. Trigger the primary action for **Capture transformation diffs and classify changed-file risk** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can inspect complete package/lockfile/source/config diffs, changed Angular migrations, content-aware risk, and forbidden-modernization findings. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Transformation summary/risk metadata and artifact references.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Complete unified diff, package/lockfile diff, migration list, changed-file inventory, risk report, forbidden-change report.

**Expected durable event:** TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
