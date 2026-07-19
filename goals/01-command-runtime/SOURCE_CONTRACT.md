# Authoritative Backlog Contracts — G01 Governed Command Runtime

The following sections are extracted verbatim from the supplied authoritative backlog. Shared operating rules add execution discipline but cannot weaken them.

<!-- S3-F01 sha256:2d4d257b6140e8e6cfa76f92b4d9fabab5fadf69e9ba9a514398a5a8bed04821 -->
### S3-F01 — Register structured commands and reject arbitrary shell execution

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Execution capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

An operator can inspect approved command templates and see raw shell strings, forbidden flags, invalid arguments, or out-of-scope workspaces rejected before execution.

#### Context

All execution must pass through a structured registry and policy engine; plans authorize command references, not arbitrary shell text.

**Governing specification sections:** 20, 40.1, 62.1-62.4, 68.4

#### Scope

Templates needed for npm ci, Angular update/version checks, build/test/lint and safe diagnostics, plus UI demonstration of rejection.

#### Out of scope

Starting processes, live logs, user-defined commands, PowerShell wrappers, and LLM command generation.

#### Backend slice

- **Application service/components:** StructuredCommandRegistry, executable/argument schemas, CommandPolicyEngine, plan membership checks, environment/network/working-directory policy, and shell=false enforcement.
- **Domain aggregate/projection:** CommandTemplate and CommandAuthorizationDecision.
- **Persistence:** Versioned command-template metadata and authorization audit records.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate`
- **Durable event:** COMMAND_AUTHORIZATION_ACCEPTED/REJECTED.
- **Artifact Store output:** Sanitized command authorization decision artifact for operator tests.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Command policy inspector showing template, expanded argv preview, policy checks, rejection reasons, and no free-form shell field.
- **Data source:** Typed FastAPI client plus authoritative state snapshot and durable SSE events where applicable.
- **User actions:** Only actions authorized by the API contract; mutating actions include observed state version and idempotency key.
- **Required visual states:** loading, empty, in progress, success, blocked, stale/conflict, reconnecting, backend failure, and authorization failure where applicable.
- **Refresh/reconnection:** Rehydrate from the backend snapshot, replay from the last durable event ID, ignore duplicates, and reload after an event gap.
- **Authority rule:** Button clicks may show a pending request indicator but never locally advance run, stage, step, approval, or repair status.

#### End-to-end flow

```text
User/reviewer/operator action
→ Next.js typed API request
→ FastAPI endpoint
→ StructuredCommandRegistry, executable/argument schemas, CommandPolicyEngine, plan membership checks, environment/network/working-directory policy, and shell=false enforcement.
→ Versioned command-template metadata and authorization audit records.
→ ArtifactService finalizes evidence: Sanitized command authorization decision artifact for operator tests.
→ Transition/Event service persists and emits: COMMAND_AUTHORIZATION_ACCEPTED/REJECTED.
→ SSE replay or snapshot refresh
→ Command policy inspector showing template, expanded argv preview, policy checks, rejection reasons, and no free-form shell field.
```

#### Sub-issues

- `S3-F01-I01` — Backend/application contract
- `S3-F01-I02` — Persistence, API, durable event, and artifact contract
- `S3-F01-I03` — Frontend projection and interaction
- `S3-F01-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Register structured commands and reject arbitrary shell execution**, then the backend performs only the authorized service operation, persists the result, emits the documented **COMMAND_AUTHORIZATION_ACCEPTED/REJECTED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Versioned command-template metadata and authorization audit records.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Sanitized command authorization decision artifact for operator tests.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Execution authority:** Given any attempt to bypass the registered command template, approved plan, exact profile, workspace alias, or `shell=false` policy, when authorization runs, then execution is rejected before process creation.

#### Manual end-to-end test scenario

**Preconditions:** S2-F07; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Command policy inspector showing template, expanded argv preview, policy checks, rejection reasons, and no free-form shell field.**.
3. Trigger the primary action for **Register structured commands and reject arbitrary shell execution** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** An operator can inspect approved command templates and see raw shell strings, forbidden flags, invalid arguments, or out-of-scope workspaces rejected before execution. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Versioned command-template metadata and authorization audit records.` are retrievable through `GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Sanitized command authorization decision artifact for operator tests.

**Expected durable event:** COMMAND_AUTHORIZATION_ACCEPTED/REJECTED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

#### Feature Definition of Done

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

#### Dependencies

S2-F07

#### Risks and edge cases

- Argument injection
- cmd/PowerShell wrapping
- path alias escape
- forbidden --force/--legacy-peer-deps
- environment smuggling
- and template drift.

---

