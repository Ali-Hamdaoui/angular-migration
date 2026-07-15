
## Sprint 3 — Controlled Command Execution, Stage Pipeline, Validation, Approvals, Cancellation, and Copy-Forward

### D.3.1 Sprint goal

Build the trusted execution path and prove complete controlled Angular major-version stages with logs, transformation review, validation, cancellation, sealing, and stage-to-stage copy-forward.

### D.3.2 Sprint boundaries

Includes command registry/policy/executor/process control, live logs, leases/cancellation, run-scoped stage sandboxes, G07/G08/G09/G12, update/validation steps, copy-forward, and a parameterized 18→19→20→21 passing path. Full LLM repair is deferred to Sprint 4.

### D.3.3 Features in implementation order


1. **S3-F01 — Register structured commands and reject arbitrary shell execution** (Execution capability, Must)

2. **S3-F02 — Execute one approved command and persist authoritative command evidence** (Execution capability, Must)

3. **S3-F03 — Stream live command logs and recover after browser reconnect** (Execution capability, Must)

4. **S3-F04 — Own commands with JobSupervisor, leases, timeout, and explicit cancellation** (Operational capability, Must)

5. **S3-F05 — Prepare a dedicated run-scoped stage sandbox and decide G07 stage start** (Approval capability, Must)

6. **S3-F06 — Run the stage bootstrap clean install** (Execution capability, Must)

7. **S3-F07 — Execute the exact Angular update and verify the target version** (Execution capability, Must)

8. **S3-F08 — Capture transformation diffs and classify changed-file risk** (Validation capability, Must)

9. **S3-F09 — Review and decide G08 transformation acceptance** (Approval capability, Must)

10. **S3-F10 — Run final clean install and deterministic static checks** (Validation capability, Must)

11. **S3-F11 — Run and inspect the required stage build matrix** (Validation capability, Must)

12. **S3-F12 — Run complete stage tests and conditional lint** (Validation capability, Must)

13. **S3-F13 — Compare parity evidence, display assurance, and decide G09 validation acceptance** (Approval capability, Must)

14. **S3-F14 — Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21** (Approval capability, Must)


### D.3.4 Full feature and sub-issue details

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

#### Detailed sub-issues

#### S3-F01-I01 — Implement backend application contract for Register structured commands and reject arbitrary shell execution

  - **Parent feature:** S3-F01
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Register structured commands and reject arbitrary shell execution so the feature has one authoritative service path.
  - **Context:** All execution must pass through a structured registry and policy engine; plans authorize command references, not arbitrary shell text.
  - **Scope:** StructuredCommandRegistry, executable/argument schemas, CommandPolicyEngine, plan membership checks, environment/network/working-directory policy, and shell=false enforcement.
  - **Out of scope:** Starting processes, live logs, user-defined commands, PowerShell wrappers, and LLM command generation.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: StructuredCommandRegistry, executable/argument schemas, CommandPolicyEngine, plan membership checks, environment/network/working-directory policy, and shell=false enforcement.
  - **Database impact:** Use or introduce the records summarized by: Versioned command-template metadata and authorization audit records.
  - **API impact:** Define service-facing request/response models supporting: GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate
  - **Event impact:** Request durable events only through the transition/event service: COMMAND_AUTHORIZATION_ACCEPTED/REJECTED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Sanitized command authorization decision artifact for operator tests.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Argument injection, cmd/PowerShell wrapping, path alias escape, forbidden --force/--legacy-peer-deps, environment smuggling, and template drift.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S2-F07
  - **Suggested labels:** sprint-3, s3-f01, execution-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S3-F01-I02 — Persist and expose evidence contracts for Register structured commands and reject arbitrary shell execution

  - **Parent feature:** S3-F01
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Register structured commands and reject arbitrary shell execution observable and auditable.
  - **Context:** All execution must pass through a structured registry and policy engine; plans authorize command references, not arbitrary shell text.
  - **Scope:** Persistence: Versioned command-template metadata and authorization audit records. API: GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate. Events: COMMAND_AUTHORIZATION_ACCEPTED/REJECTED. Artifacts: Sanitized command authorization decision artifact for operator tests.
  - **Out of scope:** Starting processes, live logs, user-defined commands, PowerShell wrappers, and LLM command generation.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Versioned command-template metadata and authorization audit records.
  - **API impact:** Implement and document: GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: COMMAND_AUTHORIZATION_ACCEPTED/REJECTED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Sanitized command authorization decision artifact for operator tests.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F01-I01
  - **Suggested labels:** sprint-3, s3-f01, execution-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S3-F01-I03 — Build frontend experience for Register structured commands and reject arbitrary shell execution

  - **Parent feature:** S3-F01
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Register structured commands and reject arbitrary shell execution, using backend snapshots and durable events only.
  - **Context:** All execution must pass through a structured registry and policy engine; plans authorize command references, not arbitrary shell text.
  - **Scope:** Command policy inspector showing template, expanded argv preview, policy checks, rejection reasons, and no free-form shell field.
  - **Out of scope:** Starting processes, live logs, user-defined commands, PowerShell wrappers, and LLM command generation.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate` plus durable events `COMMAND_AUTHORIZATION_ACCEPTED/REJECTED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Command policy inspector showing template, expanded argv preview, policy checks, rejection reasons, and no free-form shell field.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `COMMAND_AUTHORIZATION_ACCEPTED/REJECTED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Sanitized command authorization decision artifact for operator tests.
  - **UI impact:** Implement: Command policy inspector showing template, expanded argv preview, policy checks, rejection reasons, and no free-form shell field.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F01-I02
  - **Suggested labels:** sprint-3, s3-f01, execution-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F01-I04 — Verify and document Register structured commands and reject arbitrary shell execution

  - **Parent feature:** S3-F01
  - **Issue type:** Testing
  - **Technical story:** Prove Register structured commands and reject arbitrary shell execution through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** All execution must pass through a structured registry and policy engine; plans authorize command references, not arbitrary shell text.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Starting processes, live logs, user-defined commands, PowerShell wrappers, and LLM command generation.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `GET /api/v1/operator/command-templates; POST /api/v1/operator/command-policy/validate` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `COMMAND_AUTHORIZATION_ACCEPTED/REJECTED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Sanitized command authorization decision artifact for operator tests.` where applicable.
  - **UI impact:** Execute the feature through `Command policy inspector showing template, expanded argv preview, policy checks, rejection reasons, and no free-form shell field.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Argument injection, cmd/PowerShell wrapping, path alias escape, forbidden --force/--legacy-peer-deps, environment smuggling, and template drift.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F01-I03
  - **Suggested labels:** sprint-3, s3-f01, execution-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---

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

#### Detailed sub-issues

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

#### S3-F02-I02 — Persist and expose evidence contracts for Execute one approved command and persist authoritative command evidence

  - **Parent feature:** S3-F02
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Execute one approved command and persist authoritative command evidence observable and auditable.
  - **Context:** CommandExecutor is the sole authoritative external-process path and must be proven before Angular mutation.
  - **Scope:** Persistence: command_executions with idempotency, state, runtime checksum, process metadata, and artifact references. API: POST /api/v1/runs/{id}/commands; GET /api/v1/runs/{id}/commands/{commandId}. Events: COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED. Artifacts: Command manifest, full stdout, full stderr, combined ordered stream where available, and result report.
  - **Out of scope:** Live log streaming, cancellation, interactive prompts, stage mutation, and arbitrary command selection.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: command_executions with idempotency, state, runtime checksum, process metadata, and artifact references.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/commands; GET /api/v1/runs/{id}/commands/{commandId}; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Command manifest, full stdout, full stderr, combined ordered stream where available, and result report.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F02-I01
  - **Suggested labels:** sprint-3, s3-f02, execution-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S3-F02-I03 — Build frontend experience for Execute one approved command and persist authoritative command evidence

  - **Parent feature:** S3-F02
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Execute one approved command and persist authoritative command evidence, using backend snapshots and durable events only.
  - **Context:** CommandExecutor is the sole authoritative external-process path and must be proven before Angular mutation.
  - **Scope:** Command detail drawer with exact authorized command, lifecycle, evidence links, loading/running/success/failure states.
  - **Out of scope:** Live log streaming, cancellation, interactive prompts, stage mutation, and arbitrary command selection.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/commands; GET /api/v1/runs/{id}/commands/{commandId}` plus durable events `COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Command detail drawer with exact authorized command, lifecycle, evidence links, loading/running/success/failure states.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/commands; GET /api/v1/runs/{id}/commands/{commandId}` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Command manifest, full stdout, full stderr, combined ordered stream where available, and result report.
  - **UI impact:** Implement: Command detail drawer with exact authorized command, lifecycle, evidence links, loading/running/success/failure states.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F02-I02
  - **Suggested labels:** sprint-3, s3-f02, execution-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F02-I04 — Verify and document Execute one approved command and persist authoritative command evidence

  - **Parent feature:** S3-F02
  - **Issue type:** Testing
  - **Technical story:** Prove Execute one approved command and persist authoritative command evidence through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** CommandExecutor is the sole authoritative external-process path and must be proven before Angular mutation.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Live log streaming, cancellation, interactive prompts, stage mutation, and arbitrary command selection.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/commands; GET /api/v1/runs/{id}/commands/{commandId}` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Command manifest, full stdout, full stderr, combined ordered stream where available, and result report.` where applicable.
  - **UI impact:** Execute the feature through `Command detail drawer with exact authorized command, lifecycle, evidence links, loading/running/success/failure states.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Duplicate execution, mismatched runtime profile, unbounded output, secret leakage, cwd escape, orphan process, and evidence registration after pass.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F02-I03
  - **Suggested labels:** sprint-3, s3-f02, execution-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---

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

#### Detailed sub-issues

