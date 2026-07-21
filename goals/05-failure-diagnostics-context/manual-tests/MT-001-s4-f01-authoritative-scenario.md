# MT-001 — S4-F01 Authoritative Manual Scenario

## Metadata

- Goal: `G05`
- Feature/Jira: `S4-F01` / `AMFA-211`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/05-failure-diagnostics-context`

## User-observable outcome

A reviewer can open a failed command inspect immutable raw logs, normalized npm/Angular CLI/TypeScript/template/test/generic diagnostics, locations, fingerprints, and baseline origin.

## Exact backlog manual scenario

**Preconditions:** S3-F02, S3-F12; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **FailureEvidence viewer with raw/normalized tabs, code/file filters, baseline origin, fingerprint, parser confidence, and unknown state.**.
3. Trigger the primary action for **Capture FailureEvidence and parse deterministic diagnostics** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can open a failed command inspect immutable raw logs, normalized npm/Angular CLI/TypeScript/template/test/generic diagnostics, locations, fingerprints, and baseline origin. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `failures and failure_diagnostics metadata plus artifact references and transition events.` are retrievable through `POST /api/v1/runs/{id}/commands/{commandId}/failure-evidence; GET /api/v1/runs/{id}/failures/{failureId}` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Raw stdout/stderr references, structured FailureEvidence JSON, parser report, normalized diagnostics, and origin comparison.

**Expected durable event:** FAILURE_CAPTURED and FAILURE_DIAGNOSTICS_PARSED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
