# Task 05 — S3-F08-I01 — Implement backend application contract for Capture transformation diffs and classify changed-file risk

## Identity

- Capability goal: `G03`
- Backlog feature: `S3-F08` / `AMFA-147`
- Jira subtask: `AMFA-182`
- Source contract SHA-256: `51601c3f26eb4c7fa5b7eb88b831cb1bf8cca2f9a52ece4fb85158e03e3a2951`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F08-I01 — Implement backend application contract for Capture transformation diffs and classify changed-file risk

  - **Parent feature:** S3-F08
  - **Issue type:** Validation
  - **Technical story:** Implement the bounded backend/application behavior for Capture transformation diffs and classify changed-file risk so the feature has one authoritative service path.
  - **Context:** Official tooling can produce behavior-sensitive or optional changes; the transformation must be reviewable before acceptance.
  - **Scope:** TransformationEvidenceService, unified diff generator, package/lockfile summaries, changed-file classifier, sensitive-symbol/path rules, forbidden-modernization scanner, and builder-decision comparison.
  - **Out of scope:** Approving G08, editing diff, applying repair patches, and runtime parity proof.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: TransformationEvidenceService, unified diff generator, package/lockfile summaries, changed-file classifier, sensitive-symbol/path rules, forbidden-modernization scanner, and builder-decision comparison.
  - **Database impact:** Use or introduce the records summarized by: Transformation summary/risk metadata and artifact references.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence
  - **Event impact:** Request durable events only through the transition/event service: TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Complete unified diff, package/lockfile diff, migration list, changed-file inventory, risk report, forbidden-change report.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Huge diff, binary files, line-ending noise, generated files, misclassified auth/API changes, hidden modernization, and incomplete diff.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's validation behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F07
  - **Suggested labels:** sprint-3, s3-f08, validation-capability, validation, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/05-S3-F08-I01.json`.
- Task completion requires reviewer verdict `PASS`.
