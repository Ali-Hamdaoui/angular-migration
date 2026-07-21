# Task 17 — S3-F14-I01 — Implement backend application contract for Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21

## Identity

- Capability goal: `G04`
- Backlog feature: `S3-F14` / `AMFA-153`
- Jira subtask: `AMFA-206`
- Source contract SHA-256: `449f1606428900f80b858c1abec0a5858b8481b4305408bd28446348ffda50fc`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F14-I01 — Implement backend application contract for Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21

  - **Parent feature:** S3-F14
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21 so the feature has one authoritative service path.
  - **Context:** Stage completion and copy-forward are separate trusted boundaries. The engine must use actual prior-stage output and finalize exact versions before each new stage.
  - **Scope:** StageCompletionService, cleanup/cleanliness verification, stable output fingerprint, G12 package, copy-forward, next-stage exact re-resolution/plan revision hook, LangGraph stage loop, and stage status aggregation.
  - **Out of scope:** LLM repair, final clean assurance, delivery, and startup crash recovery.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G12 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: StageCompletionService, cleanup/cleanliness verification, stable output fingerprint, G12 package, copy-forward, next-stage exact re-resolution/plan revision hook, LangGraph stage loop, and stage status aggregation.
  - **Database impact:** Use or introduce the records summarized by: Stage output records, fingerprints, gate decisions, next-stage sandbox records, transitions/events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward
  - **Event impact:** Request durable events only through the transition/event service: STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: node_modules copied forward, unstable fingerprint, stage index mismatch, wrong sandbox path, next exact profile not revalidated, artifact cross-stage overwrite, and UI showing wrong active stage.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G12 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F13
  - **Suggested labels:** sprint-3, s3-f14, approval-capability, backend, g12, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/17-S3-F14-I01.json`.
- Task completion requires reviewer verdict `PASS`.
