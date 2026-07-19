# Task 01 — S4-F12-I01 — Implement backend application contract for Run independent final assurance and decide G13

## Identity

- Capability goal: `G09`
- Backlog feature: `S4-F12` / `AMFA-222`
- Jira subtask: `AMFA-270`
- Source contract SHA-256: `174fc93aaee6ee3160a099810205834fb5a6faef4e6308475058beb591e95bb8`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F12-I01 — Implement backend application contract for Run independent final assurance and decide G13

  - **Parent feature:** S4-F12
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Run independent final assurance and decide G13 so the feature has one authoritative service path.
  - **Context:** Stage-local success is insufficient for delivery; the final candidate must be proven in a clean independent workspace.
  - **Scope:** FinalAssuranceService, WorkspaceManager final sandbox, exact frozen profile/plan, clean install/version/build/test/conditional checks, route/backend comparison, source integrity verification, assurance aggregation, and G13 package.
  - **Out of scope:** Automated browser/visual tooling, external security/quality tools, delivery publication, and report acceptance.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G13 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: FinalAssuranceService, WorkspaceManager final sandbox, exact frozen profile/plan, clean install/version/build/test/conditional checks, route/backend comparison, source integrity verification, assurance aggregation, and G13 package.
  - **Database impact:** Use or introduce the records summarized by: Final assurance metadata/results, source integrity status, gate/decisions, artifacts/events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions
  - **Event impact:** Request durable events only through the transition/event service: FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Reusing stage node_modules, final profile drift, incomplete project matrix, manual status shown as pass, source changed since snapshot, and final gate bypass.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G13 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F14, S4-F08, S4-F10
  - **Suggested labels:** sprint-4, s4-f12, approval-capability, backend, g13, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/01-S4-F12-I01.json`.
- Task completion requires reviewer verdict `PASS`.
