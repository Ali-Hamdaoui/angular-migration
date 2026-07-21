# MT-004 — S3-F13 Authoritative Manual Scenario

## Metadata

- Goal: `G04`
- Feature/Jira: `S3-F13` / `AMFA-152`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/04-stage-validation-seal`

## User-observable outcome

A reviewer can inspect route/backend integration deltas, changed-file risk, technical/manual/deferred assurance dimensions, and decide G09 without converting failed core gates to pass.

## Exact backlog manual scenario

**Preconditions:** S3-F10, S3-F11, S3-F12; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Validation review page with gate matrix, route/API deltas, independent assurance cards, proof labels, manual/deferred items, and G09 controls.**.
    3. Trigger the primary action for **Compare parity evidence, display assurance, and decide G09 validation acceptance** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G09** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can inspect route/backend integration deltas, changed-file risk, technical/manual/deferred assurance dimensions, and decide G09 without converting failed core gates to pass. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `Assurance dimension records, comparison summaries, gate/decisions, events.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Route comparison, backend-integration comparison, changed-risk rollup, parity checklist, assurance summary, and G09 package.

    **Expected durable event:** PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G09 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

    **Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
