# Task 01 — S4-F04-I01 — Implement backend application contract for Generate and review a Proposer repair candidate

## Identity

- Capability goal: `G06`
- Backlog feature: `S4-F04` / `AMFA-214`
- Jira subtask: `AMFA-238`
- Source contract SHA-256: `8c485cb577936f8de037d0eac40ace047ab300e5a3981239680ddcd117c79d91`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F04-I01 — Implement backend application contract for Generate and review a Proposer repair candidate

  - **Parent feature:** S4-F04
  - **Issue type:** Agent
  - **Technical story:** Implement the bounded backend/application behavior for Generate and review a Proposer repair candidate so the feature has one authoritative service path.
  - **Context:** Only the Proposer LLM may author a repair diff; output remains an untrusted proposal until deterministic validation and Reviewer acceptance.
  - **Scope:** ProposerService using gateway role/prompt/schema, deterministic input references, candidate/insufficient/not-repairable statuses, diff parse, changed-file consistency, forbidden-action checks, lineage binding, and retry limits.
  - **Out of scope:** Reviewer decision, human Apply, patch application, command execution, and direct filesystem writes.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: ProposerService using gateway role/prompt/schema, deterministic input references, candidate/insufficient/not-repairable statuses, diff parse, changed-file consistency, forbidden-action checks, lineage binding, and retry limits.
  - **Database impact:** Use or introduce the records summarized by: Proposer invocation/result metadata, status, context lineage, usage/cost, artifact refs.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer
  - **Event impact:** Request durable events only through the transition/event service: PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Structured Proposer response, exact proposed diff, semantic validation report, changed-file inventory, usage/cost.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Hallucinated API/package, invalid diff, scope expansion, test weakening, hidden modernization, stale context, and model claiming approval.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's agent behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F03, S2-F03
  - **Suggested labels:** sprint-4, s4-f04, repair-capability, agent, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/01-S4-F04-I01.json`.
- Task completion requires reviewer verdict `PASS`.
