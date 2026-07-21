# MT-003 — S3-F09 Authoritative Manual Scenario

## Metadata

- Goal: `G03`
- Feature/Jira: `S3-F09` / `AMFA-148`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/03-angular-transform-review`

## User-observable outcome

A reviewer can approve, request modification, or reject the exact transformation artifact set; any workspace change makes the decision stale.

## Exact backlog manual scenario

**Preconditions:** S3-F08; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Transformation review workspace combining diff viewer, risk summary, comments, decision controls, stale warning, and failure/blocked states.**.
    3. Trigger the primary action for **Review and decide G08 transformation acceptance** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G08** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can approve, request modification, or reject the exact transformation artifact set; any workspace change makes the decision stale. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `Gate version, evidence checksum, fingerprint, decisions, transition/event records.` are retrievable through `GET /api/v1/runs/{id}/approvals/G08; POST /api/v1/runs/{id}/approvals/G08/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** G08 package referencing all transformation and risk artifacts.

    **Expected durable event:** APPROVAL_GATE_CREATED and G08 decision/stale events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G08 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

    **Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
