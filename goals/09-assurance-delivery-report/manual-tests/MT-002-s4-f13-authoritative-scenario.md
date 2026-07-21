# MT-002 — S4-F13 Authoritative Manual Scenario

## Metadata

- Goal: `G09`
- Feature/Jira: `S4-F13` / `AMFA-223`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/09-assurance-delivery-report`

## User-observable outcome

A reviewer can inspect the exact user-selected external output root, clean delivery manifest/fingerprint, original-source integrity proof, and destination safety, decide G14, and publish `<resolved-output-root>/migrated-app` atomically or fail closed without exposing a partial final directory.

## Exact backlog manual scenario

**Preconditions:** S4-F12; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Delivery review page with selected external output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.**.
    3. Trigger the primary action for **Create a delivery candidate and publish atomically through G14** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G14** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can inspect the exact user-selected external output root, clean delivery manifest/fingerprint, original-source integrity proof, and destination safety, decide G14, and publish `<resolved-output-root>/migrated-app` atomically or fail closed without exposing a partial final directory. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `delivery_records, output-root/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.` are retrievable through `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, output-root destination safety report, managed-output ownership report, G14 package, and publication record.

    **Expected durable event:** DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G14 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

    **Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
