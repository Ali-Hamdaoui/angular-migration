# Task 01 — S4-F10-I01 — Implement backend application contract for Reconcile interrupted commands, leases, artifacts, and graph state on startup

## Identity

- Capability goal: `G08`
- Backlog feature: `S4-F10` / `AMFA-220`
- Jira subtask: `AMFA-262`
- Source contract SHA-256: `3e36bb1df76def95a59a51b285eaa324bcdd944fc7f605e36dfd079b3593161a`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F10-I01 — Implement backend application contract for Reconcile interrupted commands, leases, artifacts, and graph state on startup

  - **Parent feature:** S4-F10
  - **Issue type:** Orchestration
  - **Technical story:** Implement the bounded backend/application behavior for Reconcile interrupted commands, leases, artifacts, and graph state on startup so the feature has one authoritative service path.
  - **Context:** SQLite is authoritative and LangGraph checkpoints are resume hints; restart must not duplicate mutation or invent evidence.
  - **Scope:** StartupReconciliationService for backend instance ID, stale leases/commands, mutation-category recovery, graph reconstruction from SQLite, artifact temp/orphan/missing/hash checks, workspace quarantine, and Transition Service recovery states.
  - **Out of scope:** Distributed recovery, cross-host process adoption, silent artifact repair, and permanent retention deletion.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/operator/reconciliation; GET /api/v1/operator/reconciliation/latest; POST /api/v1/runs/{id}/resume`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: StartupReconciliationService for backend instance ID, stale leases/commands, mutation-category recovery, graph reconstruction from SQLite, artifact temp/orphan/missing/hash checks, workspace quarantine, and Transition Service recovery states.
  - **Database impact:** Use or introduce the records summarized by: Reconciliation run/results, interrupted statuses, lease updates, artifact integrity findings, transitions/events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/operator/reconciliation; GET /api/v1/operator/reconciliation/latest; POST /api/v1/runs/{id}/resume
  - **Event impact:** Request durable events only through the transition/event service: RECONCILIATION_STARTED/COMPLETED, COMMAND_INTERRUPTED, ARTIFACT_INTEGRITY_FAILED, RUN_RECOVERY_READY/DIAGNOSTIC_HOLD.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Startup reconciliation report, artifact mismatch list, workspace recovery decision, and graph reconstruction summary.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: PID reuse, old backend process still alive, artifact mismatch, checkpoint newer than DB, unsafe mid-update resume, duplicate command, and operator choosing invalid boundary.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's orchestration behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F04, S3-F14, S4-F09
  - **Suggested labels:** sprint-4, s4-f10, operational-capability, orchestration, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/01-S4-F10-I01.json`.
- Task completion requires reviewer verdict `PASS`.
