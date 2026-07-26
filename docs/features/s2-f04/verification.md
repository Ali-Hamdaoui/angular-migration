# S2-F04 Verification Record

Verification was refreshed on 2026-07-26 at 14:45 +01:00 from working tree
`4135dfa` on branch `hermes/01-command-runtime` (working tree modified).

## Verified root cause and correction

The reviewer lifecycle hook created its invocation and then assigned
`row.reviewer_invocation_id` without loading `row`. The resulting
`UnboundLocalError` occurred before reviewer transport, and the hook transaction
rolled back the reviewer invocation and lifecycle events. The reviewer handler
then misclassified the programming error as `LLM_INTERNAL_GATEWAY_ERROR`.

The service now uses `_require_analysis_row()` keyed by both run ID and Analysis
idempotency key. Reviewer persistence is committed by the hook session before
the gateway call. Analysis responses expose proposer, reviewer, and failed
invocation IDs independently; no proposer fallback is used.

## Fresh automated evidence

Environment: Python 3.14.6; Node v20.11.1; npm 10.2.4.

RED, before the production fix:

```text
python -m pytest backend/tests/test_analysis_reviewer_lifecycle_regression.py -q
1 failed
AssertionError: status='failed', error_code='ANALYSIS_REVIEW_FAILED',
cause_code='LLM_INTERNAL_GATEWAY_ERROR', failure_stage='phase_reviewer'
```

The diagnostic run recorded one fake-gateway request, no durable reviewer
invocation/start event, and the failed-invocation projection incorrectly pointed
at the proposer.

GREEN, after the fix:

```text
python -m pytest backend/tests/test_analysis_reviewer_lifecycle_regression.py backend/tests/test_analysis_evidence_persistence_api_s2_f04_i02.py backend/tests/test_analysis_application_service_s2_f04_i01.py -q
22 passed, 2 warnings
```

The real-service regression records two provider calls, two invocation rows,
`failed_invocation_id = null`, pending G04, and this event sequence:

```text
ANALYSIS_AGENT_STARTED
LLM_INVOCATION_STARTED        proposer
LLM_INVOCATION_COMPLETED      proposer
ANALYSIS_AGENT_COMPLETED
ANALYSIS_REVIEWER_STARTED
LLM_INVOCATION_STARTED        reviewer
LLM_INVOCATION_COMPLETED      reviewer
ANALYSIS_REVIEWER_COMPLETED
G04_CREATED
```

Additional fresh checks:

```text
python -m ruff check backend/app backend/tests --select F823
All checks passed!
python -m ruff check backend/app backend/tests
All checks passed!
python -m pytest backend/tests/test_azure_response_boundary.py backend/tests/test_llm_gateway.py backend/tests/test_analysis_reviewer_lifecycle_regression.py -q
32 passed, 2 warnings
python -m pytest backend/tests/test_persistence.py::test_alembic_feature_schema_upgrades_and_rolls_back_on_temporary_sqlite -q
1 passed, 1 warning
```

The complete backend suite ran for 5:02 and produced `549 passed, 4 skipped,
7 failed`. The remaining failures are outside S2-F04: two legacy S2-F03
expectation mismatches, and one readiness expectation mismatch. They are not
reported as a passing full-backend verification.

## Database migration

Added `20260726_25_analysis_failure_origin.py`, down revision `20260726_24`.
It adds durable failure origin, technical stage, transport-started, and provider
request correlation fields to Analysis metadata. Existing records are preserved.

```text
python -m alembic -c alembic.ini current       -> 20260726_24
python -m alembic -c alembic.ini upgrade heads -> 20260726_25
python -m alembic -c alembic.ini downgrade 20260726_24
python -m alembic -c alembic.ini upgrade heads -> 20260726_25
```

The temporary SQLite Alembic round trip passed. The standalone `alembic`
executable is not installed; `python -m alembic` is the available canonical
command.

## Frontend and manual workflow

`npm ci` was blocked by Windows `EPERM` while unlinking
`frontend/node_modules/@next/swc-win32-x64-msvc/next-swc.win32-x64-msvc.node`;
Node 20.11.1 also does not satisfy several installed package engine ranges.
Consequently `npm test`, lint, typecheck, and build could not execute because
their binaries were unavailable after the interrupted install. No live Azure or
authenticated browser workflow was run: the repository environment has no
authorized provider configuration. A real post-G03 workflow, controlled
provider failure, retry, and restart recovery therefore remain unverified.

## Scope and remaining risks

Implemented changes include reviewer lifecycle persistence, error-origin
classification, explicit invocation lineage, safe frontend projection, provider
transport result correlation, append-only retry API, and restart handling for
retry-waiting source-intake jobs.

Retry and restart paths still need dedicated end-to-end tests against a real
source-intake job and provider failure. Frontend verification and full backend
green status remain blocked by the environment/legacy failures above.

No branch was created. No commit, push, merge, or rebase was performed. No
SQLite records were manually edited; the database was changed only through the
Alembic upgrade/downgrade commands shown above.
