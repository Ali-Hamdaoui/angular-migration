# Task 07 — S4-F02-I03 — Build frontend experience for Route failures with C-Lite and show environment or retry actions

## Identity

- Capability goal: `G05`
- Backlog feature: `S4-F02` / `AMFA-212`
- Jira subtask: `AMFA-232`
- Source contract SHA-256: `d348cb356f74ced5f09c93881db93c736ac0f9e53a004f32c421419692dd175d`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F02-I03 — Build frontend experience for Route failures with C-Lite and show environment or retry actions

  - **Parent feature:** S4-F02
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Route failures with C-Lite and show environment or retry actions, using backend snapshots and durable events only.
  - **Context:** Deterministic top-level routing prevents wasted LLM calls and unsafe source changes for proxy, certificate, disk, permission, or runtime failures.
  - **Scope:** Failure route card with explanation, confidence, approved action buttons, environment checklist, retry progress, and no-patch notice.
  - **Out of scope:** Automated environment repair, LLM repair execution, unlimited retries, and changing source for auth/proxy errors.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry` plus durable events `FAILURE_CLASSIFIED, ENVIRONMENT_ACTION_REQUIRED, EXTERNAL_RETRY_SCHEDULED, DIAGNOSTIC_HOLD_ENTERED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Failure route card with explanation, confidence, approved action buttons, environment checklist, retry progress, and no-patch notice.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `FAILURE_CLASSIFIED, ENVIRONMENT_ACTION_REQUIRED, EXTERNAL_RETRY_SCHEDULED, DIAGNOSTIC_HOLD_ENTERED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Classification decision, rule evidence, remediation checklist, and retry outcome.
  - **UI impact:** Implement: Failure route card with explanation, confidence, approved action buttons, environment checklist, retry progress, and no-patch notice.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F02-I02
  - **Suggested labels:** sprint-4, s4-f02, repair-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/07-S4-F02-I03.json`.
- Task completion requires reviewer verdict `PASS`.
