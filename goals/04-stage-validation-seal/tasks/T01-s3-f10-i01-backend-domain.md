# Task 01 — S3-F10-I01 — Implement backend application contract for Run final clean install and deterministic static checks

## Identity

- Capability goal: `G04`
- Backlog feature: `S3-F10` / `AMFA-149`
- Jira subtask: `AMFA-190`
- Source contract SHA-256: `b8ae99c05749d45f92b316f1123add6bca79f190acb9ba066bec2e7ccf9a3f91`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F10-I01 — Implement backend application contract for Run final clean install and deterministic static checks

  - **Parent feature:** S3-F10
  - **Issue type:** Validation
  - **Technical story:** Implement the bounded backend/application behavior for Run final clean install and deterministic static checks so the feature has one authoritative service path.
  - **Context:** Transformation acceptance does not prove reproducibility or source validity; validation must begin from a clean dependency boundary.
  - **Scope:** ValidationService install/static boundary, cleanup of node_modules/generated state, approved final npm-ci command, TypeScript/Angular template/import check adapters, result aggregation, and failure evidence hook.
  - **Out of scope:** Builds, tests/lint, route/backend comparison, LLM repair, and G09.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/validation/install-static; GET /api/v1/runs/{id}/stages/{stageId}/validation/install-static`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: ValidationService install/static boundary, cleanup of node_modules/generated state, approved final npm-ci command, TypeScript/Angular template/import check adapters, result aggregation, and failure evidence hook.
  - **Database impact:** Use or introduce the records summarized by: Validation step results, command records, diagnostics, artifact references.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/validation/install-static; GET /api/v1/runs/{id}/stages/{stageId}/validation/install-static
  - **Event impact:** Request durable events only through the transition/event service: VALIDATION_FINAL_INSTALL_* and STATIC_CHECKS_*.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Final install logs/result, static diagnostic reports, exact dependency tree evidence, and validation summary fragment.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Stale node_modules, check command not representative, phantom API false negative, command interruption, hidden generated state, and wrong validation profile.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's validation behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F09
  - **Suggested labels:** sprint-3, s3-f10, validation-capability, validation, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/01-S3-F10-I01.json`.
- Task completion requires reviewer verdict `PASS`.
