# MT-003 — S4-F06 Authoritative Manual Scenario

## Metadata

- Goal: `G06`
- Feature/Jira: `S4-F06` / `AMFA-216`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/06-repair-agents-g10`

## User-observable outcome

A human can inspect the exact accepted Proposer diff and Reviewer decision, then Apply or Reject G10; the decision is bound to proposal checksum, state, plan, and workspace fingerprint.

## Exact backlog manual scenario

**Preconditions:** S4-F05; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Repair approval page with read-only diff, failure/context/proposer/reviewer timeline, checksum/fingerprint, risk warnings, Apply/Reject controls, and stale-state message.**.
    3. Trigger the primary action for **Persist an accepted proposal and decide G10 Apply or Reject** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G10** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A human can inspect the exact accepted Proposer diff and Reviewer decision, then Apply or Reject G10; the decision is bound to proposal checksum, state, plan, and workspace fingerprint. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `repair_proposals, proposal status/checksum, gate binding, decisions, lineage and events.` are retrievable through `GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Exact immutable accepted diff, proposal manifest, Reviewer decision, lineage/provenance, risk report, and G10 package.

    **Expected durable event:** REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G10 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

    **Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
