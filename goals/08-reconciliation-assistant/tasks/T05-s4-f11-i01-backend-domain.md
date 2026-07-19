# Task 05 — S4-F11-I01 — Implement backend application contract for Explain authoritative migration state through the AI Assistant

## Identity

- Capability goal: `G08`
- Backlog feature: `S4-F11` / `AMFA-221`
- Jira subtask: `AMFA-266`
- Source contract SHA-256: `5dd1bf8bca3b5f1a0eb103d29978747a40479ceead609ca75fe16cd4227d9201`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F11-I01 — Implement backend application contract for Explain authoritative migration state through the AI Assistant

  - **Parent feature:** S4-F11
  - **Issue type:** Agent
  - **Technical story:** Implement the bounded backend/application behavior for Explain authoritative migration state through the AI Assistant so the feature has one authoritative service path.
  - **Context:** The Assistant improves comprehension but remains read-only and subordinate to authoritative services.
  - **Scope:** AssistantContextService selecting authoritative state and approved artifacts, sanitized bounded prompt, structured answer with evidence refs/proof labels, LLM usage/cost, and explicit forbidden-action policy.
  - **Out of scope:** Direct command/file tools, silent approval, raw secret exposure, unrestricted filesystem search, and autonomous workflow changes.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/assistant/messages; GET /api/v1/runs/{id}/assistant/messages`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: AssistantContextService selecting authoritative state and approved artifacts, sanitized bounded prompt, structured answer with evidence refs/proof labels, LLM usage/cost, and explicit forbidden-action policy.
  - **Database impact:** Use or introduce the records summarized by: Conversation/message metadata, artifact refs, usage/cost; no hidden chain-of-thought.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/assistant/messages; GET /api/v1/runs/{id}/assistant/messages
  - **Event impact:** Request durable events only through the transition/event service: ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Sanitized assistant input manifest, structured answer, evidence citations, and usage record.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Hallucinated status, prompt injection, stale evidence, unauthorized artifact, chat interpreted as approval, secret leakage, and high cost.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's agent behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S2-F03, S4-F10
  - **Suggested labels:** sprint-4, s4-f11, product-capability, agent, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/05-S4-F11-I01.json`.
- Task completion requires reviewer verdict `PASS`.
