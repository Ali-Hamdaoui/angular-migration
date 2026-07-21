# Task 09 — S4-F03-I01 — Implement backend application contract for Build and inspect a bounded sanitized RepairContextPack

## Identity

- Capability goal: `G05`
- Backlog feature: `S4-F03` / `AMFA-213`
- Jira subtask: `AMFA-234`
- Source contract SHA-256: `9022f10adf0eba7f5f05dd89a950dbfe525ec9ae31a3be08886e800ebf09f75a`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F03-I01 — Implement backend application contract for Build and inspect a bounded sanitized RepairContextPack

  - **Parent feature:** S4-F03
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Build and inspect a bounded sanitized RepairContextPack so the feature has one authoritative service path.
  - **Context:** Repository content is untrusted data; the model cannot freely browse the workspace or receive secrets.
  - **Scope:** RepairContextPackBuilder, deterministic selection priority, excerpt/full-file checksum binding, component/template/import relations, prior-attempt inclusion, secret sanitizer, context budget, and one governed expansion hook.
  - **Out of scope:** Calling Azure OpenAI, editing context manually, arbitrary file browsing, and patch generation.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/failures/{failureId}/repair-context; GET /api/v1/runs/{id}/repair-contexts/{contextId}`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: RepairContextPackBuilder, deterministic selection priority, excerpt/full-file checksum binding, component/template/import relations, prior-attempt inclusion, secret sanitizer, context budget, and one governed expansion hook.
  - **Database impact:** Use or introduce the records summarized by: repair_attempts, context-pack metadata, selection reasons, checksums, sanitizer record, artifact refs.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/failures/{failureId}/repair-context; GET /api/v1/runs/{id}/repair-contexts/{contextId}
  - **Event impact:** Request durable events only through the transition/event service: REPAIR_CONTEXT_CREATED or REPAIR_CONTEXT_BLOCKED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Sanitized context pack, selection manifest, redaction report, token estimate, and forbidden-action policy.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Secret missed by sanitizer, prompt injection, excessive context, stale file checksum, missing diagnostic relation, and excerpt misleading without context.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F01, S4-F02
  - **Suggested labels:** sprint-4, s4-f03, repair-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/09-S4-F03-I01.json`.
- Task completion requires reviewer verdict `PASS`.
