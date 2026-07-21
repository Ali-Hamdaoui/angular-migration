# Task 03 — S3-F07-I03 — Build frontend experience for Execute the exact Angular update and verify the target version

## Identity

- Capability goal: `G03`
- Backlog feature: `S3-F07` / `AMFA-146`
- Jira subtask: `AMFA-180`
- Source contract SHA-256: `b61d1aa51de2530feb5b44b1ae3de861c21e59463081018f6b11a832f145763a`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F07-I03 — Build frontend experience for Execute the exact Angular update and verify the target version

  - **Parent feature:** S3-F07
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Execute the exact Angular update and verify the target version, using backend snapshots and durable events only.
  - **Context:** Official Angular tooling is the first migration mechanism; success requires exact target proof, not only command exit zero.
  - **Scope:** Angular update step with exact versions/argv, live logs, migration list, prompt blocker, and target verification matrix.
  - **Out of scope:** LLM repair, optional Angular modernization migrations, and transformation approval.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/angular-update; GET /api/v1/runs/{id}/stages/{stageId}/target-version` plus durable events `ANGULAR_UPDATE_STARTED/COMPLETED/FAILED, INTERACTIVE_DECISION_REQUIRED, TARGET_VERSION_VERIFIED/FAILED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Angular update step with exact versions/argv, live logs, migration list, prompt blocker, and target verification matrix.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/angular-update; GET /api/v1/runs/{id}/stages/{stageId}/target-version` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `ANGULAR_UPDATE_STARTED/COMPLETED/FAILED, INTERACTIVE_DECISION_REQUIRED, TARGET_VERSION_VERIFIED/FAILED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Exact update command/logs, migration output, target-version report, package/lockfile/dependency evidence, and prompt evidence if interrupted.
  - **UI impact:** Implement: Angular update step with exact versions/argv, live logs, migration list, prompt blocker, and target verification matrix.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F07-I02
  - **Suggested labels:** sprint-3, s3-f07, execution-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/03-S3-F07-I03.json`.
- Task completion requires reviewer verdict `PASS`.