#### S3-F03-I01 — Implement backend application contract for Stream live command logs and recover after browser reconnect

  - **Parent feature:** S3-F03
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Stream live command logs and recover after browser reconnect so the feature has one authoritative service path.
  - **Context:** Long installs and builds need transparent progress, but live chunks are not the authoritative log evidence.
  - **Scope:** Bounded log-chunk publisher, sequence metadata, SSE command events, final artifact linkage, pagination/search endpoint for stored logs, and backpressure controls.
  - **Out of scope:** Terminal input, interactive command response, log editing, and cross-run aggregation.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `GET /api/v1/runs/{id}/commands/{commandId}/logs; existing SSE endpoint emits COMMAND_OUTPUT_AVAILABLE.`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: Bounded log-chunk publisher, sequence metadata, SSE command events, final artifact linkage, pagination/search endpoint for stored logs, and backpressure controls.
  - **Database impact:** Use or introduce the records summarized by: Command event metadata only; complete logs remain artifacts.
  - **API impact:** Define service-facing request/response models supporting: GET /api/v1/runs/{id}/commands/{commandId}/logs; existing SSE endpoint emits COMMAND_OUTPUT_AVAILABLE.
  - **Event impact:** Request durable events only through the transition/event service: COMMAND_OUTPUT_AVAILABLE with offsets/sequence, followed by final command event.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Full immutable stdout/stderr logs with truncation metadata for UI stream.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Memory pressure, event flood, dropped chunks, ordering mismatch, ANSI/control characters, secret redaction, and browser treating log text as state.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F02
  - **Suggested labels:** sprint-3, s3-f03, execution-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S3-F03-I02 — Persist and expose evidence contracts for Stream live command logs and recover after browser reconnect

  - **Parent feature:** S3-F03
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Stream live command logs and recover after browser reconnect observable and auditable.
  - **Context:** Long installs and builds need transparent progress, but live chunks are not the authoritative log evidence.
  - **Scope:** Persistence: Command event metadata only; complete logs remain artifacts. API: GET /api/v1/runs/{id}/commands/{commandId}/logs; existing SSE endpoint emits COMMAND_OUTPUT_AVAILABLE. Events: COMMAND_OUTPUT_AVAILABLE with offsets/sequence, followed by final command event. Artifacts: Full immutable stdout/stderr logs with truncation metadata for UI stream.
  - **Out of scope:** Terminal input, interactive command response, log editing, and cross-run aggregation.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Command event metadata only; complete logs remain artifacts.
  - **API impact:** Implement and document: GET /api/v1/runs/{id}/commands/{commandId}/logs; existing SSE endpoint emits COMMAND_OUTPUT_AVAILABLE.; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: COMMAND_OUTPUT_AVAILABLE with offsets/sequence, followed by final command event.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Full immutable stdout/stderr logs with truncation metadata for UI stream.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F03-I01
  - **Suggested labels:** sprint-3, s3-f03, execution-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S3-F03-I03 — Build frontend experience for Stream live command logs and recover after browser reconnect

  - **Parent feature:** S3-F03
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Stream live command logs and recover after browser reconnect, using backend snapshots and durable events only.
  - **Context:** Long installs and builds need transparent progress, but live chunks are not the authoritative log evidence.
  - **Scope:** Custom log viewer with stdout/stderr filters, tail/pause/search, reconnect indicator, dropped-chunk warning, stored-log pagination, and final result link.
  - **Out of scope:** Terminal input, interactive command response, log editing, and cross-run aggregation.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `GET /api/v1/runs/{id}/commands/{commandId}/logs; existing SSE endpoint emits COMMAND_OUTPUT_AVAILABLE.` plus durable events `COMMAND_OUTPUT_AVAILABLE with offsets/sequence, followed by final command event.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Custom log viewer with stdout/stderr filters, tail/pause/search, reconnect indicator, dropped-chunk warning, stored-log pagination, and final result link.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `GET /api/v1/runs/{id}/commands/{commandId}/logs; existing SSE endpoint emits COMMAND_OUTPUT_AVAILABLE.` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `COMMAND_OUTPUT_AVAILABLE with offsets/sequence, followed by final command event.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Full immutable stdout/stderr logs with truncation metadata for UI stream.
  - **UI impact:** Implement: Custom log viewer with stdout/stderr filters, tail/pause/search, reconnect indicator, dropped-chunk warning, stored-log pagination, and final result link.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F03-I02
  - **Suggested labels:** sprint-3, s3-f03, execution-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F03-I04 — Verify and document Stream live command logs and recover after browser reconnect

  - **Parent feature:** S3-F03
  - **Issue type:** Testing
  - **Technical story:** Prove Stream live command logs and recover after browser reconnect through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Long installs and builds need transparent progress, but live chunks are not the authoritative log evidence.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Terminal input, interactive command response, log editing, and cross-run aggregation.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `GET /api/v1/runs/{id}/commands/{commandId}/logs; existing SSE endpoint emits COMMAND_OUTPUT_AVAILABLE.` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `COMMAND_OUTPUT_AVAILABLE with offsets/sequence, followed by final command event.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Full immutable stdout/stderr logs with truncation metadata for UI stream.` where applicable.
  - **UI impact:** Execute the feature through `Custom log viewer with stdout/stderr filters, tail/pause/search, reconnect indicator, dropped-chunk warning, stored-log pagination, and final result link.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Memory pressure, event flood, dropped chunks, ordering mismatch, ANSI/control characters, secret redaction, and browser treating log text as state.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F03-I03
  - **Suggested labels:** sprint-3, s3-f03, execution-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---

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

#### Detailed sub-issues

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

#### S3-F04-I02 — Persist and expose evidence contracts for Own commands with JobSupervisor, leases, timeout, and explicit cancellation

  - **Parent feature:** S3-F04
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Own commands with JobSupervisor, leases, timeout, and explicit cancellation observable and auditable.
  - **Context:** Browser disconnect must not cancel work, but explicit user cancellation must stop scheduling and terminate the complete process tree safely.
  - **Scope:** Persistence: worker_leases, command cancellation metadata, run/step states, durable events. API: POST /api/v1/runs/{id}/cancel; GET /api/v1/runs/{id}/active-command. Events: RUN_CANCEL_REQUESTED, COMMAND_CANCELLED/INTERRUPTED, RUN_CANCELLED. Artifacts: Partial logs, process-termination report, workspace trust/recovery classification, and partial cancellation summary.
  - **Out of scope:** Full startup reconciliation, resume after crash, multi-worker scheduling, and repair rollback.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: worker_leases, command cancellation metadata, run/step states, durable events.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/cancel; GET /api/v1/runs/{id}/active-command; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: RUN_CANCEL_REQUESTED, COMMAND_CANCELLED/INTERRUPTED, RUN_CANCELLED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Partial logs, process-termination report, workspace trust/recovery classification, and partial cancellation summary.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F04-I01
  - **Suggested labels:** sprint-3, s3-f04, operational-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S3-F04-I03 — Build frontend experience for Own commands with JobSupervisor, leases, timeout, and explicit cancellation

  - **Parent feature:** S3-F04
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Own commands with JobSupervisor, leases, timeout, and explicit cancellation, using backend snapshots and durable events only.
  - **Context:** Browser disconnect must not cancel work, but explicit user cancellation must stop scheduling and terminate the complete process tree safely.
  - **Scope:** Cancel action with confirmation, cancelling status, process result, partial evidence links, blocked duplicate action, and reconnect-safe state.
  - **Out of scope:** Full startup reconciliation, resume after crash, multi-worker scheduling, and repair rollback.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/cancel; GET /api/v1/runs/{id}/active-command` plus durable events `RUN_CANCEL_REQUESTED, COMMAND_CANCELLED/INTERRUPTED, RUN_CANCELLED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Cancel action with confirmation, cancelling status, process result, partial evidence links, blocked duplicate action, and reconnect-safe state.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/cancel; GET /api/v1/runs/{id}/active-command` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `RUN_CANCEL_REQUESTED, COMMAND_CANCELLED/INTERRUPTED, RUN_CANCELLED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Partial logs, process-termination report, workspace trust/recovery classification, and partial cancellation summary.
  - **UI impact:** Implement: Cancel action with confirmation, cancelling status, process result, partial evidence links, blocked duplicate action, and reconnect-safe state.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F04-I02
  - **Suggested labels:** sprint-3, s3-f04, operational-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F04-I04 — Verify and document Own commands with JobSupervisor, leases, timeout, and explicit cancellation

  - **Parent feature:** S3-F04
  - **Issue type:** Testing
  - **Technical story:** Prove Own commands with JobSupervisor, leases, timeout, and explicit cancellation through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Browser disconnect must not cancel work, but explicit user cancellation must stop scheduling and terminate the complete process tree safely.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Full startup reconciliation, resume after crash, multi-worker scheduling, and repair rollback.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/cancel; GET /api/v1/runs/{id}/active-command` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `RUN_CANCEL_REQUESTED, COMMAND_CANCELLED/INTERRUPTED, RUN_CANCELLED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Partial logs, process-termination report, workspace trust/recovery classification, and partial cancellation summary.` where applicable.
  - **UI impact:** Execute the feature through `Cancel action with confirmation, cancelling status, process result, partial evidence links, blocked duplicate action, and reconnect-safe state.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: PID reuse, descendant escape, cancellation race at completion, stale lease, locked files, mutating command interruption, and false claim of terminated tree.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F04-I03
  - **Suggested labels:** sprint-3, s3-f04, operational-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---

### S3-F05 — Prepare a dedicated run-scoped stage sandbox and decide G07 stage start

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Approval capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G07

#### User-observable outcome

A reviewer can inspect the current stage input fingerprint, exact resolved plan/profile, registered external stage-sandbox destination, and risks, approve G07, and then create the isolated run-scoped stage sandbox under the selected output root.

#### Context

Every major transition starts from an approved clean boundary and has its own physical workspace.

**Governing specification sections:** 14, 19, 23, 56.8, 61.1-61.4

#### Scope

G07, exact current-stage locking, dedicated sandbox creation after approval, and UI.

#### Out of scope

Bootstrap install, Angular update, stage validation, and copy-forward.

#### Backend slice

- **Application service/components:** StagePreparationService, current-version re-detection, later-stage exact resolution hook, StageExecutionPlan lock, G07 package, WorkspaceManager stage-copy operation into the registered `STAGE_SANDBOX` alias at `<resolved-output-root>/.migration-factory/runs/<run-id>/sandboxes/stages/<stage-key>`, fingerprint validation, and lease checks.
- **Domain aggregate/projection:** MigrationStage, StageExecutionPlan active version, ApprovalGate G07, WorkspaceFingerprint.
- **Persistence:** migration_stages, active stage plan, workspace/fingerprint records, gate decisions.
- **State/approval rule:** G07 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/stages/{stageId}/prepare; POST /api/v1/runs/{id}/approvals/G07/decisions; POST /api/v1/runs/{id}/stages/{stageId}/sandbox`
- **Durable event:** STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY.
- **Artifact Store output:** Stage-start package, exact plan/profile, copy report, input manifest, input fingerprint, and sandbox verification.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Stage-start review page with plan/profile/input tabs, workspace alias, risk notices, G07 controls, copy progress, and ready/blocked states.
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
→ StagePreparationService, current-version re-detection, later-stage exact resolution hook, StageExecutionPlan lock, G07 package, WorkspaceManager stage-copy operation, fingerprint validation, and lease checks.
→ migration_stages, active stage plan, workspace/fingerprint records, gate decisions.
→ ArtifactService finalizes evidence: Stage-start package, exact plan/profile, copy report, input manifest, input fingerprint, and sandbox verification.
→ Transition/Event service persists and emits: STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY.
→ SSE replay or snapshot refresh
→ Stage-start review page with plan/profile/input tabs, workspace alias, risk notices, G07 controls, copy progress, and ready/blocked states.
```

#### Sub-issues

- `S3-F05-I01` — Backend/application contract
- `S3-F05-I02` — Persistence, API, durable event, and artifact contract
- `S3-F05-I03` — Frontend projection and interaction
- `S3-F05-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Prepare a dedicated run-scoped stage sandbox and decide G07 stage start**, then the backend performs only the authorized service operation, persists the result, emits the documented **STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **migration_stages, active stage plan, workspace/fingerprint records, gate decisions.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Stage-start package, exact plan/profile, copy report, input manifest, input fingerprint, and sandbox verification.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G07 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G07 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.
- **Source safety:** Given the feature completes, when the original source fingerprint is recalculated, then it equals the approved pre-operation fingerprint; any mismatch enters diagnostic hold.

#### Manual end-to-end test scenario

**Preconditions:** S2-F07, S3-F04; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Stage-start review page with plan/profile/input tabs, workspace alias, risk notices, G07 controls, copy progress, and ready/blocked states.**.
    3. Trigger the primary action for **Prepare a dedicated run-scoped stage sandbox and decide G07 stage start** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G07** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can inspect the current stage input fingerprint, exact resolved plan/profile, registered external stage-sandbox destination, and risks, approve G07, and then create the isolated run-scoped stage sandbox under the selected output root. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `migration_stages, active stage plan, workspace/fingerprint records, gate decisions.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/prepare; POST /api/v1/runs/{id}/approvals/G07/decisions; POST /api/v1/runs/{id}/stages/{stageId}/sandbox` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Stage-start package, exact plan/profile, copy report, input manifest, input fingerprint, and sandbox verification.

    **Expected durable event:** STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G07 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

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

S2-F07, S3-F04

#### Risks and edge cases

- Stale prior-stage output
- plan drift
- approval before fingerprint
- sandbox collision
- copy interruption
- active lease conflict
- and source link escape.

#### Detailed sub-issues