<!-- S3-F02 sha256:826d5c0588d295487e54e153bfdc4f7296dcf34953c28cfb998713eab4e73661 -->
### S3-F02 — Execute one approved command and persist authoritative command evidence

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Execution capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A user can run one harmless approved diagnostic command inspect exact executable, argv, profile, working directory, timestamps, exit code, and immutable stdout/stderr evidence.

#### Context

CommandExecutor is the sole authoritative external-process path and must be proven before Angular mutation.

**Governing specification sections:** 9.4, 21, 53.9, 62.2-62.6, 62.11

#### Scope

One safe registered command end to end through the authoritative executor and UI.

#### Out of scope

Live log streaming, cancellation, interactive prompts, stage mutation, and arbitrary command selection.

#### Backend slice

- **Application service/components:** CommandExecutor, ProcessController basic launch, execution-profile materialization, workspace alias resolution, command ownership, timeout metadata, output capture, redaction, and result persistence.
- **Domain aggregate/projection:** CommandExecution.
- **Persistence:** command_executions with idempotency, state, runtime checksum, process metadata, and artifact references.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/commands; GET /api/v1/runs/{id}/commands/{commandId}`
- **Durable event:** COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED.
- **Artifact Store output:** Command manifest, full stdout, full stderr, combined ordered stream where available, and result report.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Command detail drawer with exact authorized command, lifecycle, evidence links, loading/running/success/failure states.
- **Data source:** Typed FastAPI client plus authoritative state snapshot and durable SSE events where applicable.
- **User actions:** Only actions authorized by the API contract; mutating actions include observed state version and idempotency key.
- **Required visual states:** loading, empty, in progress, success, blocked, stale/conflict, reconnecting, backend failure, and authorization failure where applicable.
- **Refresh/reconnection:** Rehydrate from the backend snapshot, replay from the last durable event ID, ignore duplicates, and reload after an event gap.
- **Authority rule:** Button clicks may show a pending request indicator but never locally advance run, stage, step, approval, or repair status.

#### End-to-end flow

```text
User/reviewer/operator action
→ Next.js typed API request
→ FastAPI endpoint
→ CommandExecutor, ProcessController basic launch, execution-profile materialization, workspace alias resolution, command ownership, timeout metadata, output capture, redaction, and result persistence.
→ command_executions with idempotency, state, runtime checksum, process metadata, and artifact references.
→ ArtifactService finalizes evidence: Command manifest, full stdout, full stderr, combined ordered stream where available, and result report.
→ Transition/Event service persists and emits: COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED.
→ SSE replay or snapshot refresh
→ Command detail drawer with exact authorized command, lifecycle, evidence links, loading/running/success/failure states.
```

#### Sub-issues

- `S3-F02-I01` — Backend/application contract
- `S3-F02-I02` — Persistence, API, durable event, and artifact contract
- `S3-F02-I03` — Frontend projection and interaction
- `S3-F02-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Execute one approved command and persist authoritative command evidence**, then the backend performs only the authorized service operation, persists the result, emits the documented **COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **command_executions with idempotency, state, runtime checksum, process metadata, and artifact references.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Command manifest, full stdout, full stderr, combined ordered stream where available, and result report.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Execution authority:** Given any attempt to bypass the registered command template, approved plan, exact profile, workspace alias, or `shell=false` policy, when authorization runs, then execution is rejected before process creation.

#### Manual end-to-end test scenario

**Preconditions:** S3-F01; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Command detail drawer with exact authorized command, lifecycle, evidence links, loading/running/success/failure states.**.
3. Trigger the primary action for **Execute one approved command and persist authoritative command evidence** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can run one harmless approved diagnostic command inspect exact executable, argv, profile, working directory, timestamps, exit code, and immutable stdout/stderr evidence. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `command_executions with idempotency, state, runtime checksum, process metadata, and artifact references.` are retrievable through `POST /api/v1/runs/{id}/commands; GET /api/v1/runs/{id}/commands/{commandId}` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Command manifest, full stdout, full stderr, combined ordered stream where available, and result report.

**Expected durable event:** COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

#### Feature Definition of Done

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

#### Dependencies

S3-F01

#### Risks and edge cases

- Duplicate execution
- mismatched runtime profile
- unbounded output
- secret leakage
- cwd escape
- orphan process
- and evidence registration after pass.

---

<!-- S3-F03 sha256:c7cc38e104e832ad4b61cf005f36c5d4e0ecc476175531dcfc55678a6f808e45 -->
### S3-F03 — Stream live command logs and recover after browser reconnect

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Execution capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A user can tail stdout/stderr for a running command, pause the viewer without stopping execution, refresh, and resume from durable command state and stored logs.

#### Context

Long installs and builds need transparent progress, but live chunks are not the authoritative log evidence.

