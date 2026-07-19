# Task 05 — S3-F02-I01 — Implement backend application contract for Execute one approved command and persist authoritative command evidence

## Identity

- Capability goal: `G01`
- Backlog feature: `S3-F02` / `AMFA-141`
- Jira subtask: `AMFA-158`
- Source contract SHA-256: `5bebd335ed0829f6315a3ed4c91971d6362dff7a48dba6418a46c84cccd86637`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F02-I01 — Implement backend application contract for Execute one approved command and persist authoritative command evidence

  - **Parent feature:** S3-F02
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Execute one approved command and persist authoritative command evidence so the feature has one authoritative service path.
  - **Context:** CommandExecutor is the sole authoritative external-process path and must be proven before Angular mutation.
  - **Scope:** CommandExecutor, ProcessController basic launch, execution-profile materialization, workspace alias resolution, command ownership, timeout metadata, output capture, redaction, and result persistence.
  - **Out of scope:** Live log streaming, cancellation, interactive prompts, stage mutation, and arbitrary command selection.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/commands; GET /api/v1/runs/{id}/commands/{commandId}`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: CommandExecutor, ProcessController basic launch, execution-profile materialization, workspace alias resolution, command ownership, timeout metadata, output capture, redaction, and result persistence.
  - **Database impact:** Use or introduce the records summarized by: command_executions with idempotency, state, runtime checksum, process metadata, and artifact references.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/commands; GET /api/v1/runs/{id}/commands/{commandId}
  - **Event impact:** Request durable events only through the transition/event service: COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Command manifest, full stdout, full stderr, combined ordered stream where available, and result report.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Duplicate execution, mismatched runtime profile, unbounded output, secret leakage, cwd escape, orphan process, and evidence registration after pass.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F01
  - **Suggested labels:** sprint-3, s3-f02, execution-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/05-S3-F02-I01.json`.
- Task completion requires reviewer verdict `PASS`.
