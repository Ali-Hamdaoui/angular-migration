# MT-001 — S4-F12 Authoritative Manual Scenario

## Metadata

- Goal: `G09`
- Feature/Jira: `S4-F12` / `AMFA-222`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/09-assurance-delivery-report`

## User-observable outcome

A reviewer can create a fresh final-assurance sandbox, run exact clean install/version/build/tests/conditional checks, inspect independent assurance dimensions and source integrity, then decide G13.

## Exact backlog manual scenario

**Preconditions:** S3-F14, S4-F08, S4-F10; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Final assurance page with clean-workspace evidence, gate matrix, independent technical/parity/security/quality/delivery cards, manual/deferred items, source integrity, and G13 controls.**.
    3. Trigger the primary action for **Run independent final assurance and decide G13** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G13** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can create a fresh final-assurance sandbox, run exact clean install/version/build/tests/conditional checks, inspect independent assurance dimensions and source integrity, then decide G13. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `Final assurance metadata/results, source integrity status, gate/decisions, artifacts/events.` are retrievable through `POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.

    **Expected durable event:** FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G13 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

    **Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