**Governing specification sections:** 21.1, 36.4, 62.6, 66.5-66.6

#### Scope

Live and stored log viewing, browser refresh/reconnect, bounded buffers, and durable final evidence.

#### Out of scope

Terminal input, interactive command response, log editing, and cross-run aggregation.

#### Backend slice

- **Application service/components:** Bounded log-chunk publisher, sequence metadata, SSE command events, final artifact linkage, pagination/search endpoint for stored logs, and backpressure controls.
- **Domain aggregate/projection:** CommandExecution plus non-authoritative LogChunk projection.
- **Persistence:** Command event metadata only; complete logs remain artifacts.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `GET /api/v1/runs/{id}/commands/{commandId}/logs; existing SSE endpoint emits COMMAND_OUTPUT_AVAILABLE.`
- **Durable event:** COMMAND_OUTPUT_AVAILABLE with offsets/sequence, followed by final command event.
- **Artifact Store output:** Full immutable stdout/stderr logs with truncation metadata for UI stream.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Custom log viewer with stdout/stderr filters, tail/pause/search, reconnect indicator, dropped-chunk warning, stored-log pagination, and final result link.
- **Data source:** Typed FastAPI client plus authoritative state snapshot and durable SSE events where applicable.
- **User actions:** Only actions authorized by the API contract; mutating actions include observed state version and idempotency key.
- **Required visual states:** loading, empty, in progress, success, blocked, stale/conflict, reconnecting, backend failure, and authorization failure where applicable.
- **Refresh/reconnection:** Rehydrate from the backend snapshot, replay from the last durable event ID, ignore duplicates, and reload after an event gap.
- **Authority rule:** Button clicks may show a pending request indicator but never locally advance run, stage, step, approval, or repair status.

#### End-to-end flow

```text
User/reviewer/operator action
→ Next.js typed API request
→ FastAPI endpoint
→ Bounded log-chunk publisher, sequence metadata, SSE command events, final artifact linkage, pagination/search endpoint for stored logs, and backpressure controls.
→ Command event metadata only; complete logs remain artifacts.
→ ArtifactService finalizes evidence: Full immutable stdout/stderr logs with truncation metadata for UI stream.
→ Transition/Event service persists and emits: COMMAND_OUTPUT_AVAILABLE with offsets/sequence, followed by final command event.
→ SSE replay or snapshot refresh
→ Custom log viewer with stdout/stderr filters, tail/pause/search, reconnect indicator, dropped-chunk warning, stored-log pagination, and final result link.
```

#### Sub-issues

- `S3-F03-I01` — Backend/application contract
- `S3-F03-I02` — Persistence, API, durable event, and artifact contract
- `S3-F03-I03` — Frontend projection and interaction
- `S3-F03-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Stream live command logs and recover after browser reconnect**, then the backend performs only the authorized service operation, persists the result, emits the documented **COMMAND_OUTPUT_AVAILABLE** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Command event metadata only; complete logs remain artifacts.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Full immutable stdout/stderr logs with truncation metadata for UI stream.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Execution authority:** Given any attempt to bypass the registered command template, approved plan, exact profile, workspace alias, or `shell=false` policy, when authorization runs, then execution is rejected before process creation.

#### Manual end-to-end test scenario

**Preconditions:** S3-F02; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Custom log viewer with stdout/stderr filters, tail/pause/search, reconnect indicator, dropped-chunk warning, stored-log pagination, and final result link.**.
3. Trigger the primary action for **Stream live command logs and recover after browser reconnect** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can tail stdout/stderr for a running command, pause the viewer without stopping execution, refresh, and resume from durable command state and stored logs. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Command event metadata only; complete logs remain artifacts.` are retrievable through `GET /api/v1/runs/{id}/commands/{commandId}/logs; existing SSE endpoint emits COMMAND_OUTPUT_AVAILABLE.` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Full immutable stdout/stderr logs with truncation metadata for UI stream.

**Expected durable event:** COMMAND_OUTPUT_AVAILABLE with offsets/sequence, followed by final command event.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

#### Feature Definition of Done

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

#### Dependencies

S3-F02

#### Risks and edge cases

- Memory pressure
- event flood
- dropped chunks
- ordering mismatch
- ANSI/control characters
- secret redaction
- and browser treating log text as state.

---

<!-- S3-F04 sha256:4d05cd99308b116c2dd6f61e506e66ad5d150ec224d2317d3c10ffb61dc32e37 -->
### S3-F04 — Own commands with JobSupervisor, leases, timeout, and explicit cancellation

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Operational capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A user can cancel a controlled long-running command, see graceful then forced process-tree termination, partial evidence, and an honest interrupted/cancelled workspace classification.

#### Context

