# Task 05 — S4-F05-I01 — Implement backend application contract for Review a Proposer candidate with non-authoring Reviewer and bounded revision

## Identity

- Capability goal: `G06`
- Backlog feature: `S4-F05` / `AMFA-215`
- Jira subtask: `AMFA-242`
- Source contract SHA-256: `c8a470a809ce380a8ec631f289283e537f52e5d50f1615360a7db6115293010d`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F05-I01 — Implement backend application contract for Review a Proposer candidate with non-authoring Reviewer and bounded revision

  - **Parent feature:** S4-F05
  - **Issue type:** Agent
  - **Technical story:** Implement the bounded backend/application behavior for Review a Proposer candidate with non-authoring Reviewer and bounded revision so the feature has one authoritative service path.
  - **Context:** Critique is separated from authorship to preserve lineage and prevent a hidden replacement patch.
  - **Scope:** ReviewerService with schema explicitly excluding diff, evidence/minimality/parity/security checks, semantic validation, bounded revision/context expansion counters, and Proposer revision lineage.
  - **Out of scope:** Human approval, patch application, unlimited review loops, and reviewer-edited patch.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: ReviewerService with schema explicitly excluding diff, evidence/minimality/parity/security checks, semantic validation, bounded revision/context expansion counters, and Proposer revision lineage.
  - **Database impact:** Use or introduce the records summarized by: review_decisions, revision/context counters, LLM invocations/usage, artifact refs.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions
  - **Event impact:** Request durable events only through the transition/event service: REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Reviewer structured response, critique/revision instructions, schema-validation evidence, revised Proposer candidate where applicable.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Reviewer smuggling patch in text, circular revisions, inconsistent evidence refs, independent-role configuration error, and context expansion exposing secrets.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's agent behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F04
  - **Suggested labels:** sprint-4, s4-f05, repair-capability, agent, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/05-S4-F05-I01.json`.
- Task completion requires reviewer verdict `PASS`.
