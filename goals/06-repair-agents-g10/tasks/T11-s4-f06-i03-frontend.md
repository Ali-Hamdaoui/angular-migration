# Task 11 — S4-F06-I03 — Build frontend experience for Persist an accepted proposal and decide G10 Apply or Reject

## Identity

- Capability goal: `G06`
- Backlog feature: `S4-F06` / `AMFA-216`
- Jira subtask: `AMFA-248`
- Source contract SHA-256: `45b5d65a75d3adf6723bdf379482827b5c687ce6ff4c9cf84829c71667991ea8`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F06-I03 — Build frontend experience for Persist an accepted proposal and decide G10 Apply or Reject

  - **Parent feature:** S4-F06
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Persist an accepted proposal and decide G10 Apply or Reject, using backend snapshots and durable events only.
  - **Context:** LLM acceptance is advisory. Human authorization is mandatory before any repair mutation.
  - **Scope:** Repair approval page with read-only diff, failure/context/proposer/reviewer timeline, checksum/fingerprint, risk warnings, Apply/Reject controls, and stale-state message.
  - **Out of scope:** Patch dry run/application, modifying proposal in UI, auto-apply, and repair validation.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions` plus durable events `REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Repair approval page with read-only diff, failure/context/proposer/reviewer timeline, checksum/fingerprint, risk warnings, Apply/Reject controls, and stale-state message.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Exact immutable accepted diff, proposal manifest, Reviewer decision, lineage/provenance, risk report, and G10 package.
  - **UI impact:** Implement: Repair approval page with read-only diff, failure/context/proposer/reviewer timeline, checksum/fingerprint, risk warnings, Apply/Reject controls, and stale-state message.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G10 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F06-I02
  - **Suggested labels:** sprint-4, s4-f06, approval-capability, frontend, g10, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/11-S4-F06-I03.json`.
- Task completion requires reviewer verdict `PASS`.
