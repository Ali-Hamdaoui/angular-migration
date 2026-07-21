# Task 13 — S3-F04-I01 — Implement backend application contract for Own commands with JobSupervisor, leases, timeout, and explicit cancellation

## Identity

- Capability goal: `G01`
- Backlog feature: `S3-F04` / `AMFA-143`
- Jira subtask: `AMFA-166`
- Source contract SHA-256: `5d8106b28922230e597f920fffd48c3cba70b7c79033371fe6b8a131311370de`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F04-I01 — Implement backend application contract for Own commands with JobSupervisor, leases, timeout, and explicit cancellation

  - **Parent feature:** S3-F04
  - **Issue type:** Orchestration
  - **Technical story:** Implement the bounded backend/application behavior for Own commands with JobSupervisor, leases, timeout, and explicit cancellation so the feature has one authoritative service path.
  - **Context:** Browser disconnect must not cancel work, but explicit user cancellation must stop scheduling and terminate the complete process tree safely.
  - **Scope:** JobSupervisor active-command ownership, WorkerLease heartbeat/expiry, ProcessController process-tree termination, timeout, cancel idempotency, mutation-category recovery classification, and Transition Service cancellation.
  - **Out of scope:** Full startup reconciliation, resume after crash, multi-worker scheduling, and repair rollback.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/cancel; GET /api/v1/runs/{id}/active-command`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: JobSupervisor active-command ownership, WorkerLease heartbeat/expiry, ProcessController process-tree termination, timeout, cancel idempotency, mutation-category recovery classification, and Transition Service cancellation.
  - **Database impact:** Use or introduce the records summarized by: worker_leases, command cancellation metadata, run/step states, durable events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/cancel; GET /api/v1/runs/{id}/active-command
  - **Event impact:** Request durable events only through the transition/event service: RUN_CANCEL_REQUESTED, COMMAND_CANCELLED/INTERRUPTED, RUN_CANCELLED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Partial logs, process-termination report, workspace trust/recovery classification, and partial cancellation summary.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: PID reuse, descendant escape, cancellation race at completion, stale lease, locked files, mutating command interruption, and false claim of terminated tree.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's orchestration behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F02, S3-F03
  - **Suggested labels:** sprint-3, s3-f04, operational-capability, orchestration, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/13-S3-F04-I01.json`.
- Task completion requires reviewer verdict `PASS`.
