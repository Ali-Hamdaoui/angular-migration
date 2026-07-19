# Task 03 — S4-F12-I03 — Build frontend experience for Run independent final assurance and decide G13

## Identity

- Capability goal: `G09`
- Backlog feature: `S4-F12` / `AMFA-222`
- Jira subtask: `AMFA-272`
- Source contract SHA-256: `4d015f411db4fc5d326e2fb1fd043a85292168258cb755ee0524b537517ddd0f`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F12-I03 — Build frontend experience for Run independent final assurance and decide G13

  - **Parent feature:** S4-F12
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Run independent final assurance and decide G13, using backend snapshots and durable events only.
  - **Context:** Stage-local success is insufficient for delivery; the final candidate must be proven in a clean independent workspace.
  - **Scope:** Final assurance page with clean-workspace evidence, gate matrix, independent technical/parity/security/quality/delivery cards, manual/deferred items, source integrity, and G13 controls.
  - **Out of scope:** Automated browser/visual tooling, external security/quality tools, delivery publication, and report acceptance.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions` plus durable events `FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Final assurance page with clean-workspace evidence, gate matrix, independent technical/parity/security/quality/delivery cards, manual/deferred items, source integrity, and G13 controls.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.
  - **UI impact:** Implement: Final assurance page with clean-workspace evidence, gate matrix, independent technical/parity/security/quality/delivery cards, manual/deferred items, source integrity, and G13 controls.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G13 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F12-I02
  - **Suggested labels:** sprint-4, s4-f12, approval-capability, frontend, g13, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/03-S4-F12-I03.json`.
- Task completion requires reviewer verdict `PASS`.
