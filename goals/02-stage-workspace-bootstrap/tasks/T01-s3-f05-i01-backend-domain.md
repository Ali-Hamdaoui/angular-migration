# Task 01 — S3-F05-I01 — Implement backend application contract for Prepare a dedicated run-scoped stage sandbox and decide G07 stage start

## Identity

- Capability goal: `G02`
- Backlog feature: `S3-F05` / `AMFA-144`
- Jira subtask: `AMFA-170`
- Source contract SHA-256: `a2ce6c0fd14589a9a2109201237a08380bf5fba309ccf58ce3e8d1bad29f5a65`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F05-I01 — Implement backend application contract for Prepare a dedicated run-scoped stage sandbox and decide G07 stage start

  - **Parent feature:** S3-F05
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Prepare a dedicated run-scoped stage sandbox and decide G07 stage start so the feature has one authoritative service path.
  - **Context:** Every major transition starts from an approved clean boundary and has its own physical workspace.
  - **Scope:** StagePreparationService, current-version re-detection, later-stage exact resolution hook, StageExecutionPlan lock, G07 package, WorkspaceManager stage-copy operation, fingerprint validation, and lease checks.
  - **Out of scope:** Bootstrap install, Angular update, stage validation, and copy-forward.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G07 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/prepare; POST /api/v1/runs/{id}/approvals/G07/decisions; POST /api/v1/runs/{id}/stages/{stageId}/sandbox`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: StagePreparationService, current-version re-detection, later-stage exact resolution hook, StageExecutionPlan lock, G07 package, WorkspaceManager stage-copy operation, fingerprint validation, and lease checks.
  - **Database impact:** Use or introduce the records summarized by: migration_stages, active stage plan, workspace/fingerprint records, gate decisions.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/prepare; POST /api/v1/runs/{id}/approvals/G07/decisions; POST /api/v1/runs/{id}/stages/{stageId}/sandbox
  - **Event impact:** Request durable events only through the transition/event service: STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Stage-start package, exact plan/profile, copy report, input manifest, input fingerprint, and sandbox verification.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Stale prior-stage output, plan drift, approval before fingerprint, sandbox collision, copy interruption, active lease conflict, and source link escape.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G07 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S2-F07, S3-F04
  - **Suggested labels:** sprint-3, s3-f05, approval-capability, backend, g07, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/01-S3-F05-I01.json`.
- Task completion requires reviewer verdict `PASS`.
