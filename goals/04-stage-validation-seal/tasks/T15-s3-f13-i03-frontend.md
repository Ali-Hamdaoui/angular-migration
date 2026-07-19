# Task 15 — S3-F13-I03 — Build frontend experience for Compare parity evidence, display assurance, and decide G09 validation acceptance

## Identity

- Capability goal: `G04`
- Backlog feature: `S3-F13` / `AMFA-152`
- Jira subtask: `AMFA-204`
- Source contract SHA-256: `866321fb67f56ddbf5fe6b32bd6f50232bfc630ab06ba75ad7030ade817a6030`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F13-I03 — Build frontend experience for Compare parity evidence, display assurance, and decide G09 validation acceptance

  - **Parent feature:** S3-F13
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Compare parity evidence, display assurance, and decide G09 validation acceptance, using backend snapshots and durable events only.
  - **Context:** Stage validation combines machine gates and honest parity evidence; technical success remains separate from functional, security, and quality assurance.
  - **Scope:** Validation review page with gate matrix, route/API deltas, independent assurance cards, proof labels, manual/deferred items, and G09 controls.
  - **Out of scope:** Automated browser/visual proof, repair flow, stage sealing, and external security/quality scans.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions` plus durable events `PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Validation review page with gate matrix, route/API deltas, independent assurance cards, proof labels, manual/deferred items, and G09 controls.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Route comparison, backend-integration comparison, changed-risk rollup, parity checklist, assurance summary, and G09 package.
  - **UI impact:** Implement: Validation review page with gate matrix, route/API deltas, independent assurance cards, proof labels, manual/deferred items, and G09 controls.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G09 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F13-I02
  - **Suggested labels:** sprint-3, s3-f13, approval-capability, frontend, g09, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/15-S3-F13-I03.json`.
- Task completion requires reviewer verdict `PASS`.