#### S3-F05-I01 — Implement backend application contract for Prepare a dedicated run-scoped stage sandbox and decide G07 stage start

  - **Parent feature:** S3-F05
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Prepare a dedicated run-scoped stage sandbox and decide G07 stage start so the feature has one authoritative service path.
  - **Context:** Every major transition starts from an approved clean boundary and has its own physical workspace.
  - **Scope:** StagePreparationService, current-version re-detection, later-stage exact resolution hook, StageExecutionPlan lock, G07 package, WorkspaceManager stage-copy operation, fingerprint validation, and lease checks.
  - **Out of scope:** Bootstrap install, Angular update, stage validation, and copy-forward.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G07 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/prepare; POST /api/v1/runs/{id}/approvals/G07/decisions; POST /api/v1/runs/{id}/stages/{stageId}/sandbox`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: StagePreparationService, current-version re-detection, later-stage exact resolution hook, StageExecutionPlan lock, G07 package, WorkspaceManager stage-copy operation, fingerprint validation, and lease checks.
  - **Database impact:** Use or introduce the records summarized by: migration_stages, active stage plan, workspace/fingerprint records, gate decisions.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/prepare; POST /api/v1/runs/{id}/approvals/G07/decisions; POST /api/v1/runs/{id}/stages/{stageId}/sandbox
  - **Event impact:** Request durable events only through the transition/event service: STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Stage-start package, exact plan/profile, copy report, input manifest, input fingerprint, and sandbox verification.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Stale prior-stage output, plan drift, approval before fingerprint, sandbox collision, copy interruption, active lease conflict, and source link escape.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G07 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S2-F07, S3-F04
  - **Suggested labels:** sprint-3, s3-f05, approval-capability, backend, g07, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F05-I02 — Persist and expose evidence contracts for Prepare a dedicated run-scoped stage sandbox and decide G07 stage start

  - **Parent feature:** S3-F05
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Prepare a dedicated run-scoped stage sandbox and decide G07 stage start observable and auditable.
  - **Context:** Every major transition starts from an approved clean boundary and has its own physical workspace.
  - **Scope:** Persistence: migration_stages, active stage plan, workspace/fingerprint records, gate decisions. API: POST /api/v1/runs/{id}/stages/{stageId}/prepare; POST /api/v1/runs/{id}/approvals/G07/decisions; POST /api/v1/runs/{id}/stages/{stageId}/sandbox. Events: STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY. Artifacts: Stage-start package, exact plan/profile, copy report, input manifest, input fingerprint, and sandbox verification.
  - **Out of scope:** Bootstrap install, Angular update, stage validation, and copy-forward.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: migration_stages, active stage plan, workspace/fingerprint records, gate decisions.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/stages/{stageId}/prepare; POST /api/v1/runs/{id}/approvals/G07/decisions; POST /api/v1/runs/{id}/stages/{stageId}/sandbox; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Stage-start package, exact plan/profile, copy report, input manifest, input fingerprint, and sandbox verification.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G07 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F05-I01
  - **Suggested labels:** sprint-3, s3-f05, approval-capability, api, g07, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F05-I03 — Build frontend experience for Prepare a dedicated run-scoped stage sandbox and decide G07 stage start

  - **Parent feature:** S3-F05
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Prepare a dedicated run-scoped stage sandbox and decide G07 stage start, using backend snapshots and durable events only.
  - **Context:** Every major transition starts from an approved clean boundary and has its own physical workspace.
  - **Scope:** Stage-start review page with plan/profile/input tabs, workspace alias, risk notices, G07 controls, copy progress, and ready/blocked states.
  - **Out of scope:** Bootstrap install, Angular update, stage validation, and copy-forward.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/prepare; POST /api/v1/runs/{id}/approvals/G07/decisions; POST /api/v1/runs/{id}/stages/{stageId}/sandbox` plus durable events `STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Stage-start review page with plan/profile/input tabs, workspace alias, risk notices, G07 controls, copy progress, and ready/blocked states.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/prepare; POST /api/v1/runs/{id}/approvals/G07/decisions; POST /api/v1/runs/{id}/stages/{stageId}/sandbox` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Stage-start package, exact plan/profile, copy report, input manifest, input fingerprint, and sandbox verification.
  - **UI impact:** Implement: Stage-start review page with plan/profile/input tabs, workspace alias, risk notices, G07 controls, copy progress, and ready/blocked states.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G07 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F05-I02
  - **Suggested labels:** sprint-3, s3-f05, approval-capability, frontend, g07, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S3-F05-I04 — Verify and document Prepare a dedicated run-scoped stage sandbox and decide G07 stage start

  - **Parent feature:** S3-F05
  - **Issue type:** Testing
  - **Technical story:** Prove Prepare a dedicated run-scoped stage sandbox and decide G07 stage start through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Every major transition starts from an approved clean boundary and has its own physical workspace.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Bootstrap install, Angular update, stage validation, and copy-forward.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/stages/{stageId}/prepare; POST /api/v1/runs/{id}/approvals/G07/decisions; POST /api/v1/runs/{id}/stages/{stageId}/sandbox` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Stage-start package, exact plan/profile, copy report, input manifest, input fingerprint, and sandbox verification.` where applicable.
  - **UI impact:** Execute the feature through `Stage-start review page with plan/profile/input tabs, workspace alias, risk notices, G07 controls, copy progress, and ready/blocked states.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Stale prior-stage output, plan drift, approval before fingerprint, sandbox collision, copy interruption, active lease conflict, and source link escape.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G07 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F05-I03
  - **Suggested labels:** sprint-3, s3-f05, approval-capability, testing, g07, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---

### S3-F06 — Run the stage bootstrap clean install

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Execution capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A user can run the exact approved bootstrap install in the run-scoped stage sandbox and inspect its command, environment, lifecycle-script audit binding, logs, and result.

#### Context

The update command must start from a reproducible dependency state and cannot silently use old node_modules.

**Governing specification sections:** 23, 24, 62, 63.2

#### Scope

Approved bootstrap npm clean install in one stage, evidence, and UI.

#### Out of scope

Dependency repair, Angular update, final clean install, and generic retry of unsafe interrupted mutation.

#### Backend slice

- **Application service/components:** StagePipelineService bootstrap step, command authorization against locked StageExecutionPlan, workspace fingerprint binding, npm-ci execution, mutation-category handling, and transition/evidence completion.
- **Domain aggregate/projection:** MigrationStage, WorkflowStep bootstrap_install, CommandExecution.
- **Persistence:** Step state, command execution, stage fingerprint references, and events.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/stages/{stageId}/bootstrap-install; GET /api/v1/runs/{id}/stages/{stageId}/steps/bootstrap-install`
- **Durable event:** STAGE_BOOTSTRAP_INSTALL_STARTED/COMPLETED/FAILED plus command events.
- **Artifact Store output:** Install command/logs/result, pre/post workspace fingerprints, and package-manager debug artifacts.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Stage pipeline step card with approved command, progress/log link, result, environment blocker, retry/reconstruct guidance.
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
→ StagePipelineService bootstrap step, command authorization against locked StageExecutionPlan, workspace fingerprint binding, npm-ci execution, mutation-category handling, and transition/evidence completion.
→ Step state, command execution, stage fingerprint references, and events.
→ ArtifactService finalizes evidence: Install command/logs/result, pre/post workspace fingerprints, and package-manager debug artifacts.
→ Transition/Event service persists and emits: STAGE_BOOTSTRAP_INSTALL_STARTED/COMPLETED/FAILED plus command events.
→ SSE replay or snapshot refresh
→ Stage pipeline step card with approved command, progress/log link, result, environment blocker, retry/reconstruct guidance.
```

#### Sub-issues

- `S3-F06-I01` — Backend/application contract
- `S3-F06-I02` — Persistence, API, durable event, and artifact contract
- `S3-F06-I03` — Frontend projection and interaction
- `S3-F06-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Run the stage bootstrap clean install**, then the backend performs only the authorized service operation, persists the result, emits the documented **STAGE_BOOTSTRAP_INSTALL_STARTED/COMPLETED/FAILED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Step state, command execution, stage fingerprint references, and events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Install command/logs/result, pre/post workspace fingerprints, and package-manager debug artifacts.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Execution authority:** Given any attempt to bypass the registered command template, approved plan, exact profile, workspace alias, or `shell=false` policy, when authorization runs, then execution is rejected before process creation.

#### Manual end-to-end test scenario

**Preconditions:** S3-F05; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Stage pipeline step card with approved command, progress/log link, result, environment blocker, retry/reconstruct guidance.**.
3. Trigger the primary action for **Run the stage bootstrap clean install** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can run the exact approved bootstrap install in the run-scoped stage sandbox and inspect its command, environment, lifecycle-script audit binding, logs, and result. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Step state, command execution, stage fingerprint references, and events.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/bootstrap-install; GET /api/v1/runs/{id}/stages/{stageId}/steps/bootstrap-install` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Install command/logs/result, pre/post workspace fingerprints, and package-manager debug artifacts.

**Expected durable event:** STAGE_BOOTSTRAP_INSTALL_STARTED/COMPLETED/FAILED plus command events.

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

S3-F05

#### Risks and edge cases

- Existing node_modules not removed
- lockfile mismatch
- lifecycle script risk
- registry failure
- interrupted install
- and wrong profile.

#### Detailed sub-issues

#### S3-F06-I01 — Implement backend application contract for Run the stage bootstrap clean install

  - **Parent feature:** S3-F06
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Run the stage bootstrap clean install so the feature has one authoritative service path.
  - **Context:** The update command must start from a reproducible dependency state and cannot silently use old node_modules.
  - **Scope:** StagePipelineService bootstrap step, command authorization against locked StageExecutionPlan, workspace fingerprint binding, npm-ci execution, mutation-category handling, and transition/evidence completion.
  - **Out of scope:** Dependency repair, Angular update, final clean install, and generic retry of unsafe interrupted mutation.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/bootstrap-install; GET /api/v1/runs/{id}/stages/{stageId}/steps/bootstrap-install`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: StagePipelineService bootstrap step, command authorization against locked StageExecutionPlan, workspace fingerprint binding, npm-ci execution, mutation-category handling, and transition/evidence completion.
  - **Database impact:** Use or introduce the records summarized by: Step state, command execution, stage fingerprint references, and events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/bootstrap-install; GET /api/v1/runs/{id}/stages/{stageId}/steps/bootstrap-install
  - **Event impact:** Request durable events only through the transition/event service: STAGE_BOOTSTRAP_INSTALL_STARTED/COMPLETED/FAILED plus command events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Install command/logs/result, pre/post workspace fingerprints, and package-manager debug artifacts.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Existing node_modules not removed, lockfile mismatch, lifecycle script risk, registry failure, interrupted install, and wrong profile.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F05
  - **Suggested labels:** sprint-3, s3-f06, execution-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F06-I02 — Persist and expose evidence contracts for Run the stage bootstrap clean install

  - **Parent feature:** S3-F06
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Run the stage bootstrap clean install observable and auditable.
  - **Context:** The update command must start from a reproducible dependency state and cannot silently use old node_modules.
  - **Scope:** Persistence: Step state, command execution, stage fingerprint references, and events. API: POST /api/v1/runs/{id}/stages/{stageId}/bootstrap-install; GET /api/v1/runs/{id}/stages/{stageId}/steps/bootstrap-install. Events: STAGE_BOOTSTRAP_INSTALL_STARTED/COMPLETED/FAILED plus command events. Artifacts: Install command/logs/result, pre/post workspace fingerprints, and package-manager debug artifacts.
  - **Out of scope:** Dependency repair, Angular update, final clean install, and generic retry of unsafe interrupted mutation.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Step state, command execution, stage fingerprint references, and events.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/stages/{stageId}/bootstrap-install; GET /api/v1/runs/{id}/stages/{stageId}/steps/bootstrap-install; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: STAGE_BOOTSTRAP_INSTALL_STARTED/COMPLETED/FAILED plus command events.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Install command/logs/result, pre/post workspace fingerprints, and package-manager debug artifacts.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F06-I01
  - **Suggested labels:** sprint-3, s3-f06, execution-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F06-I03 — Build frontend experience for Run the stage bootstrap clean install

  - **Parent feature:** S3-F06
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Run the stage bootstrap clean install, using backend snapshots and durable events only.
  - **Context:** The update command must start from a reproducible dependency state and cannot silently use old node_modules.
  - **Scope:** Stage pipeline step card with approved command, progress/log link, result, environment blocker, retry/reconstruct guidance.
  - **Out of scope:** Dependency repair, Angular update, final clean install, and generic retry of unsafe interrupted mutation.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/bootstrap-install; GET /api/v1/runs/{id}/stages/{stageId}/steps/bootstrap-install` plus durable events `STAGE_BOOTSTRAP_INSTALL_STARTED/COMPLETED/FAILED plus command events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Stage pipeline step card with approved command, progress/log link, result, environment blocker, retry/reconstruct guidance.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/bootstrap-install; GET /api/v1/runs/{id}/stages/{stageId}/steps/bootstrap-install` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `STAGE_BOOTSTRAP_INSTALL_STARTED/COMPLETED/FAILED plus command events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Install command/logs/result, pre/post workspace fingerprints, and package-manager debug artifacts.
  - **UI impact:** Implement: Stage pipeline step card with approved command, progress/log link, result, environment blocker, retry/reconstruct guidance.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F06-I02
  - **Suggested labels:** sprint-3, s3-f06, execution-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S3-F06-I04 — Verify and document Run the stage bootstrap clean install

  - **Parent feature:** S3-F06
  - **Issue type:** Testing
  - **Technical story:** Prove Run the stage bootstrap clean install through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** The update command must start from a reproducible dependency state and cannot silently use old node_modules.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Dependency repair, Angular update, final clean install, and generic retry of unsafe interrupted mutation.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/stages/{stageId}/bootstrap-install; GET /api/v1/runs/{id}/stages/{stageId}/steps/bootstrap-install` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `STAGE_BOOTSTRAP_INSTALL_STARTED/COMPLETED/FAILED plus command events.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Install command/logs/result, pre/post workspace fingerprints, and package-manager debug artifacts.` where applicable.
  - **UI impact:** Execute the feature through `Stage pipeline step card with approved command, progress/log link, result, environment blocker, retry/reconstruct guidance.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Existing node_modules not removed, lockfile mismatch, lifecycle script risk, registry failure, interrupted install, and wrong profile.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F06-I03
  - **Suggested labels:** sprint-3, s3-f06, execution-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---

### S3-F07 — Execute the exact Angular update and verify the target version

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Execution capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A user can run the exact approved Angular core/CLI update for one stage and see the target exact version verified against package manifest, lockfile, dependency tree, and local CLI evidence.

#### Context

Official Angular tooling is the first migration mechanism; success requires exact target proof, not only command exit zero.

**Governing specification sections:** 4, 20-24, 51.1-51.2, 57.6

#### Scope

One approved major update, no force flags, prompt fail-closed behavior, target verification, and UI.

#### Out of scope

LLM repair, optional Angular modernization migrations, and transformation approval.

#### Backend slice

- **Application service/components:** AngularUpdateService, non-interactive exact argv resolution, prompt detector, command execution, target VersionVerificationService, multiple evidence-source comparison, and failure routing placeholder.
- **Domain aggregate/projection:** MigrationStage, WorkflowStep angular_update/target_verify, CommandExecution.
- **Persistence:** Step/command results, version verification metadata, state/events.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/stages/{stageId}/angular-update; GET /api/v1/runs/{id}/stages/{stageId}/target-version`
- **Durable event:** ANGULAR_UPDATE_STARTED/COMPLETED/FAILED, INTERACTIVE_DECISION_REQUIRED, TARGET_VERSION_VERIFIED/FAILED.
- **Artifact Store output:** Exact update command/logs, migration output, target-version report, package/lockfile/dependency evidence, and prompt evidence if interrupted.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Angular update step with exact versions/argv, live logs, migration list, prompt blocker, and target verification matrix.
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
→ AngularUpdateService, non-interactive exact argv resolution, prompt detector, command execution, target VersionVerificationService, multiple evidence-source comparison, and failure routing placeholder.
→ Step/command results, version verification metadata, state/events.
→ ArtifactService finalizes evidence: Exact update command/logs, migration output, target-version report, package/lockfile/dependency evidence, and prompt evidence if interrupted.
→ Transition/Event service persists and emits: ANGULAR_UPDATE_STARTED/COMPLETED/FAILED, INTERACTIVE_DECISION_REQUIRED, TARGET_VERSION_VERIFIED/FAILED.
→ SSE replay or snapshot refresh
→ Angular update step with exact versions/argv, live logs, migration list, prompt blocker, and target verification matrix.
```

