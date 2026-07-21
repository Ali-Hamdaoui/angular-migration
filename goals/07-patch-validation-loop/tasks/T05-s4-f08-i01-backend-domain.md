# Task 05 — S4-F08-I01 — Implement backend application contract for Run patch preflight, resume normal validation, and decide G11

## Identity

- Capability goal: `G07`
- Backlog feature: `S4-F08` / `AMFA-218`
- Jira subtask: `AMFA-254`
- Source contract SHA-256: `4e149be63da8c94e7378228db2d3808818aa5ac85e1263e5b03cbfdb01aa1b28`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F08-I01 — Implement backend application contract for Run patch preflight, resume normal validation, and decide G11

  - **Parent feature:** S4-F08
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Run patch preflight, resume normal validation, and decide G11 so the feature has one authoritative service path.
  - **Context:** Patch preflight is fast feedback only; the repair must use the same ExecutionProfile and normal stage pipeline.
  - **Scope:** PatchPreflightValidator, invalidation-boundary resolver, StageValidation resume command, same-profile/plan enforcement, error-delta calculator, G11 package, and fresh-failure hook.
  - **Out of scope:** No-progress policy across multiple attempts, startup recovery, final assurance, and stage auto-completion.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G11 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/validate; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/validation; POST /api/v1/runs/{id}/approvals/G11/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: PatchPreflightValidator, invalidation-boundary resolver, StageValidation resume command, same-profile/plan enforcement, error-delta calculator, G11 package, and fresh-failure hook.
  - **Database impact:** Use or introduce the records summarized by: Preflight results, validation rerun references, error delta, attempt outcome, gate/decision records.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/validate; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/validation; POST /api/v1/runs/{id}/approvals/G11/decisions
  - **Event impact:** Request durable events only through the transition/event service: PATCH_PREFLIGHT_COMPLETED, REPAIR_VALIDATION_STARTED/COMPLETED/FAILED and G11 events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Patch preflight report, invalidation decision, rerun logs/results, error delta, repair validation summary, and G11 package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Treating preflight as pass, skipping invalidated install/build/test, wrong profile, stale prior evidence, approval bypassing failed build, and failure evidence reuse.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G11 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F07, S3-F13
  - **Suggested labels:** sprint-4, s4-f08, approval-capability, backend, g11, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/05-S4-F08-I01.json`.
- Task completion requires reviewer verdict `PASS`.
