# Task 01 — S3-F01-I01 — Implement backend application contract for Register structured commands and reject arbitrary shell execution

## Identity

- Capability goal: `G01`
- Backlog feature: `S3-F01` / `AMFA-140`
- Jira subtask: `AMFA-154`
- Source contract SHA-256: `a688e005ce6781285dcfca74301981685a14bd1327cffa27ee823804de2f05cf`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F01-I01 — Implement backend application contract for Register structured commands and reject arbitrary shell execution

  - **Parent feature:** S3-F01
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Register structured commands and reject arbitrary shell execution so the feature has one authoritative service path.
  - **Context:** All execution must pass through a structured registry and policy engine; plans authorize command references, not arbitrary shell text.
  - **Scope:** StructuredCommandRegistry, executable/argument schemas, CommandPolicyEngine, plan membership checks, environment/network/working-directory policy, and shell=false enforcement.
  - **Out of scope:** Starting processes, live logs, user-defined commands, PowerShell wrappers, and LLM command generation.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: StructuredCommandRegistry, executable/argument schemas, CommandPolicyEngine, plan membership checks, environment/network/working-directory policy, and shell=false enforcement.
  - **Database impact:** Use or introduce the records summarized by: Versioned command-template metadata and authorization audit records.
  - **API impact:** Define service-facing request/response models supporting: GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate
  - **Event impact:** Request durable events only through the transition/event service: COMMAND_AUTHORIZATION_ACCEPTED/REJECTED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Sanitized command authorization decision artifact for operator tests.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Argument injection, cmd/PowerShell wrapping, path alias escape, forbidden --force/--legacy-peer-deps, environment smuggling, and template drift.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S2-F07
  - **Suggested labels:** sprint-3, s3-f01, execution-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/01-S3-F01-I01.json`.
- Task completion requires reviewer verdict `PASS`.
