# Task 09 — S4-F14-I01 — Implement backend application contract for Generate, view, download, and accept the final evidence and cost report through G15

## Identity

- Capability goal: `G09`
- Backlog feature: `S4-F14` / `AMFA-224`
- Jira subtask: `AMFA-278`
- Source contract SHA-256: `8b5b2949946dae16b513aaee6e4faafd9f82e4bfa3e93a331ec98ee4bcca4135`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F14-I01 — Implement backend application contract for Generate, view, download, and accept the final evidence and cost report through G15

  - **Parent feature:** S4-F14
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Generate, view, download, and accept the final evidence and cost report through G15 so the feature has one authoritative service path.
  - **Context:** The report is an evidence index and honest assurance summary, not a narrative that invents unexecuted success.
  - **Scope:** ReportService and optional ReportAgent constrained to authoritative facts, report schema/proof-label validator, artifact index builder, token/cost aggregator, manual/deferred status validator, G15 package, and immutable report generation.
  - **Out of scope:** PDF unless separately approved, hidden chain-of-thought, cached/reasoning token metrics, and claiming external scans passed.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G15 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: ReportService and optional ReportAgent constrained to authoritative facts, report schema/proof-label validator, artifact index builder, token/cost aggregator, manual/deferred status validator, G15 package, and immutable report generation.
  - **Database impact:** Use or introduce the records summarized by: Report metadata/version/checksum, aggregate usage/cost, gate decisions, completion transition.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions
  - **Event impact:** Request durable events only through the transition/event service: REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Missing artifact, report overclaim, cost rounding/config mismatch, broken links, sensitive logs exposed, stale delivery data, and accepting incomplete report.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G15 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F11, S4-F13
  - **Suggested labels:** sprint-4, s4-f14, reporting-capability, backend, g15, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/09-S4-F14-I01.json`.
- Task completion requires reviewer verdict `PASS`.