#### Sub-issues

- `S3-F07-I01` — Backend/application contract
- `S3-F07-I02` — Persistence, API, durable event, and artifact contract
- `S3-F07-I03` — Frontend projection and interaction
- `S3-F07-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Execute the exact Angular update and verify the target version**, then the backend performs only the authorized service operation, persists the result, emits the documented **ANGULAR_UPDATE_STARTED/COMPLETED/FAILED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Step/command results, version verification metadata, state/events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Exact update command/logs, migration output, target-version report, package/lockfile/dependency evidence, and prompt evidence if interrupted.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Execution authority:** Given any attempt to bypass the registered command template, approved plan, exact profile, workspace alias, or `shell=false` policy, when authorization runs, then execution is rejected before process creation.

#### Manual end-to-end test scenario

**Preconditions:** S3-F06; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Angular update step with exact versions/argv, live logs, migration list, prompt blocker, and target verification matrix.**.
3. Trigger the primary action for **Execute the exact Angular update and verify the target version** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can run the exact approved Angular core/CLI update for one stage and see the target exact version verified against package manifest, lockfile, dependency tree, and local CLI evidence. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Step/command results, version verification metadata, state/events.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/angular-update; GET /api/v1/runs/{id}/stages/{stageId}/target-version` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Exact update command/logs, migration output, target-version report, package/lockfile/dependency evidence, and prompt evidence if interrupted.

**Expected durable event:** ANGULAR_UPDATE_STARTED/COMPLETED/FAILED, INTERACTIVE_DECISION_REQUIRED, TARGET_VERSION_VERIFIED/FAILED.

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

S3-F06

#### Risks and edge cases

- Unexpected prompt
- global CLI leakage
- target patch drift
- partial mutation
- package mismatch
- forced peer resolution
- and update exit zero with wrong installed version.

#### Detailed sub-issues

#### S3-F07-I01 — Implement backend application contract for Execute the exact Angular update and verify the target version

  - **Parent feature:** S3-F07
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Execute the exact Angular update and verify the target version so the feature has one authoritative service path.
  - **Context:** Official Angular tooling is the first migration mechanism; success requires exact target proof, not only command exit zero.
  - **Scope:** AngularUpdateService, non-interactive exact argv resolution, prompt detector, command execution, target VersionVerificationService, multiple evidence-source comparison, and failure routing placeholder.
  - **Out of scope:** LLM repair, optional Angular modernization migrations, and transformation approval.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/angular-update; GET /api/v1/runs/{id}/stages/{stageId}/target-version`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: AngularUpdateService, non-interactive exact argv resolution, prompt detector, command execution, target VersionVerificationService, multiple evidence-source comparison, and failure routing placeholder.
  - **Database impact:** Use or introduce the records summarized by: Step/command results, version verification metadata, state/events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/angular-update; GET /api/v1/runs/{id}/stages/{stageId}/target-version
  - **Event impact:** Request durable events only through the transition/event service: ANGULAR_UPDATE_STARTED/COMPLETED/FAILED, INTERACTIVE_DECISION_REQUIRED, TARGET_VERSION_VERIFIED/FAILED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Exact update command/logs, migration output, target-version report, package/lockfile/dependency evidence, and prompt evidence if interrupted.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Unexpected prompt, global CLI leakage, target patch drift, partial mutation, package mismatch, forced peer resolution, and update exit zero with wrong installed version.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F06
  - **Suggested labels:** sprint-3, s3-f07, execution-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S3-F07-I02 — Persist and expose evidence contracts for Execute the exact Angular update and verify the target version

  - **Parent feature:** S3-F07
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Execute the exact Angular update and verify the target version observable and auditable.
  - **Context:** Official Angular tooling is the first migration mechanism; success requires exact target proof, not only command exit zero.
  - **Scope:** Persistence: Step/command results, version verification metadata, state/events. API: POST /api/v1/runs/{id}/stages/{stageId}/angular-update; GET /api/v1/runs/{id}/stages/{stageId}/target-version. Events: ANGULAR_UPDATE_STARTED/COMPLETED/FAILED, INTERACTIVE_DECISION_REQUIRED, TARGET_VERSION_VERIFIED/FAILED. Artifacts: Exact update command/logs, migration output, target-version report, package/lockfile/dependency evidence, and prompt evidence if interrupted.
  - **Out of scope:** LLM repair, optional Angular modernization migrations, and transformation approval.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Step/command results, version verification metadata, state/events.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/stages/{stageId}/angular-update; GET /api/v1/runs/{id}/stages/{stageId}/target-version; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: ANGULAR_UPDATE_STARTED/COMPLETED/FAILED, INTERACTIVE_DECISION_REQUIRED, TARGET_VERSION_VERIFIED/FAILED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Exact update command/logs, migration output, target-version report, package/lockfile/dependency evidence, and prompt evidence if interrupted.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F07-I01
  - **Suggested labels:** sprint-3, s3-f07, execution-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S3-F07-I03 — Build frontend experience for Execute the exact Angular update and verify the target version

  - **Parent feature:** S3-F07
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Execute the exact Angular update and verify the target version, using backend snapshots and durable events only.
  - **Context:** Official Angular tooling is the first migration mechanism; success requires exact target proof, not only command exit zero.
  - **Scope:** Angular update step with exact versions/argv, live logs, migration list, prompt blocker, and target verification matrix.
  - **Out of scope:** LLM repair, optional Angular modernization migrations, and transformation approval.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/angular-update; GET /api/v1/runs/{id}/stages/{stageId}/target-version` plus durable events `ANGULAR_UPDATE_STARTED/COMPLETED/FAILED, INTERACTIVE_DECISION_REQUIRED, TARGET_VERSION_VERIFIED/FAILED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Angular update step with exact versions/argv, live logs, migration list, prompt blocker, and target verification matrix.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/angular-update; GET /api/v1/runs/{id}/stages/{stageId}/target-version` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `ANGULAR_UPDATE_STARTED/COMPLETED/FAILED, INTERACTIVE_DECISION_REQUIRED, TARGET_VERSION_VERIFIED/FAILED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Exact update command/logs, migration output, target-version report, package/lockfile/dependency evidence, and prompt evidence if interrupted.
  - **UI impact:** Implement: Angular update step with exact versions/argv, live logs, migration list, prompt blocker, and target verification matrix.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F07-I02
  - **Suggested labels:** sprint-3, s3-f07, execution-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F07-I04 — Verify and document Execute the exact Angular update and verify the target version

  - **Parent feature:** S3-F07
  - **Issue type:** Testing
  - **Technical story:** Prove Execute the exact Angular update and verify the target version through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Official Angular tooling is the first migration mechanism; success requires exact target proof, not only command exit zero.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** LLM repair, optional Angular modernization migrations, and transformation approval.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/stages/{stageId}/angular-update; GET /api/v1/runs/{id}/stages/{stageId}/target-version` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `ANGULAR_UPDATE_STARTED/COMPLETED/FAILED, INTERACTIVE_DECISION_REQUIRED, TARGET_VERSION_VERIFIED/FAILED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Exact update command/logs, migration output, target-version report, package/lockfile/dependency evidence, and prompt evidence if interrupted.` where applicable.
  - **UI impact:** Execute the feature through `Angular update step with exact versions/argv, live logs, migration list, prompt blocker, and target verification matrix.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Unexpected prompt, global CLI leakage, target patch drift, partial mutation, package mismatch, forced peer resolution, and update exit zero with wrong installed version.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F07-I03
  - **Suggested labels:** sprint-3, s3-f07, execution-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---

### S3-F08 — Capture transformation diffs and classify changed-file risk

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Validation capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A reviewer can inspect complete package/lockfile/source/config diffs, changed Angular migrations, content-aware risk, and forbidden-modernization findings.

#### Context

Official tooling can produce behavior-sensitive or optional changes; the transformation must be reviewable before acceptance.

**Governing specification sections:** 26-27, 56.9, 63.5-63.8

#### Scope

Complete transformation evidence and deterministic risk/forbidden-change classification.

#### Out of scope

Approving G08, editing diff, applying repair patches, and runtime parity proof.

#### Backend slice

- **Application service/components:** TransformationEvidenceService, unified diff generator, package/lockfile summaries, changed-file classifier, sensitive-symbol/path rules, forbidden-modernization scanner, and builder-decision comparison.
- **Domain aggregate/projection:** TransformationEvidence and ChangedFileRiskFinding.
- **Persistence:** Transformation summary/risk metadata and artifact references.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence`
- **Durable event:** TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED.
- **Artifact Store output:** Complete unified diff, package/lockfile diff, migration list, changed-file inventory, risk report, forbidden-change report.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Custom unified diff viewer with file tree, risk filters, package/source tabs, sensitive changes, large-diff handling, and blocked findings.
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
→ TransformationEvidenceService, unified diff generator, package/lockfile summaries, changed-file classifier, sensitive-symbol/path rules, forbidden-modernization scanner, and builder-decision comparison.
→ Transformation summary/risk metadata and artifact references.
→ ArtifactService finalizes evidence: Complete unified diff, package/lockfile diff, migration list, changed-file inventory, risk report, forbidden-change report.
→ Transition/Event service persists and emits: TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED.
→ SSE replay or snapshot refresh
→ Custom unified diff viewer with file tree, risk filters, package/source tabs, sensitive changes, large-diff handling, and blocked findings.
```

#### Sub-issues

- `S3-F08-I01` — Backend/application contract
- `S3-F08-I02` — Persistence, API, durable event, and artifact contract
- `S3-F08-I03` — Frontend projection and interaction
- `S3-F08-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Capture transformation diffs and classify changed-file risk**, then the backend performs only the authorized service operation, persists the result, emits the documented **TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Transformation summary/risk metadata and artifact references.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Complete unified diff, package/lockfile diff, migration list, changed-file inventory, risk report, forbidden-change report.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S3-F07; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Custom unified diff viewer with file tree, risk filters, package/source tabs, sensitive changes, large-diff handling, and blocked findings.**.
3. Trigger the primary action for **Capture transformation diffs and classify changed-file risk** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can inspect complete package/lockfile/source/config diffs, changed Angular migrations, content-aware risk, and forbidden-modernization findings. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Transformation summary/risk metadata and artifact references.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Complete unified diff, package/lockfile diff, migration list, changed-file inventory, risk report, forbidden-change report.

**Expected durable event:** TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED.

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

S3-F07

#### Risks and edge cases

- Huge diff
- binary files
- line-ending noise
- generated files
- misclassified auth/API changes
- hidden modernization
- and incomplete diff.

#### Detailed sub-issues