Browser disconnect must not cancel work, but explicit user cancellation must stop scheduling and terminate the complete process tree safely.

**Governing specification sections:** 21, 33, 53.2, 62.7-62.9, 69.3, 70.6

#### Scope

One active run/command ownership, heartbeat, timeout, process-tree cancellation, partial evidence, and UI.

#### Out of scope

Full startup reconciliation, resume after crash, multi-worker scheduling, and repair rollback.

#### Backend slice

- **Application service/components:** JobSupervisor active-command ownership, WorkerLease heartbeat/expiry, ProcessController process-tree termination, timeout, cancel idempotency, mutation-category recovery classification, and Transition Service cancellation.
- **Domain aggregate/projection:** WorkerLease, CommandExecution, MigrationRun cancellation fields.
- **Persistence:** worker_leases, command cancellation metadata, run/step states, durable events.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/cancel; GET /api/v1/runs/{id}/active-command`
- **Durable event:** RUN_CANCEL_REQUESTED, COMMAND_CANCELLED/INTERRUPTED, RUN_CANCELLED.
- **Artifact Store output:** Partial logs, process-termination report, workspace trust/recovery classification, and partial cancellation summary.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Cancel action with confirmation, cancelling status, process result, partial evidence links, blocked duplicate action, and reconnect-safe state.
- **Data source:** Typed FastAPI client plus authoritative state snapshot and durable SSE events where applicable.
- **User actions:** Only actions authorized by the API contract; mutating actions include observed state version and idempotency key.
- **Required visual states:** loading, empty, in progress, success, blocked, stale/conflict, reconnecting, backend failure, and authorization failure where applicable.
- **Refresh/reconnection:** Rehydrate from the backend snapshot, replay from the last durable event ID, ignore duplicates, and reload after an event gap.
- **Authority rule:** Button clicks may show a pending request indicator but never locally advance run, stage, step, approval, or repair status.

#### End-to-end flow

```text
User/reviewer/operator action
→ Next.js typed API request
→ FastAPI endpoint
→ JobSupervisor active-command ownership, WorkerLease heartbeat/expiry, ProcessController process-tree termination, timeout, cancel idempotency, mutation-category recovery classification, and Transition Service cancellation.
→ worker_leases, command cancellation metadata, run/step states, durable events.
→ ArtifactService finalizes evidence: Partial logs, process-termination report, workspace trust/recovery classification, and partial cancellation summary.
→ Transition/Event service persists and emits: RUN_CANCEL_REQUESTED, COMMAND_CANCELLED/INTERRUPTED, RUN_CANCELLED.
→ SSE replay or snapshot refresh
→ Cancel action with confirmation, cancelling status, process result, partial evidence links, blocked duplicate action, and reconnect-safe state.
```

#### Sub-issues

- `S3-F04-I01` — Backend/application contract
- `S3-F04-I02` — Persistence, API, durable event, and artifact contract
- `S3-F04-I03` — Frontend projection and interaction
- `S3-F04-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Own commands with JobSupervisor, leases, timeout, and explicit cancellation**, then the backend performs only the authorized service operation, persists the result, emits the documented **RUN_CANCEL_REQUESTED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **worker_leases, command cancellation metadata, run/step states, durable events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Partial logs, process-termination report, workspace trust/recovery classification, and partial cancellation summary.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Execution authority:** Given any attempt to bypass the registered command template, approved plan, exact profile, workspace alias, or `shell=false` policy, when authorization runs, then execution is rejected before process creation.

#### Manual end-to-end test scenario

**Preconditions:** S3-F02, S3-F03; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Cancel action with confirmation, cancelling status, process result, partial evidence links, blocked duplicate action, and reconnect-safe state.**.
3. Trigger the primary action for **Own commands with JobSupervisor, leases, timeout, and explicit cancellation** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can cancel a controlled long-running command, see graceful then forced process-tree termination, partial evidence, and an honest interrupted/cancelled workspace classification. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `worker_leases, command cancellation metadata, run/step states, durable events.` are retrievable through `POST /api/v1/runs/{id}/cancel; GET /api/v1/runs/{id}/active-command` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Partial logs, process-termination report, workspace trust/recovery classification, and partial cancellation summary.

**Expected durable event:** RUN_CANCEL_REQUESTED, COMMAND_CANCELLED/INTERRUPTED, RUN_CANCELLED.

**Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.

**Cleanup:** Cancel or complete the test run through the product, retain immutable evidence, and delete only product-owned disposable test workspaces through the approved cleanup action.

#### Feature Definition of Done

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

#### Dependencies

S3-F02, S3-F03

#### Risks and edge cases

- PID reuse
- descendant escape
- cancellation race at completion
- stale lease
- locked files
- mutating command interruption
- and false claim of terminated tree.

---
