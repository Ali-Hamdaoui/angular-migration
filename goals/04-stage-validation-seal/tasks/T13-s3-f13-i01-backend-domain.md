# Task 13 — S3-F13-I01 — Implement backend application contract for Compare parity evidence, display assurance, and decide G09 validation acceptance

## Identity

- Capability goal: `G04`
- Backlog feature: `S3-F13` / `AMFA-152`
- Jira subtask: `AMFA-202`
- Source contract SHA-256: `bb263cfc3852385cf88cc1fb101ed3e78e674fc0b7bddad375cbc228b3d79b63`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F13-I01 — Implement backend application contract for Compare parity evidence, display assurance, and decide G09 validation acceptance

  - **Parent feature:** S3-F13
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Compare parity evidence, display assurance, and decide G09 validation acceptance so the feature has one authoritative service path.
  - **Context:** Stage validation combines machine gates and honest parity evidence; technical success remains separate from functional, security, and quality assurance.
  - **Scope:** RouteComparisonService, BackendIntegrationComparisonService, AssuranceAggregator, validation summary, core-gate prerequisite policy, G09 package, and Transition Service.
  - **Out of scope:** Automated browser/visual proof, repair flow, stage sealing, and external security/quality scans.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G09 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: RouteComparisonService, BackendIntegrationComparisonService, AssuranceAggregator, validation summary, core-gate prerequisite policy, G09 package, and Transition Service.
  - **Database impact:** Use or introduce the records summarized by: Assurance dimension records, comparison summaries, gate/decisions, events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions
  - **Event impact:** Request durable events only through the transition/event service: PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Route comparison, backend-integration comparison, changed-risk rollup, parity checklist, assurance summary, and G09 package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Dynamic behavior not proven, manual item shown as pass, core failure bypass, stale comparison, accepted difference without evidence, and route parser mismatch.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G09 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F10, S3-F11, S3-F12
  - **Suggested labels:** sprint-3, s3-f13, approval-capability, backend, g09, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/13-S3-F13-I01.json`.
- Task completion requires reviewer verdict `PASS`.
