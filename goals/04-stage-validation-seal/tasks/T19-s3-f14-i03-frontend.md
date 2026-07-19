# Task 19 — S3-F14-I03 — Build frontend experience for Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21

## Identity

- Capability goal: `G04`
- Backlog feature: `S3-F14` / `AMFA-153`
- Jira subtask: `AMFA-208`
- Source contract SHA-256: `8eeefa57196abe558dcfac13f4aa0f9e52e0630c0269b6af48bf4b2f87b5663a`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F14-I03 — Build frontend experience for Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21

  - **Parent feature:** S3-F14
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21, using backend snapshots and durable events only.
  - **Context:** Stage completion and copy-forward are separate trusted boundaries. The engine must use actual prior-stage output and finalize exact versions before each new stage.
  - **Scope:** Stage completion review, cleanliness/fingerprint cards, G12 controls, copy-forward progress, three-stage timeline, and stage-specific state/log/artifact navigation.
  - **Out of scope:** LLM repair, final clean assurance, delivery, and startup crash recovery.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward` plus durable events `STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Stage completion review, cleanliness/fingerprint cards, G12 controls, copy-forward progress, three-stage timeline, and stage-specific state/log/artifact navigation.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.
  - **UI impact:** Implement: Stage completion review, cleanliness/fingerprint cards, G12 controls, copy-forward progress, three-stage timeline, and stage-specific state/log/artifact navigation.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G12 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F14-I02
  - **Suggested labels:** sprint-3, s3-f14, approval-capability, frontend, g12, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/19-S3-F14-I03.json`.
- Task completion requires reviewer verdict `PASS`.
