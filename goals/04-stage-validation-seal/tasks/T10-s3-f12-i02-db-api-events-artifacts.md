# Task 10 — S3-F12-I02 — Persist and expose evidence contracts for Run complete stage tests and conditional lint

## Identity

- Capability goal: `G04`
- Backlog feature: `S3-F12` / `AMFA-151`
- Jira subtask: `AMFA-199`
- Source contract SHA-256: `b687a3ad15806965b205a3aebd972d4fbb709abb7e2f4cedac1b727d8d3a1ae3`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S3-F12-I02 — Persist and expose evidence contracts for Run complete stage tests and conditional lint

  - **Parent feature:** S3-F12
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Run complete stage tests and conditional lint observable and auditable.
  - **Context:** Full tests are required after each stage; lint is conditional but must be represented honestly.
  - **Scope:** Persistence: Command results, comparison results, step statuses, diagnostics and artifacts. API: POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality. Events: STAGE_TESTS_* and STAGE_LINT_* events. Artifacts: Full test/lint logs, structured results, baseline comparison, test-file change report, and known-failure delta.
  - **Out of scope:** Disabling tests, assertion weakening, test-framework replacement, browser E2E, and repair.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Command results, comparison results, step statuses, diagnostics and artifacts.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: STAGE_TESTS_* and STAGE_LINT_* events.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Full test/lint logs, structured results, baseline comparison, test-file change report, and known-failure delta.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F12-I01
  - **Suggested labels:** sprint-3, s3-f12, validation-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/10-S3-F12-I02.json`.
- Task completion requires reviewer verdict `PASS`.
