# Task 05 — S3-F11-I01 — Implement backend application contract for Run and inspect the required stage build matrix

## Identity

- Capability goal: `G04`
- Backlog feature: `S3-F11` / `AMFA-150`
- Jira subtask: `AMFA-194`
- Source contract SHA-256: `6fca2a980db170309ea211012f54a9751f85fa276f3cf09b5f1194fa79e6684c`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F11-I01 — Implement backend application contract for Run and inspect the required stage build matrix

  - **Parent feature:** S3-F11
  - **Issue type:** Validation
  - **Technical story:** Implement the bounded backend/application behavior for Run and inspect the required stage build matrix so the feature has one authoritative service path.
  - **Context:** Build is a mandatory core gate and cannot be changed to passed by human approval.
  - **Scope:** ValidationService build boundary, StageExecutionPlan target resolution, per-target command execution, result aggregation, output-path evidence, and failure parser hook.
  - **Out of scope:** Repair, unsupported custom-builder implementation, browser runtime tests, and G09.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/validation/builds; GET /api/v1/runs/{id}/stages/{stageId}/validation/builds`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: ValidationService build boundary, StageExecutionPlan target resolution, per-target command execution, result aggregation, output-path evidence, and failure parser hook.
  - **Database impact:** Use or introduce the records summarized by: Per-target statuses, command records, diagnostics, artifact references.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/validation/builds; GET /api/v1/runs/{id}/stages/{stageId}/validation/builds
  - **Event impact:** Request durable events only through the transition/event service: STAGE_BUILD_STARTED/TARGET_COMPLETED/COMPLETED/FAILED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Build matrix, full logs, compiler diagnostics, output manifest/budget evidence where configured.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Missing target, custom builder, output path change, memory exhaustion, conditional target silently skipped, and false pass from one project only.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's validation behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F10
  - **Suggested labels:** sprint-3, s3-f11, validation-capability, validation, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/05-S3-F11-I01.json`.
- Task completion requires reviewer verdict `PASS`.
