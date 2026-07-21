# Task 09 — S3-F09-I01 — Implement backend application contract for Review and decide G08 transformation acceptance

## Identity

- Capability goal: `G03`
- Backlog feature: `S3-F09` / `AMFA-148`
- Jira subtask: `AMFA-186`
- Source contract SHA-256: `fa17a95f1bfb6e801ba97e36b76b80213baa6e0cd3486687ed83c13656bf76e9`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F09-I01 — Implement backend application contract for Review and decide G08 transformation acceptance

  - **Parent feature:** S3-F09
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Review and decide G08 transformation acceptance so the feature has one authoritative service path.
  - **Context:** Human review is required before the stage crosses the transformation boundary, especially for high-risk files and builder behavior.
  - **Scope:** G08 EvidencePackageBuilder, artifact-set checksum, current workspace fingerprint binding, risk-dependent prerequisite checks, decision consequences, and Transition Service.
  - **Out of scope:** Changing the diff in UI, technical validation, repair, and stage completion.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G08 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `GET /api/v1/runs/{id}/approvals/G08; POST /api/v1/runs/{id}/approvals/G08/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: G08 EvidencePackageBuilder, artifact-set checksum, current workspace fingerprint binding, risk-dependent prerequisite checks, decision consequences, and Transition Service.
  - **Database impact:** Use or introduce the records summarized by: Gate version, evidence checksum, fingerprint, decisions, transition/event records.
  - **API impact:** Define service-facing request/response models supporting: GET /api/v1/runs/{id}/approvals/G08; POST /api/v1/runs/{id}/approvals/G08/decisions
  - **Event impact:** Request durable events only through the transition/event service: APPROVAL_GATE_CREATED and G08 decision/stale events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: G08 package referencing all transformation and risk artifacts.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Approving stale diff, artifact omission, high-risk change hidden by filter, modification request without new evidence version, and approval converting target mismatch into pass.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G08 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F08
  - **Suggested labels:** sprint-3, s3-f09, approval-capability, backend, g08, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/09-S3-F09-I01.json`.
- Task completion requires reviewer verdict `PASS`.
