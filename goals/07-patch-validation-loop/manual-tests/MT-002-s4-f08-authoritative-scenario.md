# MT-002 — S4-F08 Authoritative Manual Scenario

## Metadata

- Goal: `G07`
- Feature/Jira: `S4-F08` / `AMFA-218`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/07-patch-validation-loop`

## User-observable outcome

A reviewer can see deterministic patch preflight, the earliest invalidated normal validation boundary, full rerun evidence, error delta, and decide G11 repair validation acceptance.

## Exact backlog manual scenario

**Preconditions:** S4-F07, S3-F13; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Repair validation timeline showing preflight versus authoritative gates, profile/plan match, rerun evidence, delta, fresh failure link, and G11 controls.**.
    3. Trigger the primary action for **Run patch preflight, resume normal validation, and decide G11** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G11** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can see deterministic patch preflight, the earliest invalidated normal validation boundary, full rerun evidence, error delta, and decide G11 repair validation acceptance. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `Preflight results, validation rerun references, error delta, attempt outcome, gate/decision records.` are retrievable through `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/validate; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/validation; POST /api/v1/runs/{id}/approvals/G11/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Patch preflight report, invalidation decision, rerun logs/results, error delta, repair validation summary, and G11 package.

    **Expected durable event:** PATCH_PREFLIGHT_COMPLETED, REPAIR_VALIDATION_STARTED/COMPLETED/FAILED and G11 events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G11 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

    **Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
