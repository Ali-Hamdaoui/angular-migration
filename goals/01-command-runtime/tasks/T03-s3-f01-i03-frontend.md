# Task 03 — S3-F01-I03 — Build frontend experience for Register structured commands and reject arbitrary shell execution

## Identity

- Capability goal: `G01`
- Backlog feature: `S3-F01` / `AMFA-140`
- Jira subtask: `AMFA-156`
- Source contract SHA-256: `cbbbb441cc7f2c40c93758f5d99f3d25b1fdc47e8c1f3717962fd31ed55818d2`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F01-I03 — Build frontend experience for Register structured commands and reject arbitrary shell execution

  - **Parent feature:** S3-F01
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Register structured commands and reject arbitrary shell execution, using backend snapshots and durable events only.
  - **Context:** All execution must pass through a structured registry and policy engine; plans authorize command references, not arbitrary shell text.
  - **Scope:** Command policy inspector showing template, expanded argv preview, policy checks, rejection reasons, and no free-form shell field.
  - **Out of scope:** Starting processes, live logs, user-defined commands, PowerShell wrappers, and LLM command generation.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate` plus durable events `COMMAND_AUTHORIZATION_ACCEPTED/REJECTED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Command policy inspector showing template, expanded argv preview, policy checks, rejection reasons, and no free-form shell field.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `COMMAND_AUTHORIZATION_ACCEPTED/REJECTED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Sanitized command authorization decision artifact for operator tests.
  - **UI impact:** Implement: Command policy inspector showing template, expanded argv preview, policy checks, rejection reasons, and no free-form shell field.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F01-I02
  - **Suggested labels:** sprint-3, s3-f01, execution-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/03-S3-F01-I03.json`.
- Task completion requires reviewer verdict `PASS`.