#### S3-F08-I01 — Implement backend application contract for Capture transformation diffs and classify changed-file risk

  - **Parent feature:** S3-F08
  - **Issue type:** Validation
  - **Technical story:** Implement the bounded backend/application behavior for Capture transformation diffs and classify changed-file risk so the feature has one authoritative service path.
  - **Context:** Official tooling can produce behavior-sensitive or optional changes; the transformation must be reviewable before acceptance.
  - **Scope:** TransformationEvidenceService, unified diff generator, package/lockfile summaries, changed-file classifier, sensitive-symbol/path rules, forbidden-modernization scanner, and builder-decision comparison.
  - **Out of scope:** Approving G08, editing diff, applying repair patches, and runtime parity proof.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: TransformationEvidenceService, unified diff generator, package/lockfile summaries, changed-file classifier, sensitive-symbol/path rules, forbidden-modernization scanner, and builder-decision comparison.
  - **Database impact:** Use or introduce the records summarized by: Transformation summary/risk metadata and artifact references.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence
  - **Event impact:** Request durable events only through the transition/event service: TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Complete unified diff, package/lockfile diff, migration list, changed-file inventory, risk report, forbidden-change report.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Huge diff, binary files, line-ending noise, generated files, misclassified auth/API changes, hidden modernization, and incomplete diff.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's validation behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F07
  - **Suggested labels:** sprint-3, s3-f08, validation-capability, validation, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F08-I02 — Persist and expose evidence contracts for Capture transformation diffs and classify changed-file risk

  - **Parent feature:** S3-F08
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Capture transformation diffs and classify changed-file risk observable and auditable.
  - **Context:** Official tooling can produce behavior-sensitive or optional changes; the transformation must be reviewable before acceptance.
  - **Scope:** Persistence: Transformation summary/risk metadata and artifact references. API: POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence. Events: TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED. Artifacts: Complete unified diff, package/lockfile diff, migration list, changed-file inventory, risk report, forbidden-change report.
  - **Out of scope:** Approving G08, editing diff, applying repair patches, and runtime parity proof.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Transformation summary/risk metadata and artifact references.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Complete unified diff, package/lockfile diff, migration list, changed-file inventory, risk report, forbidden-change report.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F08-I01
  - **Suggested labels:** sprint-3, s3-f08, validation-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F08-I03 — Build frontend experience for Capture transformation diffs and classify changed-file risk

  - **Parent feature:** S3-F08
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Capture transformation diffs and classify changed-file risk, using backend snapshots and durable events only.
  - **Context:** Official tooling can produce behavior-sensitive or optional changes; the transformation must be reviewable before acceptance.
  - **Scope:** Custom unified diff viewer with file tree, risk filters, package/source tabs, sensitive changes, large-diff handling, and blocked findings.
  - **Out of scope:** Approving G08, editing diff, applying repair patches, and runtime parity proof.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence` plus durable events `TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Custom unified diff viewer with file tree, risk filters, package/source tabs, sensitive changes, large-diff handling, and blocked findings.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Complete unified diff, package/lockfile diff, migration list, changed-file inventory, risk report, forbidden-change report.
  - **UI impact:** Implement: Custom unified diff viewer with file tree, risk filters, package/source tabs, sensitive changes, large-diff handling, and blocked findings.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F08-I02
  - **Suggested labels:** sprint-3, s3-f08, validation-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S3-F08-I04 — Verify and document Capture transformation diffs and classify changed-file risk

  - **Parent feature:** S3-F08
  - **Issue type:** Testing
  - **Technical story:** Prove Capture transformation diffs and classify changed-file risk through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Official tooling can produce behavior-sensitive or optional changes; the transformation must be reviewable before acceptance.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Approving G08, editing diff, applying repair patches, and runtime parity proof.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/stages/{stageId}/transformation-evidence; GET /api/v1/runs/{id}/stages/{stageId}/transformation-evidence` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Complete unified diff, package/lockfile diff, migration list, changed-file inventory, risk report, forbidden-change report.` where applicable.
  - **UI impact:** Execute the feature through `Custom unified diff viewer with file tree, risk filters, package/source tabs, sensitive changes, large-diff handling, and blocked findings.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Huge diff, binary files, line-ending noise, generated files, misclassified auth/API changes, hidden modernization, and incomplete diff.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F08-I03
  - **Suggested labels:** sprint-3, s3-f08, validation-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---

### S3-F09 — Review and decide G08 transformation acceptance

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Approval capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G08

#### User-observable outcome

A reviewer can approve, request modification, or reject the exact transformation artifact set; any workspace change makes the decision stale.

#### Context

Human review is required before the stage crosses the transformation boundary, especially for high-risk files and builder behavior.

**Governing specification sections:** 12, 27, 56.9

#### Scope

G08 binding, review UI, risk-aware decision package, and proof validation cannot cross configured gate without approval.

#### Out of scope

Changing the diff in UI, technical validation, repair, and stage completion.

#### Backend slice

- **Application service/components:** G08 EvidencePackageBuilder, artifact-set checksum, current workspace fingerprint binding, risk-dependent prerequisite checks, decision consequences, and Transition Service.
- **Domain aggregate/projection:** ApprovalGate G08 and UserDecision.
- **Persistence:** Gate version, evidence checksum, fingerprint, decisions, transition/event records.
- **State/approval rule:** G08 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `GET /api/v1/runs/{id}/approvals/G08; POST /api/v1/runs/{id}/approvals/G08/decisions`
- **Durable event:** APPROVAL_GATE_CREATED and G08 decision/stale events.
- **Artifact Store output:** G08 package referencing all transformation and risk artifacts.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Transformation review workspace combining diff viewer, risk summary, comments, decision controls, stale warning, and failure/blocked states.
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
→ G08 EvidencePackageBuilder, artifact-set checksum, current workspace fingerprint binding, risk-dependent prerequisite checks, decision consequences, and Transition Service.
→ Gate version, evidence checksum, fingerprint, decisions, transition/event records.
→ ArtifactService finalizes evidence: G08 package referencing all transformation and risk artifacts.
→ Transition/Event service persists and emits: APPROVAL_GATE_CREATED and G08 decision/stale events.
→ SSE replay or snapshot refresh
→ Transformation review workspace combining diff viewer, risk summary, comments, decision controls, stale warning, and failure/blocked states.
```

#### Sub-issues

- `S3-F09-I01` — Backend/application contract
- `S3-F09-I02` — Persistence, API, durable event, and artifact contract
- `S3-F09-I03` — Frontend projection and interaction
- `S3-F09-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Review and decide G08 transformation acceptance**, then the backend performs only the authorized service operation, persists the result, emits the documented **APPROVAL_GATE_CREATED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Gate version, evidence checksum, fingerprint, decisions, transition/event records.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **G08 package referencing all transformation and risk artifacts.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G08 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G08 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.

#### Manual end-to-end test scenario

**Preconditions:** S3-F08; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Transformation review workspace combining diff viewer, risk summary, comments, decision controls, stale warning, and failure/blocked states.**.
    3. Trigger the primary action for **Review and decide G08 transformation acceptance** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G08** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can approve, request modification, or reject the exact transformation artifact set; any workspace change makes the decision stale. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `Gate version, evidence checksum, fingerprint, decisions, transition/event records.` are retrievable through `GET /api/v1/runs/{id}/approvals/G08; POST /api/v1/runs/{id}/approvals/G08/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** G08 package referencing all transformation and risk artifacts.

    **Expected durable event:** APPROVAL_GATE_CREATED and G08 decision/stale events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G08 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

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

S3-F08

#### Risks and edge cases

- Approving stale diff
- artifact omission
- high-risk change hidden by filter
- modification request without new evidence version
- and approval converting target mismatch into pass.

#### Detailed sub-issues

#### S3-F09-I01 — Implement backend application contract for Review and decide G08 transformation acceptance

  - **Parent feature:** S3-F09
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Review and decide G08 transformation acceptance so the feature has one authoritative service path.
  - **Context:** Human review is required before the stage crosses the transformation boundary, especially for high-risk files and builder behavior.
  - **Scope:** G08 EvidencePackageBuilder, artifact-set checksum, current workspace fingerprint binding, risk-dependent prerequisite checks, decision consequences, and Transition Service.
  - **Out of scope:** Changing the diff in UI, technical validation, repair, and stage completion.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G08 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `GET /api/v1/runs/{id}/approvals/G08; POST /api/v1/runs/{id}/approvals/G08/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: G08 EvidencePackageBuilder, artifact-set checksum, current workspace fingerprint binding, risk-dependent prerequisite checks, decision consequences, and Transition Service.
  - **Database impact:** Use or introduce the records summarized by: Gate version, evidence checksum, fingerprint, decisions, transition/event records.
  - **API impact:** Define service-facing request/response models supporting: GET /api/v1/runs/{id}/approvals/G08; POST /api/v1/runs/{id}/approvals/G08/decisions
  - **Event impact:** Request durable events only through the transition/event service: APPROVAL_GATE_CREATED and G08 decision/stale events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: G08 package referencing all transformation and risk artifacts.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Approving stale diff, artifact omission, high-risk change hidden by filter, modification request without new evidence version, and approval converting target mismatch into pass.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G08 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F08
  - **Suggested labels:** sprint-3, s3-f09, approval-capability, backend, g08, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F09-I02 — Persist and expose evidence contracts for Review and decide G08 transformation acceptance

  - **Parent feature:** S3-F09
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Review and decide G08 transformation acceptance observable and auditable.
  - **Context:** Human review is required before the stage crosses the transformation boundary, especially for high-risk files and builder behavior.
  - **Scope:** Persistence: Gate version, evidence checksum, fingerprint, decisions, transition/event records. API: GET /api/v1/runs/{id}/approvals/G08; POST /api/v1/runs/{id}/approvals/G08/decisions. Events: APPROVAL_GATE_CREATED and G08 decision/stale events. Artifacts: G08 package referencing all transformation and risk artifacts.
  - **Out of scope:** Changing the diff in UI, technical validation, repair, and stage completion.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Gate version, evidence checksum, fingerprint, decisions, transition/event records.
  - **API impact:** Implement and document: GET /api/v1/runs/{id}/approvals/G08; POST /api/v1/runs/{id}/approvals/G08/decisions; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: APPROVAL_GATE_CREATED and G08 decision/stale events.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: G08 package referencing all transformation and risk artifacts.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G08 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F09-I01
  - **Suggested labels:** sprint-3, s3-f09, approval-capability, api, g08, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F09-I03 — Build frontend experience for Review and decide G08 transformation acceptance

  - **Parent feature:** S3-F09
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Review and decide G08 transformation acceptance, using backend snapshots and durable events only.
  - **Context:** Human review is required before the stage crosses the transformation boundary, especially for high-risk files and builder behavior.
  - **Scope:** Transformation review workspace combining diff viewer, risk summary, comments, decision controls, stale warning, and failure/blocked states.
  - **Out of scope:** Changing the diff in UI, technical validation, repair, and stage completion.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `GET /api/v1/runs/{id}/approvals/G08; POST /api/v1/runs/{id}/approvals/G08/decisions` plus durable events `APPROVAL_GATE_CREATED and G08 decision/stale events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Transformation review workspace combining diff viewer, risk summary, comments, decision controls, stale warning, and failure/blocked states.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `GET /api/v1/runs/{id}/approvals/G08; POST /api/v1/runs/{id}/approvals/G08/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `APPROVAL_GATE_CREATED and G08 decision/stale events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: G08 package referencing all transformation and risk artifacts.
  - **UI impact:** Implement: Transformation review workspace combining diff viewer, risk summary, comments, decision controls, stale warning, and failure/blocked states.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G08 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F09-I02
  - **Suggested labels:** sprint-3, s3-f09, approval-capability, frontend, g08, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S3-F09-I04 — Verify and document Review and decide G08 transformation acceptance

  - **Parent feature:** S3-F09
  - **Issue type:** Testing
  - **Technical story:** Prove Review and decide G08 transformation acceptance through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Human review is required before the stage crosses the transformation boundary, especially for high-risk files and builder behavior.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Changing the diff in UI, technical validation, repair, and stage completion.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `GET /api/v1/runs/{id}/approvals/G08; POST /api/v1/runs/{id}/approvals/G08/decisions` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `APPROVAL_GATE_CREATED and G08 decision/stale events.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `G08 package referencing all transformation and risk artifacts.` where applicable.
  - **UI impact:** Execute the feature through `Transformation review workspace combining diff viewer, risk summary, comments, decision controls, stale warning, and failure/blocked states.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Approving stale diff, artifact omission, high-risk change hidden by filter, modification request without new evidence version, and approval converting target mismatch into pass.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G08 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F09-I03
  - **Suggested labels:** sprint-3, s3-f09, approval-capability, testing, g08, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---

### S3-F10 — Run final clean install and deterministic static checks

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Validation capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A user can run a fresh final dependency install after G08 and inspect static TypeScript/template/import checks with precise pass, failure, not-configured, or blocked statuses.

#### Context

Transformation acceptance does not prove reproducibility or source validity; validation must begin from a clean dependency boundary.

**Governing specification sections:** 23-24, 32.1, 63.1-63.2

#### Scope

Final clean install and deterministic static checks after G08.

#### Out of scope

Builds, tests/lint, route/backend comparison, LLM repair, and G09.

#### Backend slice

- **Application service/components:** ValidationService install/static boundary, cleanup of node_modules/generated state, approved final npm-ci command, TypeScript/Angular template/import check adapters, result aggregation, and failure evidence hook.
- **Domain aggregate/projection:** WorkflowStep final_install/static_checks and ValidationRun.
- **Persistence:** Validation step results, command records, diagnostics, artifact references.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/stages/{stageId}/validation/install-static; GET /api/v1/runs/{id}/stages/{stageId}/validation/install-static`
- **Durable event:** VALIDATION_FINAL_INSTALL_* and STATIC_CHECKS_*.
- **Artifact Store output:** Final install logs/result, static diagnostic reports, exact dependency tree evidence, and validation summary fragment.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Install/static validation panel with step timeline, diagnostics grouped by file/code, logs, retry/reconstruct guidance, and honest statuses.
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
→ ValidationService install/static boundary, cleanup of node_modules/generated state, approved final npm-ci command, TypeScript/Angular template/import check adapters, result aggregation, and failure evidence hook.
→ Validation step results, command records, diagnostics, artifact references.
→ ArtifactService finalizes evidence: Final install logs/result, static diagnostic reports, exact dependency tree evidence, and validation summary fragment.
→ Transition/Event service persists and emits: VALIDATION_FINAL_INSTALL_* and STATIC_CHECKS_*.
→ SSE replay or snapshot refresh
→ Install/static validation panel with step timeline, diagnostics grouped by file/code, logs, retry/reconstruct guidance, and honest statuses.
```

#### Sub-issues

