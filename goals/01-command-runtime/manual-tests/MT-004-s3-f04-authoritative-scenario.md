# MT-004 — S3-F04 Authoritative Manual Scenario

## Metadata

- Goal: `G01`
- Feature/Jira: `S3-F04` / `AMFA-143`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/01-command-runtime`

## User-observable outcome

A user can cancel a controlled long-running command, see graceful then forced process-tree termination, partial evidence, and an honest interrupted/cancelled workspace classification.

## Exact backlog manual scenario

**Preconditions:** S3-F02, S3-F03; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Cancel action with confirmation, cancelling status, process result, partial evidence links, blocked duplicate action, and reconnect-safe state.**.
3. Trigger the primary action for **Own commands with JobSupervisor, leases, timeout, and explicit cancellation** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can cancel a controlled long-running command, see graceful then forced process-tree termination, partial evidence, and an honest interrupted/cancelled workspace classification. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `worker_leases, command cancellation metadata, run/step states, durable events.` are retrievable through `POST /api/v1/runs/{id}/cancel; GET /api/v1/runs/{id}/active-command` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Partial logs, process-termination report, workspace trust/recovery classification, and partial cancellation summary.

**Expected durable event:** RUN_CANCEL_REQUESTED, COMMAND_CANCELLED/INTERRUPTED, RUN_CANCELLED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
