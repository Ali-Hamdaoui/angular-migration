# Task 07 — S3-F08-I03 — Build frontend experience for Capture transformation diffs and classify changed-file risk

## Identity

- Capability goal: `G03`
- Backlog feature: `S3-F08` / `AMFA-147`
- Jira subtask: `AMFA-184`
- Source contract SHA-256: `3c81123fb3287f6f57f2c8e1468ec3181c747a947f022ef90d8bc04c466fea01`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F08-I03 — Build frontend experience for Capture transformation diffs and classify changed-file risk

  - **Parent feature:** S3-F08
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Capture transformation diffs and classify changed-file risk, using backend snapshots and durable events only.
  - **Context:** Official tooling can produce behavior-sensitive or optional changes; the transformation must be reviewable before acceptance.
  - **Scope:** Custom unified diff viewer with file tree, risk filters, package/source tabs, sensitive changes, large-diff handling, and blocked findings.
  - **Out of scope:** Approving G08, editing diff, applying repair patches, and runtime parity proof.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence` plus durable events `TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Custom unified diff viewer with file tree, risk filters, package/source tabs, sensitive changes, large-diff handling, and blocked findings.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Complete unified diff, package/lockfile diff, migration list, changed-file inventory, risk report, forbidden-change report.
  - **UI impact:** Implement: Custom unified diff viewer with file tree, risk filters, package/source tabs, sensitive changes, large-diff handling, and blocked findings.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F08-I02
  - **Suggested labels:** sprint-3, s3-f08, validation-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/07-S3-F08-I03.json`.
- Task completion requires reviewer verdict `PASS`.