- `S3-F10-I01` — Backend/application contract
- `S3-F10-I02` — Persistence, API, durable event, and artifact contract
- `S3-F10-I03` — Frontend projection and interaction
- `S3-F10-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Run final clean install and deterministic static checks**, then the backend performs only the authorized service operation, persists the result, emits the documented **VALIDATION_FINAL_INSTALL_*** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Validation step results, command records, diagnostics, artifact references.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Final install logs/result, static diagnostic reports, exact dependency tree evidence, and validation summary fragment.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Execution authority:** Given any attempt to bypass the registered command template, approved plan, exact profile, workspace alias, or `shell=false` policy, when authorization runs, then execution is rejected before process creation.

#### Manual end-to-end test scenario

**Preconditions:** S3-F09; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Install/static validation panel with step timeline, diagnostics grouped by file/code, logs, retry/reconstruct guidance, and honest statuses.**.
3. Trigger the primary action for **Run final clean install and deterministic static checks** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can run a fresh final dependency install after G08 and inspect static TypeScript/template/import checks with precise pass, failure, not-configured, or blocked statuses. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Validation step results, command records, diagnostics, artifact references.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/validation/install-static; GET /api/v1/runs/{id}/stages/{stageId}/validation/install-static` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Final install logs/result, static diagnostic reports, exact dependency tree evidence, and validation summary fragment.

**Expected durable event:** VALIDATION_FINAL_INSTALL_* and STATIC_CHECKS_*.

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

S3-F09

#### Risks and edge cases

- Stale node_modules
- check command not representative
- phantom API false negative
- command interruption
- hidden generated state
- and wrong validation profile.

#### Detailed sub-issues

#### S3-F10-I01 — Implement backend application contract for Run final clean install and deterministic static checks

  - **Parent feature:** S3-F10
  - **Issue type:** Validation
  - **Technical story:** Implement the bounded backend/application behavior for Run final clean install and deterministic static checks so the feature has one authoritative service path.
  - **Context:** Transformation acceptance does not prove reproducibility or source validity; validation must begin from a clean dependency boundary.
  - **Scope:** ValidationService install/static boundary, cleanup of node_modules/generated state, approved final npm-ci command, TypeScript/Angular template/import check adapters, result aggregation, and failure evidence hook.
  - **Out of scope:** Builds, tests/lint, route/backend comparison, LLM repair, and G09.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/validation/install-static; GET /api/v1/runs/{id}/stages/{stageId}/validation/install-static`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: ValidationService install/static boundary, cleanup of node_modules/generated state, approved final npm-ci command, TypeScript/Angular template/import check adapters, result aggregation, and failure evidence hook.
  - **Database impact:** Use or introduce the records summarized by: Validation step results, command records, diagnostics, artifact references.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/validation/install-static; GET /api/v1/runs/{id}/stages/{stageId}/validation/install-static
  - **Event impact:** Request durable events only through the transition/event service: VALIDATION_FINAL_INSTALL_* and STATIC_CHECKS_*.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Final install logs/result, static diagnostic reports, exact dependency tree evidence, and validation summary fragment.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Stale node_modules, check command not representative, phantom API false negative, command interruption, hidden generated state, and wrong validation profile.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's validation behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F09
  - **Suggested labels:** sprint-3, s3-f10, validation-capability, validation, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F10-I02 — Persist and expose evidence contracts for Run final clean install and deterministic static checks

  - **Parent feature:** S3-F10
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Run final clean install and deterministic static checks observable and auditable.
  - **Context:** Transformation acceptance does not prove reproducibility or source validity; validation must begin from a clean dependency boundary.
  - **Scope:** Persistence: Validation step results, command records, diagnostics, artifact references. API: POST /api/v1/runs/{id}/stages/{stageId}/validation/install-static; GET /api/v1/runs/{id}/stages/{stageId}/validation/install-static. Events: VALIDATION_FINAL_INSTALL_* and STATIC_CHECKS_*. Artifacts: Final install logs/result, static diagnostic reports, exact dependency tree evidence, and validation summary fragment.
  - **Out of scope:** Builds, tests/lint, route/backend comparison, LLM repair, and G09.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Validation step results, command records, diagnostics, artifact references.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/stages/{stageId}/validation/install-static; GET /api/v1/runs/{id}/stages/{stageId}/validation/install-static; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: VALIDATION_FINAL_INSTALL_* and STATIC_CHECKS_*.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Final install logs/result, static diagnostic reports, exact dependency tree evidence, and validation summary fragment.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F10-I01
  - **Suggested labels:** sprint-3, s3-f10, validation-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F10-I03 — Build frontend experience for Run final clean install and deterministic static checks

  - **Parent feature:** S3-F10
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Run final clean install and deterministic static checks, using backend snapshots and durable events only.
  - **Context:** Transformation acceptance does not prove reproducibility or source validity; validation must begin from a clean dependency boundary.
  - **Scope:** Install/static validation panel with step timeline, diagnostics grouped by file/code, logs, retry/reconstruct guidance, and honest statuses.
  - **Out of scope:** Builds, tests/lint, route/backend comparison, LLM repair, and G09.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/validation/install-static; GET /api/v1/runs/{id}/stages/{stageId}/validation/install-static` plus durable events `VALIDATION_FINAL_INSTALL_* and STATIC_CHECKS_*.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Install/static validation panel with step timeline, diagnostics grouped by file/code, logs, retry/reconstruct guidance, and honest statuses.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/validation/install-static; GET /api/v1/runs/{id}/stages/{stageId}/validation/install-static` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `VALIDATION_FINAL_INSTALL_* and STATIC_CHECKS_*.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Final install logs/result, static diagnostic reports, exact dependency tree evidence, and validation summary fragment.
  - **UI impact:** Implement: Install/static validation panel with step timeline, diagnostics grouped by file/code, logs, retry/reconstruct guidance, and honest statuses.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F10-I02
  - **Suggested labels:** sprint-3, s3-f10, validation-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S3-F10-I04 — Verify and document Run final clean install and deterministic static checks

  - **Parent feature:** S3-F10
  - **Issue type:** Testing
  - **Technical story:** Prove Run final clean install and deterministic static checks through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Transformation acceptance does not prove reproducibility or source validity; validation must begin from a clean dependency boundary.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Builds, tests/lint, route/backend comparison, LLM repair, and G09.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/stages/{stageId}/validation/install-static; GET /api/v1/runs/{id}/stages/{stageId}/validation/install-static` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `VALIDATION_FINAL_INSTALL_* and STATIC_CHECKS_*.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Final install logs/result, static diagnostic reports, exact dependency tree evidence, and validation summary fragment.` where applicable.
  - **UI impact:** Execute the feature through `Install/static validation panel with step timeline, diagnostics grouped by file/code, logs, retry/reconstruct guidance, and honest statuses.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Stale node_modules, check command not representative, phantom API false negative, command interruption, hidden generated state, and wrong validation profile.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F10-I03
  - **Suggested labels:** sprint-3, s3-f10, validation-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---

### S3-F11 — Run and inspect the required stage build matrix

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Validation capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A reviewer can execute all approved required build targets for the stage and inspect per-target compilation evidence and failure diagnostics.

#### Context

Build is a mandatory core gate and cannot be changed to passed by human approval.

**Governing specification sections:** 24.1-24.6, 63.2-63.3

#### Scope

All approved required production build targets for supported MVP topology.

#### Out of scope

Repair, unsupported custom-builder implementation, browser runtime tests, and G09.

#### Backend slice

- **Application service/components:** ValidationService build boundary, StageExecutionPlan target resolution, per-target command execution, result aggregation, output-path evidence, and failure parser hook.
- **Domain aggregate/projection:** ValidationRun, WorkflowStep builds, CommandExecution.
- **Persistence:** Per-target statuses, command records, diagnostics, artifact references.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/stages/{stageId}/validation/builds; GET /api/v1/runs/{id}/stages/{stageId}/validation/builds`
- **Durable event:** STAGE_BUILD_STARTED/TARGET_COMPLETED/COMPLETED/FAILED.
- **Artifact Store output:** Build matrix, full logs, compiler diagnostics, output manifest/budget evidence where configured.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Build matrix with project/configuration, mandatory/conditional labels, progress, diagnostic drill-down, and immutable evidence links.
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
→ ValidationService build boundary, StageExecutionPlan target resolution, per-target command execution, result aggregation, output-path evidence, and failure parser hook.
→ Per-target statuses, command records, diagnostics, artifact references.
→ ArtifactService finalizes evidence: Build matrix, full logs, compiler diagnostics, output manifest/budget evidence where configured.
→ Transition/Event service persists and emits: STAGE_BUILD_STARTED/TARGET_COMPLETED/COMPLETED/FAILED.
→ SSE replay or snapshot refresh
→ Build matrix with project/configuration, mandatory/conditional labels, progress, diagnostic drill-down, and immutable evidence links.
```

#### Sub-issues

- `S3-F11-I01` — Backend/application contract
- `S3-F11-I02` — Persistence, API, durable event, and artifact contract
- `S3-F11-I03` — Frontend projection and interaction
- `S3-F11-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Run and inspect the required stage build matrix**, then the backend performs only the authorized service operation, persists the result, emits the documented **STAGE_BUILD_STARTED/TARGET_COMPLETED/COMPLETED/FAILED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Per-target statuses, command records, diagnostics, artifact references.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Build matrix, full logs, compiler diagnostics, output manifest/budget evidence where configured.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Execution authority:** Given any attempt to bypass the registered command template, approved plan, exact profile, workspace alias, or `shell=false` policy, when authorization runs, then execution is rejected before process creation.

#### Manual end-to-end test scenario

**Preconditions:** S3-F10; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Build matrix with project/configuration, mandatory/conditional labels, progress, diagnostic drill-down, and immutable evidence links.**.
3. Trigger the primary action for **Run and inspect the required stage build matrix** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can execute all approved required build targets for the stage and inspect per-target compilation evidence and failure diagnostics. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Per-target statuses, command records, diagnostics, artifact references.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/validation/builds; GET /api/v1/runs/{id}/stages/{stageId}/validation/builds` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Build matrix, full logs, compiler diagnostics, output manifest/budget evidence where configured.

**Expected durable event:** STAGE_BUILD_STARTED/TARGET_COMPLETED/COMPLETED/FAILED.

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

S3-F10

#### Risks and edge cases

- Missing target
- custom builder
- output path change
- memory exhaustion
- conditional target silently skipped
- and false pass from one project only.

#### Detailed sub-issues

#### S3-F11-I01 — Implement backend application contract for Run and inspect the required stage build matrix

  - **Parent feature:** S3-F11
  - **Issue type:** Validation
  - **Technical story:** Implement the bounded backend/application behavior for Run and inspect the required stage build matrix so the feature has one authoritative service path.
  - **Context:** Build is a mandatory core gate and cannot be changed to passed by human approval.
  - **Scope:** ValidationService build boundary, StageExecutionPlan target resolution, per-target command execution, result aggregation, output-path evidence, and failure parser hook.
  - **Out of scope:** Repair, unsupported custom-builder implementation, browser runtime tests, and G09.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/validation/builds; GET /api/v1/runs/{id}/stages/{stageId}/validation/builds`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: ValidationService build boundary, StageExecutionPlan target resolution, per-target command execution, result aggregation, output-path evidence, and failure parser hook.
  - **Database impact:** Use or introduce the records summarized by: Per-target statuses, command records, diagnostics, artifact references.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/validation/builds; GET /api/v1/runs/{id}/stages/{stageId}/validation/builds
  - **Event impact:** Request durable events only through the transition/event service: STAGE_BUILD_STARTED/TARGET_COMPLETED/COMPLETED/FAILED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Build matrix, full logs, compiler diagnostics, output manifest/budget evidence where configured.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Missing target, custom builder, output path change, memory exhaustion, conditional target silently skipped, and false pass from one project only.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's validation behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F10
  - **Suggested labels:** sprint-3, s3-f11, validation-capability, validation, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F11-I02 — Persist and expose evidence contracts for Run and inspect the required stage build matrix

  - **Parent feature:** S3-F11
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Run and inspect the required stage build matrix observable and auditable.
  - **Context:** Build is a mandatory core gate and cannot be changed to passed by human approval.
  - **Scope:** Persistence: Per-target statuses, command records, diagnostics, artifact references. API: POST /api/v1/runs/{id}/stages/{stageId}/validation/builds; GET /api/v1/runs/{id}/stages/{stageId}/validation/builds. Events: STAGE_BUILD_STARTED/TARGET_COMPLETED/COMPLETED/FAILED. Artifacts: Build matrix, full logs, compiler diagnostics, output manifest/budget evidence where configured.
  - **Out of scope:** Repair, unsupported custom-builder implementation, browser runtime tests, and G09.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Per-target statuses, command records, diagnostics, artifact references.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/stages/{stageId}/validation/builds; GET /api/v1/runs/{id}/stages/{stageId}/validation/builds; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: STAGE_BUILD_STARTED/TARGET_COMPLETED/COMPLETED/FAILED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Build matrix, full logs, compiler diagnostics, output manifest/budget evidence where configured.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F11-I01
  - **Suggested labels:** sprint-3, s3-f11, validation-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F11-I03 — Build frontend experience for Run and inspect the required stage build matrix

  - **Parent feature:** S3-F11
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Run and inspect the required stage build matrix, using backend snapshots and durable events only.
  - **Context:** Build is a mandatory core gate and cannot be changed to passed by human approval.
  - **Scope:** Build matrix with project/configuration, mandatory/conditional labels, progress, diagnostic drill-down, and immutable evidence links.
  - **Out of scope:** Repair, unsupported custom-builder implementation, browser runtime tests, and G09.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/validation/builds; GET /api/v1/runs/{id}/stages/{stageId}/validation/builds` plus durable events `STAGE_BUILD_STARTED/TARGET_COMPLETED/COMPLETED/FAILED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Build matrix with project/configuration, mandatory/conditional labels, progress, diagnostic drill-down, and immutable evidence links.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/validation/builds; GET /api/v1/runs/{id}/stages/{stageId}/validation/builds` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `STAGE_BUILD_STARTED/TARGET_COMPLETED/COMPLETED/FAILED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Build matrix, full logs, compiler diagnostics, output manifest/budget evidence where configured.
  - **UI impact:** Implement: Build matrix with project/configuration, mandatory/conditional labels, progress, diagnostic drill-down, and immutable evidence links.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F11-I02
  - **Suggested labels:** sprint-3, s3-f11, validation-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S3-F11-I04 — Verify and document Run and inspect the required stage build matrix

  - **Parent feature:** S3-F11
  - **Issue type:** Testing
  - **Technical story:** Prove Run and inspect the required stage build matrix through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Build is a mandatory core gate and cannot be changed to passed by human approval.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Repair, unsupported custom-builder implementation, browser runtime tests, and G09.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/stages/{stageId}/validation/builds; GET /api/v1/runs/{id}/stages/{stageId}/validation/builds` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `STAGE_BUILD_STARTED/TARGET_COMPLETED/COMPLETED/FAILED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Build matrix, full logs, compiler diagnostics, output manifest/budget evidence where configured.` where applicable.
  - **UI impact:** Execute the feature through `Build matrix with project/configuration, mandatory/conditional labels, progress, diagnostic drill-down, and immutable evidence links.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Missing target, custom builder, output path change, memory exhaustion, conditional target silently skipped, and false pass from one project only.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F11-I03
  - **Suggested labels:** sprint-3, s3-f11, validation-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---

