# Task 02 — S4-F15-I02 — Persist and expose evidence contracts for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

## Identity

- Capability goal: `G10`
- Backlog feature: `S4-F15` / `AMFA-225`
- Jira subtask: `AMFA-283`
- Source contract SHA-256: `dccf1f91fad2d65db31b31a2aa0df6935fe7d44a7c0029c0f5f5a6f2f4692836`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F15-I02 — Persist and expose evidence contracts for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

  - **Parent feature:** S4-F15
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart observable and auditable.
  - **Context:** The MVP is complete only when the integrated controlled platform—not isolated services—proves the authoritative workflow.
  - **Scope:** Persistence: Test execution metadata and complete migration-run records/artifacts. API: Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status. Events: Existing production events validated for completeness/order; acceptance-suite status events optional. Artifacts: External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
  - **Out of scope:** Angular 11-17 production validation, Angular 22, unsupported topologies, browser automation, and enterprise scale.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Test execution metadata and complete migration-run records/artifacts.
  - **API impact:** Implement and document: Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: Existing production events validated for completeness/order; acceptance-suite status events optional.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F15-I01
  - **Suggested labels:** sprint-4, s4-f15, operational-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

## Goal 10 phase boundary

Phase A implements only the branch-owned acceptance harness and consuming contracts. Any criterion requiring real G01–G09 production implementations is recorded as `BLOCKED_INTEGRATION` rather than faked. Phase A may become `harness_ready` but cannot complete AMFA-225. Phase B executes this exact task contract against the integrated product and is required for `jira_complete=true`.

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/02-S4-F15-I02.json`.
- Task completion requires reviewer verdict `PASS`.
