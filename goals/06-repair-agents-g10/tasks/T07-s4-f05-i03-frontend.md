# Task 07 — S4-F05-I03 — Build frontend experience for Review a Proposer candidate with non-authoring Reviewer and bounded revision

## Identity

- Capability goal: `G06`
- Backlog feature: `S4-F05` / `AMFA-215`
- Jira subtask: `AMFA-244`
- Source contract SHA-256: `7104b27f8a1903cb0f5b705a3e58f06e5e42c7cefef374882eb8490b8922c9dd`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F05-I03 — Build frontend experience for Review a Proposer candidate with non-authoring Reviewer and bounded revision

  - **Parent feature:** S4-F05
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Review a Proposer candidate with non-authoring Reviewer and bounded revision, using backend snapshots and durable events only.
  - **Context:** Critique is separated from authorship to preserve lineage and prevent a hidden replacement patch.
  - **Scope:** Side-by-side Proposer/Reviewer view, decision badge, critique, revision timeline, context-expansion status, and explicit 'Reviewer never authors a diff' notice.
  - **Out of scope:** Human approval, patch application, unlimited review loops, and reviewer-edited patch.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions` plus durable events `REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Side-by-side Proposer/Reviewer view, decision badge, critique, revision timeline, context-expansion status, and explicit 'Reviewer never authors a diff' notice.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Reviewer structured response, critique/revision instructions, schema-validation evidence, revised Proposer candidate where applicable.
  - **UI impact:** Implement: Side-by-side Proposer/Reviewer view, decision badge, critique, revision timeline, context-expansion status, and explicit 'Reviewer never authors a diff' notice.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F05-I02
  - **Suggested labels:** sprint-4, s4-f05, repair-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/07-S4-F05-I03.json`.
- Task completion requires reviewer verdict `PASS`.
