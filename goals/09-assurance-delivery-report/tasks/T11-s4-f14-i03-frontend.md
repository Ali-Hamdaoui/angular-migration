# Task 11 — S4-F14-I03 — Build frontend experience for Generate, view, download, and accept the final evidence and cost report through G15

## Identity

- Capability goal: `G09`
- Backlog feature: `S4-F14` / `AMFA-224`
- Jira subtask: `AMFA-280`
- Source contract SHA-256: `6e337b8411eafefae6a2ece5cc297c22afef85cd2ea096d523ebcce8f2aec8f7`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F14-I03 — Build frontend experience for Generate, view, download, and accept the final evidence and cost report through G15

  - **Parent feature:** S4-F14
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Generate, view, download, and accept the final evidence and cost report through G15, using backend snapshots and durable events only.
  - **Context:** The report is an evidence index and honest assurance summary, not a narrative that invents unexecuted success.
  - **Scope:** Markdown report viewer with navigation, proof badges, approval timeline, artifact links, usage/cost table, unresolved items, download, and G15 controls.
  - **Out of scope:** PDF unless separately approved, hidden chain-of-thought, cached/reasoning token metrics, and claiming external scans passed.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions` plus durable events `REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Markdown report viewer with navigation, proof badges, approval timeline, artifact links, usage/cost table, unresolved items, download, and G15 controls.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.
  - **UI impact:** Implement: Markdown report viewer with navigation, proof badges, approval timeline, artifact links, usage/cost table, unresolved items, download, and G15 controls.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G15 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F14-I02
  - **Suggested labels:** sprint-4, s4-f14, reporting-capability, frontend, g15, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/11-S4-F14-I03.json`.
- Task completion requires reviewer verdict `PASS`.
