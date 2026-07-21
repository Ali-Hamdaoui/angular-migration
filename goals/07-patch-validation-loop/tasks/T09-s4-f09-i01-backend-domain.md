# Task 09 — S4-F09-I01 — Implement backend application contract for Stop no-progress repair loops and reconstruct or roll back safely

## Identity

- Capability goal: `G07`
- Backlog feature: `S4-F09` / `AMFA-219`
- Jira subtask: `AMFA-258`
- Source contract SHA-256: `aabffaed3c194253a6ba6630bc00d9bb948243c8509e3946620164fc3403749b`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F09-I01 — Implement backend application contract for Stop no-progress repair loops and reconstruct or roll back safely

  - **Parent feature:** S4-F09
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Stop no-progress repair loops and reconstruct or roll back safely so the feature has one authoritative service path.
  - **Context:** Bounded repair protects cost, source parity, and delivery predictability; repeated equivalent patches must never loop.
  - **Scope:** RepairProgressService, semantic patch normalization/fingerprints, failure-set comparison, max-three applied attempts, revision/transport counters separation, rollback checkpoint or WorkspaceManager reconstruction, and diagnostic-hold transitions.
  - **Out of scope:** Automatic business-level resolution, unlimited human overrides, and cross-run learning.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `GET /api/v1/runs/{id}/repair-chains/{chainId}; POST /api/v1/runs/{id}/repair-chains/{chainId}/recover`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: RepairProgressService, semantic patch normalization/fingerprints, failure-set comparison, max-three applied attempts, revision/transport counters separation, rollback checkpoint or WorkspaceManager reconstruction, and diagnostic-hold transitions.
  - **Database impact:** Use or introduce the records summarized by: Attempt counters/outcomes, no-progress decisions, rollback/reconstruction records, state/events.
  - **API impact:** Define service-facing request/response models supporting: GET /api/v1/runs/{id}/repair-chains/{chainId}; POST /api/v1/runs/{id}/repair-chains/{chainId}/recover
  - **Event impact:** Request durable events only through the transition/event service: DUPLICATE_PATCH_REJECTED, NO_PROGRESS_DETECTED, REPAIR_ROLLED_BACK, STAGE_RECONSTRUCTED, ATTEMPT_LIMIT_REACHED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Attempt lineage, fingerprint comparison, error-delta history, rollback/reconstruction report, and diagnostic-hold summary.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Equivalent patch normalization false positive, rollback incomplete, reconstruction from wrong input, attempts miscounted, cost race, and high-risk change escalation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F08
  - **Suggested labels:** sprint-4, s4-f09, repair-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/09-S4-F09-I01.json`.
- Task completion requires reviewer verdict `PASS`.
