# Task 05 — S4-F02-I01 — Implement backend application contract for Route failures with C-Lite and show environment or retry actions

## Identity

- Capability goal: `G05`
- Backlog feature: `S4-F02` / `AMFA-212`
- Jira subtask: `AMFA-230`
- Source contract SHA-256: `884d6d72e5ee81d41da94e420d83aed389f84bb491ae78e7dd8332802f63aeb9`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F02-I01 — Implement backend application contract for Route failures with C-Lite and show environment or retry actions

  - **Parent feature:** S4-F02
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Route failures with C-Lite and show environment or retry actions so the feature has one authoritative service path.
  - **Context:** Deterministic top-level routing prevents wasted LLM calls and unsafe source changes for proxy, certificate, disk, permission, or runtime failures.
  - **Scope:** CLiteRouter, rule/confidence model, environment remediation checklist builder, retry policy, diagnostic-hold transition, semantic-attempt accounting exclusions, and safe rerun authorization.
  - **Out of scope:** Automated environment repair, LLM repair execution, unlimited retries, and changing source for auth/proxy errors.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: CLiteRouter, rule/confidence model, environment remediation checklist builder, retry policy, diagnostic-hold transition, semantic-attempt accounting exclusions, and safe rerun authorization.
  - **Database impact:** Use or introduce the records summarized by: Route decision, confidence, policy version, action records, state/events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry
  - **Event impact:** Request durable events only through the transition/event service: FAILURE_CLASSIFIED, ENVIRONMENT_ACTION_REQUIRED, EXTERNAL_RETRY_SCHEDULED, DIAGNOSTIC_HOLD_ENTERED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Classification decision, rule evidence, remediation checklist, and retry outcome.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Misrouting dependency issue, retry storm, environment secrets, user action not revalidated, unknown treated as repairable, and semantic attempt wrongly consumed.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F01
  - **Suggested labels:** sprint-4, s4-f02, repair-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/05-S4-F02-I01.json`.
- Task completion requires reviewer verdict `PASS`.
