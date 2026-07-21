# Task 06 — S4-F05-I02 — Persist and expose evidence contracts for Review a Proposer candidate with non-authoring Reviewer and bounded revision

## Identity

- Capability goal: `G06`
- Backlog feature: `S4-F05` / `AMFA-215`
- Jira subtask: `AMFA-243`
- Source contract SHA-256: `0cf6a440ef02d5cf940aa9f4a5f66d77440bb6de0747dcbed84682a3db44d81f`

## Mandatory subagent cycle

1. Read-only planner maps current symbols, reuse, gaps, owned/shared files, tests, risks, acceptance criteria, and ordered implementation.
2. Sole implementer executes only the approved scope and tests.
3. Independent read-only reviewer checks the exact task and parent-feature acceptance criteria.
4. Only when the reviewer returns `FAIL`, a fixer applies the approved findings.
5. Only after fixes, an independent re-review returns `PASS` or remaining evidence-backed findings. No fixer/re-review run is required after a first-pass `PASS`.

## Exact authoritative subissue contract

#### S4-F05-I02 — Persist and expose evidence contracts for Review a Proposer candidate with non-authoring Reviewer and bounded revision

  - **Parent feature:** S4-F05
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Review a Proposer candidate with non-authoring Reviewer and bounded revision observable and auditable.
  - **Context:** Critique is separated from authorship to preserve lineage and prevent a hidden replacement patch.
  - **Scope:** Persistence: review_decisions, revision/context counters, LLM invocations/usage, artifact refs. API: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions. Events: REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED. Artifacts: Reviewer structured response, critique/revision instructions, schema-validation evidence, revised Proposer candidate where applicable.
  - **Out of scope:** Human approval, patch application, unlimited review loops, and reviewer-edited patch.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: review_decisions, revision/context counters, LLM invocations/usage, artifact refs.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Reviewer structured response, critique/revision instructions, schema-validation evidence, revised Proposer candidate where applicable.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F05-I01
  - **Suggested labels:** sprint-4, s4-f05, repair-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

## Additional execution requirements

- Conform to consumed/provided frozen schemas in `CROSS_GOAL_CONTRACTS.md`.
- Do not implement another feature or Sprint 2 to hide a dependency gap.
- Record changed/shared files, tests, artifacts/events, limitations, commit SHA, and reviewer verdict in `evidence/task-results/06-S4-F05-I02.json`.
- Task completion requires reviewer verdict `PASS`.