### S3-F12 — Run complete stage tests and conditional lint

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Validation capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A reviewer can run the complete configured required test suite and lint, compare failures to baseline fingerprints, and see qualified or failed outcomes without weakening tests.

#### Context

Full tests are required after each stage; lint is conditional but must be represented honestly.

**Governing specification sections:** 24, 31-32, 63.4-63.5

#### Scope

Complete configured tests, conditional lint, baseline comparison, and test-safety evidence.

#### Out of scope

Disabling tests, assertion weakening, test-framework replacement, browser E2E, and repair.

#### Backend slice

- **Application service/components:** ValidationService test/lint boundary, complete-suite command enforcement, baseline failure comparator, known-failure policy, test-change governance checks, and diagnostic normalization.
- **Domain aggregate/projection:** ValidationRun, WorkflowStep tests/lint, FailureComparison.
- **Persistence:** Command results, comparison results, step statuses, diagnostics and artifacts.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality`
- **Durable event:** STAGE_TESTS_* and STAGE_LINT_* events.
- **Artifact Store output:** Full test/lint logs, structured results, baseline comparison, test-file change report, and known-failure delta.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Tests/lint panel with full-suite proof, baseline/new/resolved grouping, not-configured state, test-change warnings, and logs.
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
→ ValidationService test/lint boundary, complete-suite command enforcement, baseline failure comparator, known-failure policy, test-change governance checks, and diagnostic normalization.
→ Command results, comparison results, step statuses, diagnostics and artifacts.
→ ArtifactService finalizes evidence: Full test/lint logs, structured results, baseline comparison, test-file change report, and known-failure delta.
→ Transition/Event service persists and emits: STAGE_TESTS_* and STAGE_LINT_* events.
→ SSE replay or snapshot refresh
→ Tests/lint panel with full-suite proof, baseline/new/resolved grouping, not-configured state, test-change warnings, and logs.
```

#### Sub-issues

- `S3-F12-I01` — Backend/application contract
- `S3-F12-I02` — Persistence, API, durable event, and artifact contract
- `S3-F12-I03` — Frontend projection and interaction
- `S3-F12-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Run complete stage tests and conditional lint**, then the backend performs only the authorized service operation, persists the result, emits the documented **STAGE_TESTS_*** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Command results, comparison results, step statuses, diagnostics and artifacts.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Full test/lint logs, structured results, baseline comparison, test-file change report, and known-failure delta.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S3-F11; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Tests/lint panel with full-suite proof, baseline/new/resolved grouping, not-configured state, test-change warnings, and logs.**.
3. Trigger the primary action for **Run complete stage tests and conditional lint** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can run the complete configured required test suite and lint, compare failures to baseline fingerprints, and see qualified or failed outcomes without weakening tests. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Command results, comparison results, step statuses, diagnostics and artifacts.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Full test/lint logs, structured results, baseline comparison, test-file change report, and known-failure delta.

**Expected durable event:** STAGE_TESTS_* and STAGE_LINT_* events.

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

S3-F11

#### Risks and edge cases

- Watch mode
- flaky test
- partial suite
- changed expected values
- hidden skipped tests
- baseline fingerprint drift
- and accepted risk misuse.

#### Detailed sub-issues

#### S3-F12-I01 — Implement backend application contract for Run complete stage tests and conditional lint

  - **Parent feature:** S3-F12
  - **Issue type:** Validation
  - **Technical story:** Implement the bounded backend/application behavior for Run complete stage tests and conditional lint so the feature has one authoritative service path.
  - **Context:** Full tests are required after each stage; lint is conditional but must be represented honestly.
  - **Scope:** ValidationService test/lint boundary, complete-suite command enforcement, baseline failure comparator, known-failure policy, test-change governance checks, and diagnostic normalization.
  - **Out of scope:** Disabling tests, assertion weakening, test-framework replacement, browser E2E, and repair.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: ValidationService test/lint boundary, complete-suite command enforcement, baseline failure comparator, known-failure policy, test-change governance checks, and diagnostic normalization.
  - **Database impact:** Use or introduce the records summarized by: Command results, comparison results, step statuses, diagnostics and artifacts.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality
  - **Event impact:** Request durable events only through the transition/event service: STAGE_TESTS_* and STAGE_LINT_* events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Full test/lint logs, structured results, baseline comparison, test-file change report, and known-failure delta.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Watch mode, flaky test, partial suite, changed expected values, hidden skipped tests, baseline fingerprint drift, and accepted risk misuse.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's validation behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F11
  - **Suggested labels:** sprint-3, s3-f12, validation-capability, validation, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

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

#### S3-F12-I03 — Build frontend experience for Run complete stage tests and conditional lint

  - **Parent feature:** S3-F12
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Run complete stage tests and conditional lint, using backend snapshots and durable events only.
  - **Context:** Full tests are required after each stage; lint is conditional but must be represented honestly.
  - **Scope:** Tests/lint panel with full-suite proof, baseline/new/resolved grouping, not-configured state, test-change warnings, and logs.
  - **Out of scope:** Disabling tests, assertion weakening, test-framework replacement, browser E2E, and repair.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality` plus durable events `STAGE_TESTS_* and STAGE_LINT_* events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Tests/lint panel with full-suite proof, baseline/new/resolved grouping, not-configured state, test-change warnings, and logs.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `STAGE_TESTS_* and STAGE_LINT_* events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Full test/lint logs, structured results, baseline comparison, test-file change report, and known-failure delta.
  - **UI impact:** Implement: Tests/lint panel with full-suite proof, baseline/new/resolved grouping, not-configured state, test-change warnings, and logs.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F12-I02
  - **Suggested labels:** sprint-3, s3-f12, validation-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S3-F12-I04 — Verify and document Run complete stage tests and conditional lint

  - **Parent feature:** S3-F12
  - **Issue type:** Testing
  - **Technical story:** Prove Run complete stage tests and conditional lint through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Full tests are required after each stage; lint is conditional but must be represented honestly.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Disabling tests, assertion weakening, test-framework replacement, browser E2E, and repair.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/stages/{stageId}/validation/quality; GET /api/v1/runs/{id}/stages/{stageId}/validation/quality` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `STAGE_TESTS_* and STAGE_LINT_* events.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Full test/lint logs, structured results, baseline comparison, test-file change report, and known-failure delta.` where applicable.
  - **UI impact:** Execute the feature through `Tests/lint panel with full-suite proof, baseline/new/resolved grouping, not-configured state, test-change warnings, and logs.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Watch mode, flaky test, partial suite, changed expected values, hidden skipped tests, baseline fingerprint drift, and accepted risk misuse.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F12-I03
  - **Suggested labels:** sprint-3, s3-f12, validation-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---

### S3-F13 — Compare parity evidence, display assurance, and decide G09 validation acceptance

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Approval capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G09

#### User-observable outcome

A reviewer can inspect route/backend integration deltas, changed-file risk, technical/manual/deferred assurance dimensions, and decide G09 without converting failed core gates to pass.

#### Context

Stage validation combines machine gates and honest parity evidence; technical success remains separate from functional, security, and quality assurance.

**Governing specification sections:** 24-25, 56.10, 63.6-63.10

#### Scope

Structural parity comparison, assurance model, complete validation package, and G09.

#### Out of scope

Automated browser/visual proof, repair flow, stage sealing, and external security/quality scans.

#### Backend slice

- **Application service/components:** RouteComparisonService, BackendIntegrationComparisonService, AssuranceAggregator, validation summary, core-gate prerequisite policy, G09 package, and Transition Service.
- **Domain aggregate/projection:** ValidationRun, AssuranceStatus, ApprovalGate G09.
- **Persistence:** Assurance dimension records, comparison summaries, gate/decisions, events.
- **State/approval rule:** G09 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions`
- **Durable event:** PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events.
- **Artifact Store output:** Route comparison, backend-integration comparison, changed-risk rollup, parity checklist, assurance summary, and G09 package.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Validation review page with gate matrix, route/API deltas, independent assurance cards, proof labels, manual/deferred items, and G09 controls.
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
→ RouteComparisonService, BackendIntegrationComparisonService, AssuranceAggregator, validation summary, core-gate prerequisite policy, G09 package, and Transition Service.
→ Assurance dimension records, comparison summaries, gate/decisions, events.
→ ArtifactService finalizes evidence: Route comparison, backend-integration comparison, changed-risk rollup, parity checklist, assurance summary, and G09 package.
→ Transition/Event service persists and emits: PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events.
→ SSE replay or snapshot refresh
→ Validation review page with gate matrix, route/API deltas, independent assurance cards, proof labels, manual/deferred items, and G09 controls.
```

#### Sub-issues

- `S3-F13-I01` — Backend/application contract
- `S3-F13-I02` — Persistence, API, durable event, and artifact contract
- `S3-F13-I03` — Frontend projection and interaction
- `S3-F13-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Compare parity evidence, display assurance, and decide G09 validation acceptance**, then the backend performs only the authorized service operation, persists the result, emits the documented **PARITY_COMPARISON_COMPLETED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Assurance dimension records, comparison summaries, gate/decisions, events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Route comparison, backend-integration comparison, changed-risk rollup, parity checklist, assurance summary, and G09 package.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G09 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G09 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.

#### Manual end-to-end test scenario

**Preconditions:** S3-F10, S3-F11, S3-F12; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Validation review page with gate matrix, route/API deltas, independent assurance cards, proof labels, manual/deferred items, and G09 controls.**.
    3. Trigger the primary action for **Compare parity evidence, display assurance, and decide G09 validation acceptance** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G09** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can inspect route/backend integration deltas, changed-file risk, technical/manual/deferred assurance dimensions, and decide G09 without converting failed core gates to pass. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `Assurance dimension records, comparison summaries, gate/decisions, events.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Route comparison, backend-integration comparison, changed-risk rollup, parity checklist, assurance summary, and G09 package.

    **Expected durable event:** PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G09 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

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

S3-F10, S3-F11, S3-F12

#### Risks and edge cases

- Dynamic behavior not proven
- manual item shown as pass
- core failure bypass
- stale comparison
- accepted difference without evidence
- and route parser mismatch.

#### Detailed sub-issues

