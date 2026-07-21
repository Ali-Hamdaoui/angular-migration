# MT-005 — S3-F14 Authoritative Manual Scenario

## Metadata

- Goal: `G04`
- Feature/Jira: `S3-F14` / `AMFA-153`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/04-stage-validation-seal`

## User-observable outcome

A reviewer can clean and fingerprint an approved stage, decide G12, copy only its clean output into the next dedicated sandbox, and observe the same engine execute 18→19, 19→20, and 20→21 on a passing fixture.

## Exact backlog manual scenario

**Preconditions:** S3-F13; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Stage completion review, cleanliness/fingerprint cards, G12 controls, copy-forward progress, three-stage timeline, and stage-specific state/log/artifact navigation.**.
    3. Trigger the primary action for **Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G12** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can clean and fingerprint an approved stage, decide G12, copy only its clean output into the next dedicated sandbox, and observe the same engine execute 18→19, 19→20, and 20→21 on a passing fixture. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `Stage output records, fingerprints, gate decisions, next-stage sandbox records, transitions/events.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.

    **Expected durable event:** STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G12 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

    **Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
