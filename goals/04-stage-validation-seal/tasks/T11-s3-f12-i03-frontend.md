# Task 11 — S3-F12-I03 — Build frontend experience for Run complete stage tests and conditional lint

## Identity

- Capability goal: `G04`
- Backlog feature: `S3-F12` / `AMFA-151`
- Jira subtask: `AMFA-200`
- Source contract SHA-256: `5a744e58a6097e0a44d6b544da8903000a9242da4d30c53d53dc0cb52d1db1d2`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F12-I03 — Build frontend experience for Run complete stage tests and conditional lint

  - **Parent feature:** S3-F12
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Run complete stage tests and conditional lint, using backend snapshots and durable events only.
  - **Context:** Full tests are required after each stage; lint is conditional but must be represented honestly.
  - **Scope:** Tests/lint panel with full-suite proof, baseline/new/resolved grouping, not-configured state, test-change warnings, and logs.
  - **Out of scope:** Disabling tests, assertion weakening, test-framework replacement, browser E2E, and repair.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality` plus durable events `STAGE_TESTS_* and STAGE_LINT_* events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Tests/lint panel with full-suite proof, baseline/new/resolved grouping, not-configured state, test-change warnings, and logs.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `STAGE_TESTS_* and STAGE_LINT_* events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Full test/lint logs, structured results, baseline comparison, test-file change report, and known-failure delta.
  - **UI impact:** Implement: Tests/lint panel with full-suite proof, baseline/new/resolved grouping, not-configured state, test-change warnings, and logs.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F12-I02
  - **Suggested labels:** sprint-3, s3-f12, validation-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/11-S3-F12-I03.json`.
- Task completion requires reviewer verdict `PASS`.
