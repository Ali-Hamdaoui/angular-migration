# Acceptance Contract — G09 Final Assurance, Delivery, Reporting, and G13–G15

Every criterion below is mandatory unless the authoritative backlog explicitly marks it conditional.

## S4-F12 — Run independent final assurance and decide G13

### Exact feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Run independent final assurance and decide G13**, then the backend performs only the authorized service operation, persists the result, emits the documented **FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Final assurance metadata/results, source integrity status, gate/decisions, artifacts/events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G13 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G13 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.

### Exact feature Definition of Done

- Backend application service and domain rules are complete and invoked through one authoritative path.
- Frontend surface is complete in the same sprint and reads authoritative APIs/events only.
- API request/response and stable error contracts are documented.
- Alembic migration exists and rollback/upgrade is tested when schema changes.
- Expected artifacts are finalized, checksum-registered, immutable, and accessible by ID.
- Durable events are committed after/with state and replay correctly when applicable.
- Unit, API integration, frontend component, SSE/event, security/integrity, and regression tests pass as relevant.
- The documented UI manual scenario passes, including at least one negative case.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- No architecture authority is bypassed and relevant design/API/testing documentation is updated.

## S4-F13 — Create a delivery candidate and publish atomically through G14

### Exact feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Create a delivery candidate and publish atomically through G14**, then the backend performs only the authorized service operation, persists the result, emits the documented **DELIVERY_CANDIDATE_READY** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **delivery_records, output-root/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, output-root destination safety report, managed-output ownership report, G14 package, and publication record.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G14 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G14 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.
- **Repository/source isolation:** Given publication starts, when all paths are revalidated, then the external source and platform repository are read-only/out-of-scope and only registered product-owned candidate and destination aliases may be touched.
- **Destination contract:** Given publication succeeds, when the selected external output root is inspected, then `migrated-app/` exactly matches the approved candidate fingerprint and no temporary or partial final directory is presented as successful.
- **Source integrity:** Given the original source fingerprint differs from the G02-approved boundary, when G14 or publication is attempted, then delivery is blocked and the changed source is reported without mutation.

### Exact feature Definition of Done

- Backend application service and domain rules are complete and invoked through one authoritative path.
- Frontend surface is complete in the same sprint and reads authoritative APIs/events only.
- API request/response and stable error contracts are documented.
- Alembic migration exists and rollback/upgrade is tested when schema changes.
- Expected artifacts are finalized, checksum-registered, immutable, and accessible by ID.
- Durable events are committed after/with state and replay correctly when applicable.
- Unit, API integration, frontend component, SSE/event, security/integrity, and regression tests pass as relevant.
- The documented UI manual scenario passes, including at least one negative case.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- No architecture authority is bypassed and relevant design/API/testing documentation is updated.

## S4-F14 — Generate the deterministic evidence report, optional AI narrative, and decide G15

### Exact feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Generate, view, download, and accept the final evidence and cost report through G15**, then the backend performs only the authorized service operation, persists the result, emits the documented **REPORT_GENERATION_STARTED/READY/FAILED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Report metadata/version/checksum, aggregate usage/cost, gate decisions, completion transition.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G15 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G15 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.

### Exact feature Definition of Done

- Backend application service and domain rules are complete and invoked through one authoritative path.
- Frontend surface is complete in the same sprint and reads authoritative APIs/events only.
- API request/response and stable error contracts are documented.
- Alembic migration exists and rollback/upgrade is tested when schema changes.
- Expected artifacts are finalized, checksum-registered, immutable, and accessible by ID.
- Durable events are committed after/with state and replay correctly when applicable.
- Unit, API integration, frontend component, SSE/event, security/integrity, and regression tests pass as relevant.
- The documented UI manual scenario passes, including at least one negative case.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- No architecture authority is bypassed and relevant design/API/testing documentation is updated.

## Capability closeout

- All Jira task review cycles pass.
- Frozen contract conformance tests pass.
- Automated and mandatory manual validation pass.
- As-built documentation passes.
- Both final audits pass.
- Shared/database changes are recorded.
- `branch_ready=true` before push.
- `integration_verified=true` only after integrated evidence.