#### S3-F13-I01 — Implement backend application contract for Compare parity evidence, display assurance, and decide G09 validation acceptance

  - **Parent feature:** S3-F13
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Compare parity evidence, display assurance, and decide G09 validation acceptance so the feature has one authoritative service path.
  - **Context:** Stage validation combines machine gates and honest parity evidence; technical success remains separate from functional, security, and quality assurance.
  - **Scope:** RouteComparisonService, BackendIntegrationComparisonService, AssuranceAggregator, validation summary, core-gate prerequisite policy, G09 package, and Transition Service.
  - **Out of scope:** Automated browser/visual proof, repair flow, stage sealing, and external security/quality scans.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G09 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: RouteComparisonService, BackendIntegrationComparisonService, AssuranceAggregator, validation summary, core-gate prerequisite policy, G09 package, and Transition Service.
  - **Database impact:** Use or introduce the records summarized by: Assurance dimension records, comparison summaries, gate/decisions, events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions
  - **Event impact:** Request durable events only through the transition/event service: PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Route comparison, backend-integration comparison, changed-risk rollup, parity checklist, assurance summary, and G09 package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Dynamic behavior not proven, manual item shown as pass, core failure bypass, stale comparison, accepted difference without evidence, and route parser mismatch.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G09 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F10, S3-F11, S3-F12
  - **Suggested labels:** sprint-3, s3-f13, approval-capability, backend, g09, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F13-I02 — Persist and expose evidence contracts for Compare parity evidence, display assurance, and decide G09 validation acceptance

  - **Parent feature:** S3-F13
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Compare parity evidence, display assurance, and decide G09 validation acceptance observable and auditable.
  - **Context:** Stage validation combines machine gates and honest parity evidence; technical success remains separate from functional, security, and quality assurance.
  - **Scope:** Persistence: Assurance dimension records, comparison summaries, gate/decisions, events. API: POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions. Events: PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events. Artifacts: Route comparison, backend-integration comparison, changed-risk rollup, parity checklist, assurance summary, and G09 package.
  - **Out of scope:** Automated browser/visual proof, repair flow, stage sealing, and external security/quality scans.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Assurance dimension records, comparison summaries, gate/decisions, events.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Route comparison, backend-integration comparison, changed-risk rollup, parity checklist, assurance summary, and G09 package.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G09 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F13-I01
  - **Suggested labels:** sprint-3, s3-f13, approval-capability, api, g09, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F13-I03 — Build frontend experience for Compare parity evidence, display assurance, and decide G09 validation acceptance

  - **Parent feature:** S3-F13
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Compare parity evidence, display assurance, and decide G09 validation acceptance, using backend snapshots and durable events only.
  - **Context:** Stage validation combines machine gates and honest parity evidence; technical success remains separate from functional, security, and quality assurance.
  - **Scope:** Validation review page with gate matrix, route/API deltas, independent assurance cards, proof labels, manual/deferred items, and G09 controls.
  - **Out of scope:** Automated browser/visual proof, repair flow, stage sealing, and external security/quality scans.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions` plus durable events `PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Validation review page with gate matrix, route/API deltas, independent assurance cards, proof labels, manual/deferred items, and G09 controls.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Route comparison, backend-integration comparison, changed-risk rollup, parity checklist, assurance summary, and G09 package.
  - **UI impact:** Implement: Validation review page with gate matrix, route/API deltas, independent assurance cards, proof labels, manual/deferred items, and G09 controls.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G09 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F13-I02
  - **Suggested labels:** sprint-3, s3-f13, approval-capability, frontend, g09, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S3-F13-I04 — Verify and document Compare parity evidence, display assurance, and decide G09 validation acceptance

  - **Parent feature:** S3-F13
  - **Issue type:** Testing
  - **Technical story:** Prove Compare parity evidence, display assurance, and decide G09 validation acceptance through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Stage validation combines machine gates and honest parity evidence; technical success remains separate from functional, security, and quality assurance.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Automated browser/visual proof, repair flow, stage sealing, and external security/quality scans.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/stages/{stageId}/validation/parity; GET /api/v1/runs/{id}/stages/{stageId}/validation/summary; POST /api/v1/runs/{id}/approvals/G09/decisions` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `PARITY_COMPARISON_COMPLETED, STAGE_VALIDATION_COMPLETED, G09 events.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Route comparison, backend-integration comparison, changed-risk rollup, parity checklist, assurance summary, and G09 package.` where applicable.
  - **UI impact:** Execute the feature through `Validation review page with gate matrix, route/API deltas, independent assurance cards, proof labels, manual/deferred items, and G09 controls.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Dynamic behavior not proven, manual item shown as pass, core failure bypass, stale comparison, accepted difference without evidence, and route parser mismatch.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G09 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F13-I03
  - **Suggested labels:** sprint-3, s3-f13, approval-capability, testing, g09, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---

### S3-F14 — Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21

#### Feature identity

- **Sprint:** Sprint 3
- **Feature type:** Approval capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G12

#### User-observable outcome

A reviewer can clean and fingerprint an approved stage, decide G12, copy only its clean output into the next dedicated sandbox, and observe the same engine execute 18→19, 19→20, and 20→21 on a passing fixture.

#### Context

Stage completion and copy-forward are separate trusted boundaries. The engine must use actual prior-stage output and finalize exact versions before each new stage.

**Governing specification sections:** 14, 22-23, 33, 56.13, 61.4-61.7, 72.1

#### Scope

G12, clean sealing, physical copy-forward, parameterized LangGraph stage loop, and passing-fixture proof for all three transitions.

#### Out of scope

LLM repair, final clean assurance, delivery, and startup crash recovery.

#### Backend slice

- **Application service/components:** StageCompletionService, cleanup/cleanliness verification, stable output fingerprint, G12 package, copy-forward, next-stage exact re-resolution/plan revision hook, LangGraph stage loop, and stage status aggregation.
- **Domain aggregate/projection:** MigrationStage, WorkspaceFingerprint, ApprovalGate G12, MigrationRun active-stage pointer.
- **Persistence:** Stage output records, fingerprints, gate decisions, next-stage sandbox records, transitions/events.
- **State/approval rule:** G12 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward`
- **Durable event:** STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.
- **Artifact Store output:** Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Stage completion review, cleanliness/fingerprint cards, G12 controls, copy-forward progress, three-stage timeline, and stage-specific state/log/artifact navigation.
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
→ StageCompletionService, cleanup/cleanliness verification, stable output fingerprint, G12 package, copy-forward, next-stage exact re-resolution/plan revision hook, LangGraph stage loop, and stage status aggregation.
→ Stage output records, fingerprints, gate decisions, next-stage sandbox records, transitions/events.
→ ArtifactService finalizes evidence: Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.
→ Transition/Event service persists and emits: STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.
→ SSE replay or snapshot refresh
→ Stage completion review, cleanliness/fingerprint cards, G12 controls, copy-forward progress, three-stage timeline, and stage-specific state/log/artifact navigation.
```

#### Sub-issues

- `S3-F14-I01` — Backend/application contract
- `S3-F14-I02` — Persistence, API, durable event, and artifact contract
- `S3-F14-I03` — Frontend projection and interaction
- `S3-F14-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21**, then the backend performs only the authorized service operation, persists the result, emits the documented **STAGE_CLEANUP_COMPLETED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Stage output records, fingerprints, gate decisions, next-stage sandbox records, transitions/events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G12 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G12 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.

#### Manual end-to-end test scenario

**Preconditions:** S3-F13; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Stage completion review, cleanliness/fingerprint cards, G12 controls, copy-forward progress, three-stage timeline, and stage-specific state/log/artifact navigation.**.
    3. Trigger the primary action for **Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G12** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can clean and fingerprint an approved stage, decide G12, copy only its clean output into the next dedicated sandbox, and observe the same engine execute 18→19, 19→20, and 20→21 on a passing fixture. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `Stage output records, fingerprints, gate decisions, next-stage sandbox records, transitions/events.` are retrievable through `POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.

    **Expected durable event:** STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G12 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

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

S3-F13

#### Risks and edge cases

- node_modules copied forward
- unstable fingerprint
- stage index mismatch
- wrong sandbox path
- next exact profile not revalidated
- artifact cross-stage overwrite
- and UI showing wrong active stage.

#### Detailed sub-issues

#### S3-F14-I01 — Implement backend application contract for Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21

  - **Parent feature:** S3-F14
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21 so the feature has one authoritative service path.
  - **Context:** Stage completion and copy-forward are separate trusted boundaries. The engine must use actual prior-stage output and finalize exact versions before each new stage.
  - **Scope:** StageCompletionService, cleanup/cleanliness verification, stable output fingerprint, G12 package, copy-forward, next-stage exact re-resolution/plan revision hook, LangGraph stage loop, and stage status aggregation.
  - **Out of scope:** LLM repair, final clean assurance, delivery, and startup crash recovery.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G12 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: StageCompletionService, cleanup/cleanliness verification, stable output fingerprint, G12 package, copy-forward, next-stage exact re-resolution/plan revision hook, LangGraph stage loop, and stage status aggregation.
  - **Database impact:** Use or introduce the records summarized by: Stage output records, fingerprints, gate decisions, next-stage sandbox records, transitions/events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward
  - **Event impact:** Request durable events only through the transition/event service: STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: node_modules copied forward, unstable fingerprint, stage index mismatch, wrong sandbox path, next exact profile not revalidated, artifact cross-stage overwrite, and UI showing wrong active stage.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G12 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F13
  - **Suggested labels:** sprint-3, s3-f14, approval-capability, backend, g12, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F14-I02 — Persist and expose evidence contracts for Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21

  - **Parent feature:** S3-F14
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21 observable and auditable.
  - **Context:** Stage completion and copy-forward are separate trusted boundaries. The engine must use actual prior-stage output and finalize exact versions before each new stage.
  - **Scope:** Persistence: Stage output records, fingerprints, gate decisions, next-stage sandbox records, transitions/events. API: POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward. Events: STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY. Artifacts: Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.
  - **Out of scope:** LLM repair, final clean assurance, delivery, and startup crash recovery.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Stage output records, fingerprints, gate decisions, next-stage sandbox records, transitions/events.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G12 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S3-F14-I01
  - **Suggested labels:** sprint-3, s3-f14, approval-capability, api, g12, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S3-F14-I03 — Build frontend experience for Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21

  - **Parent feature:** S3-F14
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21, using backend snapshots and durable events only.
  - **Context:** Stage completion and copy-forward are separate trusted boundaries. The engine must use actual prior-stage output and finalize exact versions before each new stage.
  - **Scope:** Stage completion review, cleanliness/fingerprint cards, G12 controls, copy-forward progress, three-stage timeline, and stage-specific state/log/artifact navigation.
  - **Out of scope:** LLM repair, final clean assurance, delivery, and startup crash recovery.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward` plus durable events `STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Stage completion review, cleanliness/fingerprint cards, G12 controls, copy-forward progress, three-stage timeline, and stage-specific state/log/artifact navigation.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.
  - **UI impact:** Implement: Stage completion review, cleanliness/fingerprint cards, G12 controls, copy-forward progress, three-stage timeline, and stage-specific state/log/artifact navigation.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G12 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S3-F14-I02
  - **Suggested labels:** sprint-3, s3-f14, approval-capability, frontend, g12, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S3-F14-I04 — Verify and document Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21

  - **Parent feature:** S3-F14
  - **Issue type:** Testing
  - **Technical story:** Prove Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21 through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Stage completion and copy-forward are separate trusted boundaries. The engine must use actual prior-stage output and finalize exact versions before each new stage.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** LLM repair, final clean assurance, delivery, and startup crash recovery.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/stages/{stageId}/complete-package; POST /api/v1/runs/{id}/approvals/G12/decisions; POST /api/v1/runs/{id}/stages/{stageId}/copy-forward` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, NEXT_STAGE_CREATED/SANDBOX_READY.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Cleanup report, cleanliness report, output manifest/fingerprint, stage evidence index, G12 package, and copy-forward report.` where applicable.
  - **UI impact:** Execute the feature through `Stage completion review, cleanliness/fingerprint cards, G12 controls, copy-forward progress, three-stage timeline, and stage-specific state/log/artifact navigation.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: node_modules copied forward, unstable fingerprint, stage index mismatch, wrong sandbox path, next exact profile not revalidated, artifact cross-stage overwrite, and UI showing wrong active stage.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G12 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S3-F14-I03
  - **Suggested labels:** sprint-3, s3-f14, approval-capability, testing, g12, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### D.3.5 Sprint integration tests

- Command policy negative tests for shell strings, forbidden flags, cwd escape, environment smuggling, and stale plan.

- Real harmless subprocess, timeout, live log, process-tree cancellation, and partial-evidence tests.

- Run-scoped stage sandbox isolation and no-node_modules copy-forward tests.

- Complete stage validation matrix and core-gate non-bypass tests.

- LangGraph parameterized stage-loop tests using actual prior-stage output and exact re-resolution.


### D.3.6 Sprint manual demonstration

Approve G07; create Stage 18→19 sandbox; run exact update; watch/reconnect logs; inspect diff and approve G08; run install/static/build/tests/lint/parity; approve G09; clean/fingerprint and approve G12; copy forward; cancel a controlled command; prove source unchanged; run all three stages on a passing fixture.


#### Demonstration checklist

1. Approve G07.

2. Create Stage 18→19 sandbox.

3. Run exact update.

4. Watch/reconnect logs.

5. Inspect diff and approve G08.

6. Run install/static/build/tests/lint/parity.

7. Approve G09.

8. Clean/fingerprint and approve G12.

9. Copy forward.

10. Cancel a controlled command.

11. Prove source unchanged.

12. Run all three stages on a passing fixture..


### D.3.7 Sprint exit criteria

- The CommandExecutor is the sole process path.

- G07, G08, G09, and G12 block and bind correctly.

- All three MVP transitions pass on a representative passing fixture.

- Browser refresh does not cancel execution.

- Explicit cancellation terminates the controlled process tree and preserves evidence.

- Every stage has a distinct clean sandbox and fingerprint.


### D.3.8 Risks carried into the next sprint

Repair governance, crash recovery, final assurance, atomic delivery, reporting, and runtime acceptance are completed in Sprint 4.