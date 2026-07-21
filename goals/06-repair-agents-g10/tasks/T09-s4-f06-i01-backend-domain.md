# Task 09 — S4-F06-I01 — Implement backend application contract for Persist an accepted proposal and decide G10 Apply or Reject

## Identity

- Capability goal: `G06`
- Backlog feature: `S4-F06` / `AMFA-216`
- Jira subtask: `AMFA-246`
- Source contract SHA-256: `73ce8d38e0884cd4c35e76b716e08b1f5d8d4982a3c005b8a45c9dbc0fe79a84`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F06-I01 — Implement backend application contract for Persist an accepted proposal and decide G10 Apply or Reject

  - **Parent feature:** S4-F06
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Persist an accepted proposal and decide G10 Apply or Reject so the feature has one authoritative service path.
  - **Context:** LLM acceptance is advisory. Human authorization is mandatory before any repair mutation.
  - **Scope:** RepairProposalService, exact diff persistence/checksum, pre-apply fingerprint, model/prompt/schema provenance, risk package, G10 gate, stale condition evaluation, and decision consequences.
  - **Out of scope:** Patch dry run/application, modifying proposal in UI, auto-apply, and repair validation.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G10 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: RepairProposalService, exact diff persistence/checksum, pre-apply fingerprint, model/prompt/schema provenance, risk package, G10 gate, stale condition evaluation, and decision consequences.
  - **Database impact:** Use or introduce the records summarized by: repair_proposals, proposal status/checksum, gate binding, decisions, lineage and events.
  - **API impact:** Define service-facing request/response models supporting: GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions
  - **Event impact:** Request durable events only through the transition/event service: REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Exact immutable accepted diff, proposal manifest, Reviewer decision, lineage/provenance, risk report, and G10 package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Stale workspace, UI resubmitting altered diff, checksum mismatch, wrong attempt lineage, high-risk file approval, and double Apply.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G10 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F05
  - **Suggested labels:** sprint-4, s4-f06, approval-capability, backend, g10, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/09-S4-F06-I01.json`.
- Task completion requires reviewer verdict `PASS`.
