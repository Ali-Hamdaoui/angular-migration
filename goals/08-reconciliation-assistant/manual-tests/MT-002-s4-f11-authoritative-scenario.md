# MT-002 — S4-F11 Authoritative Manual Scenario

## Metadata

- Goal: `G08`
- Feature/Jira: `S4-F11` / `AMFA-221`
- Commit SHA: record at execution
- Runtime root: `/home/ubuntu/amfa-runtime/08-reconciliation-assistant`

## User-observable outcome

A user can ask what is happening, why approval is needed, what failed or changed, which evidence exists, and token/cost usage; answers cite approved state/artifacts and cannot execute or approve.

## Exact backlog manual scenario

**Preconditions:** S2-F03, S4-F10; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Chat panel with suggested questions, evidence links, proof labels, streaming/progress, empty/error/budget-blocked states, and disabled mutation/approval actions.**.
3. Trigger the primary action for **Explain authoritative migration state through the AI Assistant** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can ask what is happening, why approval is needed, what failed or changed, which evidence exists, and token/cost usage; answers cite approved state/artifacts and cannot execute or approve. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Conversation/message metadata, artifact refs, usage/cost; no hidden chain-of-thought.` are retrievable through `POST /api/v1/runs/{id}/assistant/messages; GET /api/v1/runs/{id}/assistant/messages` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Sanitized assistant input manifest, structured answer, evidence citations, and usage record.

**Expected durable event:** ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

## Required evidence

Record preconditions, external fixture identity/fingerprints, exact UI/API steps, expected/actual result, DB records/state version, durable event sequence, artifact IDs/checksums, screenshots/trace/network/SSE/log evidence, source-integrity proof, cleanup, defects, and PASS/FAIL/BLOCKED.
