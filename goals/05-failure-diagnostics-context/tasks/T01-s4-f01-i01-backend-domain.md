# Task 01 — S4-F01-I01 — Implement backend application contract for Capture FailureEvidence and parse deterministic diagnostics

## Identity

- Capability goal: `G05`
- Backlog feature: `S4-F01` / `AMFA-211`
- Jira subtask: `AMFA-226`
- Source contract SHA-256: `d38bbdee720397f1ad4586b4beb523c03a00b550bd4501c7ebf391aa72a313ae`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F01-I01 — Implement backend application contract for Capture FailureEvidence and parse deterministic diagnostics

  - **Parent feature:** S4-F01
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Capture FailureEvidence and parse deterministic diagnostics so the feature has one authoritative service path.
  - **Context:** Repair may begin only from a real failed command with deterministic evidence, never from a speculative LLM diagnosis.
  - **Scope:** FailureEvidenceBuilder, parser registry, parser adapters, normalized diagnostic schema, failure/origin fingerprints, baseline comparator, and Artifact Store registration before failure transition.
  - **Out of scope:** C-Lite routing action, LLM context, patch proposal, and environment remediation execution.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/commands/{commandId}/failure-evidence; GET /api/v1/runs/{id}/failures/{failureId}`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: FailureEvidenceBuilder, parser registry, parser adapters, normalized diagnostic schema, failure/origin fingerprints, baseline comparator, and Artifact Store registration before failure transition.
  - **Database impact:** Use or introduce the records summarized by: failures and failure_diagnostics metadata plus artifact references and transition events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/commands/{commandId}/failure-evidence; GET /api/v1/runs/{id}/failures/{failureId}
  - **Event impact:** Request durable events only through the transition/event service: FAILURE_CAPTURED and FAILURE_DIAGNOSTICS_PARSED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Raw stdout/stderr references, structured FailureEvidence JSON, parser report, normalized diagnostics, and origin comparison.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Parser false certainty, log truncation, line-number drift, unstable fingerprints, secret leakage, and failure transition before artifacts exist.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F02, S3-F12
  - **Suggested labels:** sprint-4, s4-f01, repair-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/01-S4-F01-I01.json`.
- Task completion requires reviewer verdict `PASS`.
