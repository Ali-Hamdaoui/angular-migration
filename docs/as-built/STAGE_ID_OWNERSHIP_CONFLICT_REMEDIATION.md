# Stage ID Ownership Conflict Remediation

Date: 2026-07-29

## Outcome

The Planning/G06 failure for `run-21b7e5ccf404` was reproduced and fixed.
The repository is ready for Transformation Agent development, but that
specific migration run cannot be resumed. A fresh migration run is required
after the backend is restarted with this fix.

## Root cause

The compatibility catalogue intentionally reuses semantic route identifiers
such as `angular-18-to-19`. Planning persisted that catalogue identifier
directly as `migration_stages.id`, even though the column is a global primary
key. A second migration using the same route therefore collided with the
stage owned by an earlier run and failed terminally with:

`STAGE_ID_OWNERSHIP_CONFLICT at generating_plan`

The catalogue route was correct. The persistence identity was not scoped to
the migration run.

## Remediation

Planning now derives a deterministic, globally unique stage-instance ID from
the run ID and catalogue stage ID:

`<catalogue-stage-id>--<16-character SHA-256 prefix>`

The derived identity is bounded to the existing 64-character database
contract and is used consistently by:

- `MigrationPlan.route`
- `StageExecutionPlan.stage_id`
- persisted `MigrationStage.id`
- stage-plan API paths
- stage workspace aliases

The G05 compatibility catalogue and approved semantic route remain unchanged.
Only the run-owned executable stage identity is scoped.

Regression coverage proves that two runs planning the same catalogue route
receive different stage IDs and that stage persistence, foreign keys, API
reads, generated command aliases, and the Planning-to-Transformation boundary
use the same derived identity.

## Test database isolation incident

The first diagnostic full-suite run used the configured operational SQLite
database because the suite had no process-wide database isolation. That run
recreated the schema and removed the existing relational projections,
including `run-21b7e5ccf404` and the earlier proof run.

No safe relational backup containing these current runs was found. Rebuilding
the database from artifacts alone would invent missing event, approval,
idempotency, and state-version history, so no synthetic recovery was
performed.

`backend/tests/conftest.py` now establishes a unique temporary application
root and database before any application import, disables live LLM use, and
applies Alembic migrations only to that isolated database.
`test_test_database_isolation.py` fails if pytest ever resolves the configured
operational `control-tower.db`.

The operational database currently has:

- Alembic head: `20260729_35`
- `PRAGMA integrity_check`: `ok`
- foreign-key violations: `0`
- migration runs: `0`
- migration stages: `0`

A focused settings/startup/isolation run passed 21 tests while preserving the
operational database SHA-256 and modification timestamp byte-for-byte. An
earlier one-time pre/post-suite hash discrepancy was observed after the
database recreation; it did not change the empty row counts, schema head, or
integrity result and was not reproducible after the isolation guard.

## Preserved failed-run evidence

The filesystem evidence for `run-21b7e5ccf404` remains at:

`C:\Users\hamdaoui.ali\Downloads\MSA-COMMON-STG1\angular-crud-poc-angular-21-dc1b18a11ec1\.migration-factory\runs\run-21b7e5ccf404`

Its 102 payload files and 102 metadata sidecars were audited with:

- checksum mismatches: `0`
- missing or orphan metadata: `0`
- metadata/path inconsistencies: `0`

The terminal planning failure remains immutable forensic evidence under
`artifacts/03_planning/planning-generation-failure.json`.

## Verification

The complete backend suite was executed in deterministic partitions because a
single process exceeded the execution environment's five-minute limit:

- A-C: `322 passed, 3 skipped`
- D-L: `100 passed`
- M-Z: `284 passed, 2 skipped`
- Total: `706 passed, 5 skipped`, zero failures

The remaining warnings are third-party deprecations from Starlette/httpx,
pytest-asyncio/Python 3.14, and LangGraph.

Ruff passes for all changed Planning and isolation files. `git diff --check`
also passes; Git reports only the repository's existing LF-to-CRLF checkout
notices.

## Operational decision

Repository readiness: **ready for Transformation Agent development**.

Current-run readiness: **not resumable**. Restart the backend and create a
fresh migration run, then complete G01-G06 again. The new Planning stage IDs
will be run-scoped and will not collide with another migration using the same
Angular route.
