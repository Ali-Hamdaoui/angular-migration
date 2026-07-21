# MT-001 — S3-F01 Authoritative Manual Scenario

## Metadata

- Goal: `G01`
- Feature/Jira: `S3-F01` / `AMFA-140`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/01-command-runtime`

## User-observable outcome

An operator can inspect approved command templates and see raw shell strings, forbidden flags, invalid arguments, or out-of-scope workspaces rejected before execution.

## Exact backlog manual scenario

**Preconditions:** S2-F07; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Command policy inspector showing template, expanded argv preview, policy checks, rejection reasons, and no free-form shell field.**.
3. Trigger the primary action for **Register structured commands and reject arbitrary shell execution** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** An operator can inspect approved command templates and see raw shell strings, forbidden flags, invalid arguments, or out-of-scope workspaces rejected before execution. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Versioned command-template metadata and authorization audit records.` are retrievable through `GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Sanitized command authorization decision artifact for operator tests.

**Expected durable event:** COMMAND_AUTHORIZATION_ACCEPTED/REJECTED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
