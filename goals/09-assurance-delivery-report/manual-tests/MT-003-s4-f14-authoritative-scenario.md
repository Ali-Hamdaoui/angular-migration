# MT-003 — S4-F14 Authoritative Manual Scenario

## Metadata

- Goal: `G09`
- Feature/Jira: `S4-F14` / `AMFA-224`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/09-assurance-delivery-report`

## User-observable outcome

A lead can view/download a complete report covering stages, approvals, commands, failures, repairs, source integrity, delivery, proof labels, manual/deferred items, and input/output/total token costs, then decide G15.

## Exact backlog manual scenario

**Preconditions:** S4-F11, S4-F13; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Markdown report viewer with navigation, proof badges, approval timeline, artifact links, usage/cost table, unresolved items, download, and G15 controls.**.
    3. Trigger the primary action for **Generate, view, download, and accept the final evidence and cost report through G15** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G15** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A lead can view/download a complete report covering stages, approvals, commands, failures, repairs, source integrity, delivery, proof labels, manual/deferred items, and input/output/total token costs, then decide G15. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `Report metadata/version/checksum, aggregate usage/cost, gate decisions, completion transition.` are retrievable through `POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.

    **Expected durable event:** REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G15 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

    **Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
