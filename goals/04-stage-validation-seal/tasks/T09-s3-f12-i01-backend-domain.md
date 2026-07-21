# Task 09 — S3-F12-I01 — Implement backend application contract for Run complete stage tests and conditional lint

## Identity

- Capability goal: `G04`
- Backlog feature: `S3-F12` / `AMFA-151`
- Jira subtask: `AMFA-198`
- Source contract SHA-256: `da41603d2e11bb1ba2838adb7a81f9a9854dd9911eddb3f67767cbad1d71a7ed`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F12-I01 — Implement backend application contract for Run complete stage tests and conditional lint

  - **Parent feature:** S3-F12
  - **Issue type:** Validation
  - **Technical story:** Implement the bounded backend/application behavior for Run complete stage tests and conditional lint so the feature has one authoritative service path.
  - **Context:** Full tests are required after each stage; lint is conditional but must be represented honestly.
  - **Scope:** ValidationService test/lint boundary, complete-suite command enforcement, baseline failure comparator, known-failure policy, test-change governance checks, and diagnostic normalization.
  - **Out of scope:** Disabling tests, assertion weakening, test-framework replacement, browser E2E, and repair.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: ValidationService test/lint boundary, complete-suite command enforcement, baseline failure comparator, known-failure policy, test-change governance checks, and diagnostic normalization.
  - **Database impact:** Use or introduce the records summarized by: Command results, comparison results, step statuses, diagnostics and artifacts.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality
  - **Event impact:** Request durable events only through the transition/event service: STAGE_TESTS_* and STAGE_LINT_* events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Full test/lint logs, structured results, baseline comparison, test-file change report, and known-failure delta.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Watch mode, flaky test, partial suite, changed expected values, hidden skipped tests, baseline fingerprint drift, and accepted risk misuse.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's validation behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F11
  - **Suggested labels:** sprint-3, s3-f12, validation-capability, validation, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/09-S3-F12-I01.json`.
- Task completion requires reviewer verdict `PASS`.
