

## Sprint 2 — Deterministic Discovery, Governed Azure AI Analysis, Feasibility, Compatibility Resolution, and Planning

**Dependency:** Sprint 1 G03-approved baseline  
**Migration boundary:** No Angular source transformation or `ng update`  
**Human gates:** G04, G05, G06  
**Feature count:** 7 vertical features / 28 bounded issues

### Sprint goal

Expand the G03-approved baseline into complete deterministic discovery, prove the production Azure OpenAI boundary before any real AI phase work, generate checksum-bound Analysis and Planning Proposer/Reviewer chains, resolve the one-major-at-a-time migration route and exact Stage 1 execution profile, and obtain an immutable executable plan through G04–G06.

### Sprint boundaries

**In scope:** deterministic discovery, behavior-sensitive parity findings, governed Azure OpenAI gateway, role routing, append-only LLM invocation ledger, smoke/capability diagnostics, Analysis phase review chain, compatibility catalogue and feasibility, MigrationPlan and StageExecutionPlan, Planning phase review chain, plan revision, and G04–G06.

**Out of scope:** real `ng update`, run-scoped stage sandbox mutation, repair patching, final assurance, and publication.

### Features in implementation order

1. **S2-F01 — Display deterministic workspace, dependency, builder, and test discovery findings**
2. **S2-F02 — Inspect routes, backend integration, and behavior-sensitive hotspots**
3. **S2-F03 — Invoke Azure OpenAI through a governed role-routed gateway**
4. **S2-F04 — Generate a checksum-bound Analysis phase review chain and decide G04**
5. **S2-F05 — Resolve the family route, support level, and exact Stage 1 profile with G05**
6. **S2-F06 — Generate and inspect the MigrationPlan and first StageExecutionPlan**
7. **S2-F07 — Review the deterministic plan through a checksum-bound Planning chain and decide G06**

### S2-F01 — Display deterministic workspace, dependency, builder, and test discovery findings

#### Feature identity

- **Sprint:** Sprint 2
- **Feature type:** Product capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A reviewer can browse deterministic discovery facts for projects, dependencies, private packages, builders, scripts, tests, lint, SSR/PWA/i18n, and state-management indicators.

#### Context

Feasibility and AI analysis must consume machine facts rather than allowing an LLM to invent project truth.

**Governing specification sections:** 16.1-16.2, 52.3, 59.7, 59.9

#### Scope

Independent deterministic scanners, parallel coordination, immutable findings, and UI.

#### Out of scope

Route/backend contract deep comparison, AI interpretation, compatibility support level, and mutation.

#### Backend slice

- **Application service/components:** Parallel read-only discovery coordinator with isolated scanners, result aggregation, confidence/unknown markers, and immutable artifact registration.
- **Domain aggregate/projection:** DiscoveryRun and WorkflowStep discovery.
- **Persistence:** Discovery summary, scanner statuses, artifact references, and transition records.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/discovery; GET /api/v1/runs/{id}/discovery`
- **Durable event:** DISCOVERY_STARTED/SCANNER_COMPLETED/COMPLETED/BLOCKED.
- **Artifact Store output:** Workspace/project, dependency, builder, test/lint, SSR/PWA/i18n, UI library/theme, and state-management inventories.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Deterministic findings explorer with scanner status, filters, fact/unknown labels, source references, and artifact drill-down.
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
→ Parallel read-only discovery coordinator with isolated scanners, result aggregation, confidence/unknown markers, and immutable artifact registration.
→ Discovery summary, scanner statuses, artifact references, and transition records.
→ ArtifactService finalizes evidence: Workspace/project, dependency, builder, test/lint, SSR/PWA/i18n, UI library/theme, and state-management inventories.
→ Transition/Event service persists and emits: DISCOVERY_STARTED/SCANNER_COMPLETED/COMPLETED/BLOCKED.
→ SSE replay or snapshot refresh
→ Deterministic findings explorer with scanner status, filters, fact/unknown labels, source references, and artifact drill-down.
```

#### Sub-issues

- `S2-F01-I01` — Backend/application contract
- `S2-F01-I02` — Persistence, API, durable event, and artifact contract
- `S2-F01-I03` — Frontend projection and interaction
- `S2-F01-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Display deterministic workspace, dependency, builder, and test discovery findings**, then the backend performs only the authorized service operation, persists the result, emits the documented **DISCOVERY_STARTED/SCANNER_COMPLETED/COMPLETED/BLOCKED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Discovery summary, scanner statuses, artifact references, and transition records.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Workspace/project, dependency, builder, test/lint, SSR/PWA/i18n, UI library/theme, and state-management inventories.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Execution authority:** Given any attempt to bypass the registered command template, approved plan, exact profile, workspace alias, or `shell=false` policy, when authorization runs, then execution is rejected before process creation.

#### Manual end-to-end test scenario

**Preconditions:** S1-F14; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Deterministic findings explorer with scanner status, filters, fact/unknown labels, source references, and artifact drill-down.**.
3. Trigger the primary action for **Display deterministic workspace, dependency, builder, and test discovery findings** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can browse deterministic discovery facts for projects, dependencies, private packages, builders, scripts, tests, lint, SSR/PWA/i18n, and state-management indicators. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Discovery summary, scanner statuses, artifact references, and transition records.` are retrievable through `POST /api/v1/runs/{id}/discovery; GET /api/v1/runs/{id}/discovery` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Workspace/project, dependency, builder, test/lint, SSR/PWA/i18n, UI library/theme, and state-management inventories.

**Expected durable event:** DISCOVERY_STARTED/SCANNER_COMPLETED/COMPLETED/BLOCKED.

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

S1-F14

#### Risks and edge cases

- Scanner overlap
- nondeterministic results
- large workspace
- unsupported topology
- malicious file content
- and partial scanner failure.

#### Detailed sub-issues

#### S2-F01-I01 — Implement backend application contract for Display deterministic workspace, dependency, builder, and test discovery findings

  - **Parent feature:** S2-F01
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Display deterministic workspace, dependency, builder, and test discovery findings so the feature has one authoritative service path.
  - **Context:** Feasibility and AI analysis must consume machine facts rather than allowing an LLM to invent project truth.
  - **Scope:** Parallel read-only discovery coordinator with isolated scanners, result aggregation, confidence/unknown markers, and immutable artifact registration.
  - **Out of scope:** Route/backend contract deep comparison, AI interpretation, compatibility support level, and mutation.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/discovery; GET /api/v1/runs/{id}/discovery`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: Parallel read-only discovery coordinator with isolated scanners, result aggregation, confidence/unknown markers, and immutable artifact registration.
  - **Database impact:** Use or introduce the records summarized by: Discovery summary, scanner statuses, artifact references, and transition records.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/discovery; GET /api/v1/runs/{id}/discovery
  - **Event impact:** Request durable events only through the transition/event service: DISCOVERY_STARTED/SCANNER_COMPLETED/COMPLETED/BLOCKED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Workspace/project, dependency, builder, test/lint, SSR/PWA/i18n, UI library/theme, and state-management inventories.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Scanner overlap, nondeterministic results, large workspace, unsupported topology, malicious file content, and partial scanner failure.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S1-F14
  - **Suggested labels:** sprint-2, s2-f01, product-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F01-I02 — Persist and expose evidence contracts for Display deterministic workspace, dependency, builder, and test discovery findings

  - **Parent feature:** S2-F01
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Display deterministic workspace, dependency, builder, and test discovery findings observable and auditable.
  - **Context:** Feasibility and AI analysis must consume machine facts rather than allowing an LLM to invent project truth.
  - **Scope:** Persistence: Discovery summary, scanner statuses, artifact references, and transition records. API: POST /api/v1/runs/{id}/discovery; GET /api/v1/runs/{id}/discovery. Events: DISCOVERY_STARTED/SCANNER_COMPLETED/COMPLETED/BLOCKED. Artifacts: Workspace/project, dependency, builder, test/lint, SSR/PWA/i18n, UI library/theme, and state-management inventories.
  - **Out of scope:** Route/backend contract deep comparison, AI interpretation, compatibility support level, and mutation.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Discovery summary, scanner statuses, artifact references, and transition records.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/discovery; GET /api/v1/runs/{id}/discovery; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: DISCOVERY_STARTED/SCANNER_COMPLETED/COMPLETED/BLOCKED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Workspace/project, dependency, builder, test/lint, SSR/PWA/i18n, UI library/theme, and state-management inventories.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S2-F01-I01
  - **Suggested labels:** sprint-2, s2-f01, product-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F01-I03 — Build frontend experience for Display deterministic workspace, dependency, builder, and test discovery findings

  - **Parent feature:** S2-F01
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Display deterministic workspace, dependency, builder, and test discovery findings, using backend snapshots and durable events only.
  - **Context:** Feasibility and AI analysis must consume machine facts rather than allowing an LLM to invent project truth.
  - **Scope:** Deterministic findings explorer with scanner status, filters, fact/unknown labels, source references, and artifact drill-down.
  - **Out of scope:** Route/backend contract deep comparison, AI interpretation, compatibility support level, and mutation.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/discovery; GET /api/v1/runs/{id}/discovery` plus durable events `DISCOVERY_STARTED/SCANNER_COMPLETED/COMPLETED/BLOCKED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Deterministic findings explorer with scanner status, filters, fact/unknown labels, source references, and artifact drill-down.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/discovery; GET /api/v1/runs/{id}/discovery` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `DISCOVERY_STARTED/SCANNER_COMPLETED/COMPLETED/BLOCKED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Workspace/project, dependency, builder, test/lint, SSR/PWA/i18n, UI library/theme, and state-management inventories.
  - **UI impact:** Implement: Deterministic findings explorer with scanner status, filters, fact/unknown labels, source references, and artifact drill-down.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S2-F01-I02
  - **Suggested labels:** sprint-2, s2-f01, product-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S2-F01-I04 — Verify and document Display deterministic workspace, dependency, builder, and test discovery findings

  - **Parent feature:** S2-F01
  - **Issue type:** Testing
  - **Technical story:** Prove Display deterministic workspace, dependency, builder, and test discovery findings through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Feasibility and AI analysis must consume machine facts rather than allowing an LLM to invent project truth.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Route/backend contract deep comparison, AI interpretation, compatibility support level, and mutation.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/discovery; GET /api/v1/runs/{id}/discovery` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `DISCOVERY_STARTED/SCANNER_COMPLETED/COMPLETED/BLOCKED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Workspace/project, dependency, builder, test/lint, SSR/PWA/i18n, UI library/theme, and state-management inventories.` where applicable.
  - **UI impact:** Execute the feature through `Deterministic findings explorer with scanner status, filters, fact/unknown labels, source references, and artifact drill-down.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Scanner overlap, nondeterministic results, large workspace, unsupported topology, malicious file content, and partial scanner failure.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S2-F01-I03
  - **Suggested labels:** sprint-2, s2-f01, product-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### S2-F02 — Inspect routes, backend integration, and behavior-sensitive hotspots

#### Feature identity

- **Sprint:** Sprint 2
- **Feature type:** Validation capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A reviewer can inspect route/guard/resolver inventory, backend API/auth/environment integration, forms, themes, and high-risk source hotspots that will become parity baselines.

#### Context

Strict functional parity requires explicit structural evidence for behavior-sensitive areas before mutation.

**Governing specification sections:** 16, 25, 27, 59.7, 63.6-63.8

#### Scope

Structural baseline evidence and sensitivity classification for supported single-app workspaces.

#### Out of scope

Automated browser/visual proof, runtime traffic capture, and stage comparison.

#### Backend slice

- **Application service/components:** RouteInventoryBuilder, BackendContractSnapshotBuilder, SensitiveFilePolicy, form/theme/auth/interceptor scanners, deterministic risk classification, and parity baseline assembly.
- **Domain aggregate/projection:** ParityBaseline and DiscoveryFinding.
- **Persistence:** Parity baseline summary and artifact references.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/discovery/parity-baseline; GET /api/v1/runs/{id}/discovery/parity-baseline`
- **Durable event:** PARITY_BASELINE_STARTED/COMPLETED/BLOCKED.
- **Artifact Store output:** Route inventory, backend integration snapshot, sensitive-file inventory, UI/theme/form evidence, and parity manifest.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Parity evidence viewer with route tree, API/auth tables, risk filters, unknown/manual indicators, and source-artifact links.
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
→ RouteInventoryBuilder, BackendContractSnapshotBuilder, SensitiveFilePolicy, form/theme/auth/interceptor scanners, deterministic risk classification, and parity baseline assembly.
→ Parity baseline summary and artifact references.
→ ArtifactService finalizes evidence: Route inventory, backend integration snapshot, sensitive-file inventory, UI/theme/form evidence, and parity manifest.
→ Transition/Event service persists and emits: PARITY_BASELINE_STARTED/COMPLETED/BLOCKED.
→ SSE replay or snapshot refresh
→ Parity evidence viewer with route tree, API/auth tables, risk filters, unknown/manual indicators, and source-artifact links.
```

#### Sub-issues

- `S2-F02-I01` — Backend/application contract
- `S2-F02-I02` — Persistence, API, durable event, and artifact contract
- `S2-F02-I03` — Frontend projection and interaction
- `S2-F02-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Inspect routes, backend integration, and behavior-sensitive hotspots**, then the backend performs only the authorized service operation, persists the result, emits the documented **PARITY_BASELINE_STARTED/COMPLETED/BLOCKED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Parity baseline summary and artifact references.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Route inventory, backend integration snapshot, sensitive-file inventory, UI/theme/form evidence, and parity manifest.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S2-F01; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Parity evidence viewer with route tree, API/auth tables, risk filters, unknown/manual indicators, and source-artifact links.**.
3. Trigger the primary action for **Inspect routes, backend integration, and behavior-sensitive hotspots** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can inspect route/guard/resolver inventory, backend API/auth/environment integration, forms, themes, and high-risk source hotspots that will become parity baselines. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Parity baseline summary and artifact references.` are retrievable through `POST /api/v1/runs/{id}/discovery/parity-baseline; GET /api/v1/runs/{id}/discovery/parity-baseline` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Route inventory, backend integration snapshot, sensitive-file inventory, UI/theme/form evidence, and parity manifest.

**Expected durable event:** PARITY_BASELINE_STARTED/COMPLETED/BLOCKED.

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

S2-F01

#### Risks and edge cases

- Dynamic routes/endpoints not statically detectable
- secret literals
- false sensitivity level
- generated code
- and overclaiming parity.

#### Detailed sub-issues

#### S2-F02-I01 — Implement backend application contract for Inspect routes, backend integration, and behavior-sensitive hotspots

  - **Parent feature:** S2-F02
  - **Issue type:** Validation
  - **Technical story:** Implement the bounded backend/application behavior for Inspect routes, backend integration, and behavior-sensitive hotspots so the feature has one authoritative service path.
  - **Context:** Strict functional parity requires explicit structural evidence for behavior-sensitive areas before mutation.
  - **Scope:** RouteInventoryBuilder, BackendContractSnapshotBuilder, SensitiveFilePolicy, form/theme/auth/interceptor scanners, deterministic risk classification, and parity baseline assembly.
  - **Out of scope:** Automated browser/visual proof, runtime traffic capture, and stage comparison.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/discovery/parity-baseline; GET /api/v1/runs/{id}/discovery/parity-baseline`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: RouteInventoryBuilder, BackendContractSnapshotBuilder, SensitiveFilePolicy, form/theme/auth/interceptor scanners, deterministic risk classification, and parity baseline assembly.
  - **Database impact:** Use or introduce the records summarized by: Parity baseline summary and artifact references.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/discovery/parity-baseline; GET /api/v1/runs/{id}/discovery/parity-baseline
  - **Event impact:** Request durable events only through the transition/event service: PARITY_BASELINE_STARTED/COMPLETED/BLOCKED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Route inventory, backend integration snapshot, sensitive-file inventory, UI/theme/form evidence, and parity manifest.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Dynamic routes/endpoints not statically detectable, secret literals, false sensitivity level, generated code, and overclaiming parity.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's validation behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S2-F01
  - **Suggested labels:** sprint-2, s2-f02, validation-capability, validation, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F02-I02 — Persist and expose evidence contracts for Inspect routes, backend integration, and behavior-sensitive hotspots

  - **Parent feature:** S2-F02
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Inspect routes, backend integration, and behavior-sensitive hotspots observable and auditable.
  - **Context:** Strict functional parity requires explicit structural evidence for behavior-sensitive areas before mutation.
  - **Scope:** Persistence: Parity baseline summary and artifact references. API: POST /api/v1/runs/{id}/discovery/parity-baseline; GET /api/v1/runs/{id}/discovery/parity-baseline. Events: PARITY_BASELINE_STARTED/COMPLETED/BLOCKED. Artifacts: Route inventory, backend integration snapshot, sensitive-file inventory, UI/theme/form evidence, and parity manifest.
  - **Out of scope:** Automated browser/visual proof, runtime traffic capture, and stage comparison.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Parity baseline summary and artifact references.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/discovery/parity-baseline; GET /api/v1/runs/{id}/discovery/parity-baseline; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: PARITY_BASELINE_STARTED/COMPLETED/BLOCKED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Route inventory, backend integration snapshot, sensitive-file inventory, UI/theme/form evidence, and parity manifest.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S2-F02-I01
  - **Suggested labels:** sprint-2, s2-f02, validation-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F02-I03 — Build frontend experience for Inspect routes, backend integration, and behavior-sensitive hotspots

  - **Parent feature:** S2-F02
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Inspect routes, backend integration, and behavior-sensitive hotspots, using backend snapshots and durable events only.
  - **Context:** Strict functional parity requires explicit structural evidence for behavior-sensitive areas before mutation.
  - **Scope:** Parity evidence viewer with route tree, API/auth tables, risk filters, unknown/manual indicators, and source-artifact links.
  - **Out of scope:** Automated browser/visual proof, runtime traffic capture, and stage comparison.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/discovery/parity-baseline; GET /api/v1/runs/{id}/discovery/parity-baseline` plus durable events `PARITY_BASELINE_STARTED/COMPLETED/BLOCKED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Parity evidence viewer with route tree, API/auth tables, risk filters, unknown/manual indicators, and source-artifact links.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/discovery/parity-baseline; GET /api/v1/runs/{id}/discovery/parity-baseline` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `PARITY_BASELINE_STARTED/COMPLETED/BLOCKED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Route inventory, backend integration snapshot, sensitive-file inventory, UI/theme/form evidence, and parity manifest.
  - **UI impact:** Implement: Parity evidence viewer with route tree, API/auth tables, risk filters, unknown/manual indicators, and source-artifact links.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S2-F02-I02
  - **Suggested labels:** sprint-2, s2-f02, validation-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S2-F02-I04 — Verify and document Inspect routes, backend integration, and behavior-sensitive hotspots

  - **Parent feature:** S2-F02
  - **Issue type:** Testing
  - **Technical story:** Prove Inspect routes, backend integration, and behavior-sensitive hotspots through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Strict functional parity requires explicit structural evidence for behavior-sensitive areas before mutation.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Automated browser/visual proof, runtime traffic capture, and stage comparison.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/discovery/parity-baseline; GET /api/v1/runs/{id}/discovery/parity-baseline` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `PARITY_BASELINE_STARTED/COMPLETED/BLOCKED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Route inventory, backend integration snapshot, sensitive-file inventory, UI/theme/form evidence, and parity manifest.` where applicable.
  - **UI impact:** Execute the feature through `Parity evidence viewer with route tree, API/auth tables, risk filters, unknown/manual indicators, and source-artifact links.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Dynamic routes/endpoints not statically detectable, secret literals, false sensitivity level, generated code, and overclaiming parity.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S2-F02-I03
  - **Suggested labels:** sprint-2, s2-f02, validation-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### S2-F03 — Invoke Azure OpenAI through a governed role-routed gateway

#### Feature identity

- **Sprint:** Sprint 2
- **Feature type:** Operational capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

An operator can run a schema-constrained test invocation, inspect provider/deployment/prompt/schema provenance, input/output/total tokens, estimated input/output/total cost, retries, latency, and budget status.

#### Context

All agents use one backend gateway with redaction, structured-output validation, cost evidence, and no hidden chain-of-thought storage.

**Governing specification sections:** 39, 51.7, 64.5-64.6, 68.6

#### Scope

Backend-only gateway, structured-output validation foundation, input/output/total tokens and costs, budget controls, and UI.

#### Out of scope

Cached/reasoning token display, direct browser calls, model-driven commands, and autonomous budget override.

#### Backend slice

- **Application service/components:** AzureOpenAILLMGateway, deployment configuration, prompt/schema registry, structured output adapter, timeout/transport retry, Pydantic/semantic validation hook, token usage extraction, fixed pricing snapshot, budget policy, and sanitization.
- **Domain aggregate/projection:** LLMInvocation and UsageCostRecord.
- **Persistence:** llm_invocations and usage_cost_records with prompt/schema/model/pricing versions and artifact hashes.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `GET /api/v1/llm/readiness; POST /api/v1/llm/smoke; GET /api/v1/runs/{id}/llm/activity; GET /api/v1/runs/{id}/usage`
- **Durable event:** LLM_INVOCATION_STARTED/COMPLETED/FAILED and LLM_BUDGET_WARNING/BLOCKED.
- **Artifact Store output:** Sanitized request manifest, validated structured response, redacted error, and usage/cost report.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** LLM diagnostics/usage panel with provenance, usage totals, costs, retries, budget status, and configuration/model failure states.
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
→ AzureOpenAILLMGateway, deployment configuration, prompt/schema registry, structured output adapter, timeout/transport retry, Pydantic/semantic validation hook, token usage extraction, fixed pricing snapshot, budget policy, and sanitization.
→ llm_invocations and usage_cost_records with prompt/schema/model/pricing versions and artifact hashes.
→ ArtifactService finalizes evidence: Sanitized request manifest, validated structured response, redacted error, and usage/cost report.
→ Transition/Event service persists and emits: LLM_INVOCATION_STARTED/COMPLETED/FAILED and LLM_BUDGET_WARNING/BLOCKED.
→ SSE replay or snapshot refresh
→ LLM diagnostics/usage panel with provenance, usage totals, costs, retries, budget status, and configuration/model failure states.
```

#### Required production LLM governance

- Implement one backend-only Azure OpenAI model client, one role router, one prompt/schema registry, and one model-capability registry.
- Prefer the Azure OpenAI v1 Responses API and Structured Outputs where the selected deployment supports them; use Chat Completions only through an explicit capability adapter.
- When strict structured function calling is used, set `parallel_tool_calls=false` and reject capability combinations that cannot guarantee the configured schema contract.
- Use API-key authentication for the local MVP while keeping an authentication-provider abstraction for future Microsoft Entra ID.
- Set provider storage to disabled (`store=false`) for phase, repair, assistant, and report requests unless a separately approved retention policy changes this.
- Separate roles: `assistant`, `phase_proposer`, `phase_reviewer`, `repair_proposer`, `repair_reviewer`, `report_narrator`, and `fallback`. Multiple roles may map to the same GPT-5 mini deployment in the MVP.
- Separate responsibilities and policies for analysis review, planning review, repair proposal, repair review, assistant answers, report narrative, and smoke checks.
- Classify configuration, authentication, authorization, deployment, capability, rate limit, quota, timeout, network, server, protocol, content filter, schema, semantic, empty-output, and cancellation failures distinctly.
- Persist every invocation in an append-only privacy-preserving ledger. Store role, responsibility, safe deployment alias hash, versions, checksums, retries, latency, tokens, pricing snapshot, estimated cost, redacted summary, and redacted failure. Never store raw prompts, raw completions, API keys, endpoints, deployment values, or hidden reasoning.
- Keep transport retries, protocol fallback, structured-output regeneration, phase-review revisions, repair-review revisions, and semantic repair attempts as independent counters.
- The smoke check proves connectivity and simple parsing only; it does not prove that analysis, planning, or repair prompts and schemas will succeed.
- Label locally calculated money as **estimated cost using the project pricing snapshot**, not Azure-billed cost.

#### Sub-issues

- `S2-F03-I01` — Backend/application contract
- `S2-F03-I02` — Persistence, API, durable event, and artifact contract
- `S2-F03-I03` — Frontend projection and interaction
- `S2-F03-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Invoke Azure OpenAI through a governed gateway and display token cost**, then the backend performs only the authorized service operation, persists the result, emits the documented **LLM_INVOCATION_STARTED/COMPLETED/FAILED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **llm_invocations and usage_cost_records with prompt/schema/model/pricing versions and artifact hashes.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Sanitized request manifest, validated structured response, redacted error, and usage/cost report.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S1-F14, S2-F02; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **LLM diagnostics/usage panel with provenance, usage totals, costs, retries, budget status, and configuration/model failure states.**.
3. Trigger the primary action for **Invoke Azure OpenAI through a governed gateway and display token cost** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** An operator can run a schema-constrained test invocation, inspect provider/deployment/prompt/schema provenance, input/output/total tokens, estimated input/output/total cost, retries, latency, and budget status. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `llm_invocations and usage_cost_records with prompt/schema/model/pricing versions and artifact hashes.` are retrievable through `GET /api/v1/llm/readiness; POST /api/v1/llm/smoke; GET /api/v1/runs/{id}/llm/activity; GET /api/v1/runs/{id}/usage` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Sanitized request manifest, validated structured response, redacted error, and usage/cost report.

**Expected durable event:** LLM_INVOCATION_STARTED/COMPLETED/FAILED and LLM_BUDGET_WARNING/BLOCKED.

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

S1-F14, S2-F02

#### Risks and edge cases

- Price configuration drift
- missing usage metadata
- Azure outage/quota
- schema unsupported
- secrets
- prompt logging
- and retry double-counting.

#### Detailed sub-issues

#### S2-F03-I01 — Implement backend application contract for Invoke Azure OpenAI through a governed gateway and display token cost

  - **Parent feature:** S2-F03
  - **Issue type:** Agent
  - **Technical story:** Implement the bounded backend/application behavior for Invoke Azure OpenAI through a governed gateway and display token cost so the feature has one authoritative service path.
  - **Context:** All agents use one backend gateway with redaction, structured-output validation, cost evidence, and no hidden chain-of-thought storage.
  - **Scope:** AzureOpenAILLMGateway, deployment configuration, prompt/schema registry, structured output adapter, timeout/transport retry, Pydantic/semantic validation hook, token usage extraction, fixed pricing snapshot, budget policy, and sanitization.
  - **Out of scope:** Cached/reasoning token display, direct browser calls, model-driven commands, and autonomous budget override.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `GET /api/v1/llm/readiness; POST /api/v1/llm/smoke; GET /api/v1/runs/{id}/llm/activity; GET /api/v1/runs/{id}/usage`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: AzureOpenAILLMGateway, deployment configuration, prompt/schema registry, structured output adapter, timeout/transport retry, Pydantic/semantic validation hook, token usage extraction, fixed pricing snapshot, budget policy, and sanitization.
  - **Database impact:** Use or introduce the records summarized by: llm_invocations and usage_cost_records with prompt/schema/model/pricing versions and artifact hashes.
  - **API impact:** Define service-facing request/response models supporting: GET /api/v1/llm/readiness; POST /api/v1/llm/smoke; GET /api/v1/runs/{id}/llm/activity; GET /api/v1/runs/{id}/usage
  - **Event impact:** Request durable events only through the transition/event service: LLM_INVOCATION_STARTED/COMPLETED/FAILED and LLM_BUDGET_WARNING/BLOCKED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Sanitized request manifest, validated structured response, redacted error, and usage/cost report.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Price configuration drift, missing usage metadata, Azure outage/quota, schema unsupported, secrets, prompt logging, and retry double-counting.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's agent behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S1-F14, S2-F02
  - **Suggested labels:** sprint-2, s2-f03, operational-capability, agent, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F03-I02 — Persist and expose evidence contracts for Invoke Azure OpenAI through a governed gateway and display token cost

  - **Parent feature:** S2-F03
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Invoke Azure OpenAI through a governed gateway and display token cost observable and auditable.
  - **Context:** All agents use one backend gateway with redaction, structured-output validation, cost evidence, and no hidden chain-of-thought storage.
  - **Scope:** Persistence: llm_invocations and usage_cost_records with prompt/schema/model/pricing versions and artifact hashes. API: GET /api/v1/llm/readiness; POST /api/v1/llm/smoke; GET /api/v1/runs/{id}/llm/activity; GET /api/v1/runs/{id}/usage. Events: LLM_INVOCATION_STARTED/COMPLETED/FAILED and LLM_BUDGET_WARNING/BLOCKED. Artifacts: Sanitized request manifest, validated structured response, redacted error, and usage/cost report.
  - **Out of scope:** Cached/reasoning token display, direct browser calls, model-driven commands, and autonomous budget override.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: llm_invocations and usage_cost_records with prompt/schema/model/pricing versions and artifact hashes.
  - **API impact:** Implement and document: GET /api/v1/llm/readiness; POST /api/v1/llm/smoke; GET /api/v1/runs/{id}/llm/activity; GET /api/v1/runs/{id}/usage; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: LLM_INVOCATION_STARTED/COMPLETED/FAILED and LLM_BUDGET_WARNING/BLOCKED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Sanitized request manifest, validated structured response, redacted error, and usage/cost report.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S2-F03-I01
  - **Suggested labels:** sprint-2, s2-f03, operational-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F03-I03 — Build frontend experience for Invoke Azure OpenAI through a governed gateway and display token cost

  - **Parent feature:** S2-F03
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Invoke Azure OpenAI through a governed gateway and display token cost, using backend snapshots and durable events only.
  - **Context:** All agents use one backend gateway with redaction, structured-output validation, cost evidence, and no hidden chain-of-thought storage.
  - **Scope:** LLM diagnostics/usage panel with provenance, usage totals, costs, retries, budget status, and configuration/model failure states.
  - **Out of scope:** Cached/reasoning token display, direct browser calls, model-driven commands, and autonomous budget override.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `GET /api/v1/llm/readiness; POST /api/v1/llm/smoke; GET /api/v1/runs/{id}/llm/activity; GET /api/v1/runs/{id}/usage` plus durable events `LLM_INVOCATION_STARTED/COMPLETED/FAILED and LLM_BUDGET_WARNING/BLOCKED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: LLM diagnostics/usage panel with provenance, usage totals, costs, retries, budget status, and configuration/model failure states.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `GET /api/v1/llm/readiness; POST /api/v1/llm/smoke; GET /api/v1/runs/{id}/llm/activity; GET /api/v1/runs/{id}/usage` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `LLM_INVOCATION_STARTED/COMPLETED/FAILED and LLM_BUDGET_WARNING/BLOCKED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Sanitized request manifest, validated structured response, redacted error, and usage/cost report.
  - **UI impact:** Implement: LLM diagnostics/usage panel with provenance, usage totals, costs, retries, budget status, and configuration/model failure states.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S2-F03-I02
  - **Suggested labels:** sprint-2, s2-f03, operational-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S2-F03-I04 — Verify and document Invoke Azure OpenAI through a governed gateway and display token cost

  - **Parent feature:** S2-F03
  - **Issue type:** Testing
  - **Technical story:** Prove Invoke Azure OpenAI through a governed gateway and display token cost through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** All agents use one backend gateway with redaction, structured-output validation, cost evidence, and no hidden chain-of-thought storage.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Cached/reasoning token display, direct browser calls, model-driven commands, and autonomous budget override.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `GET /api/v1/llm/readiness; POST /api/v1/llm/smoke; GET /api/v1/runs/{id}/llm/activity; GET /api/v1/runs/{id}/usage` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `LLM_INVOCATION_STARTED/COMPLETED/FAILED and LLM_BUDGET_WARNING/BLOCKED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Sanitized request manifest, validated structured response, redacted error, and usage/cost report.` where applicable.
  - **UI impact:** Execute the feature through `LLM diagnostics/usage panel with provenance, usage totals, costs, retries, budget status, and configuration/model failure states.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Price configuration drift, missing usage metadata, Azure outage/quota, schema unsupported, secrets, prompt logging, and retry double-counting.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S2-F03-I03
  - **Suggested labels:** sprint-2, s2-f03, operational-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### S2-F04 — Generate a checksum-bound Analysis phase review chain and decide G04

#### Feature identity

- **Sprint:** Sprint 2
- **Feature type:** Approval capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G04

#### User-observable outcome

A reviewer can compare deterministic facts with a structured AI interpretation, inspect provenance/tokens/cost, and approve, modify, or reject G04.

#### Context

The Analysis Agent improves explanation and risk grouping but cannot alter deterministic facts, support status, or execute actions.

**Governing specification sections:** 37, 39, 52.3, 56.5, 59.8-59.9

#### Scope

Analysis Agent only, structured output, semantic checks, fact separation, token/cost capture, and G04.

#### Out of scope

Planning Agent, Proposer/Reviewer repair roles, arbitrary repository browsing, and support-level determination by AI.

#### Backend slice

- **Application service/components:** AnalysisAgentService through the LLM Gateway abstraction, bounded deterministic input artifact references, structured schema/Pydantic/semantic validation, prompt/schema versioning, retries, usage record, and G04 package.
- **Domain aggregate/projection:** LLMInvocation, AnalysisNarrative, ApprovalGate G04.
- **Persistence:** llm_invocations, usage_cost_records, analysis metadata, gate/decision records.
- **State/approval rule:** G04 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/analysis; GET /api/v1/runs/{id}/analysis; POST /api/v1/runs/{id}/approvals/G04/decisions`
- **Durable event:** ANALYSIS_AGENT_STARTED/COMPLETED/FAILED and G04 events.
- **Artifact Store output:** Sanitized model input manifest, structured response, human-readable analysis, usage/cost record, and G04 package.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Split-view analysis page separating machine facts from AI interpretation, model provenance, token/cost panel, invalid/failed state, and G04 controls.
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
→ AnalysisAgentService through the LLM Gateway abstraction, bounded deterministic input artifact references, structured schema/Pydantic/semantic validation, prompt/schema versioning, retries, usage record, and G04 package.
→ llm_invocations, usage_cost_records, analysis metadata, gate/decision records.
→ ArtifactService finalizes evidence: Sanitized model input manifest, structured response, human-readable analysis, usage/cost record, and G04 package.
→ Transition/Event service persists and emits: ANALYSIS_AGENT_STARTED/COMPLETED/FAILED and G04 events.
→ SSE replay or snapshot refresh
→ Split-view analysis page separating machine facts from AI interpretation, model provenance, token/cost panel, invalid/failed state, and G04 controls.
```

#### Mandatory Analysis phase review chain

```text
deterministic analysis artifact
→ canonical input checksum
→ phase Proposer
→ provider/schema/Pydantic/semantic validation
→ Proposer output checksum
→ phase Reviewer
→ checksum, evidence, minimality, and policy validation
→ final reviewed analysis artifact
→ G04 human decision
```

The phase Proposer may summarize facts, group risks, cite evidence, identify unresolved questions, and recommend the next workflow action. It cannot create commands, patches, approvals, support status, or target-version truth.

The phase Reviewer returns only `accept`, `request_revision`, `reject`, or `insufficient_context`, plus notes, risks, policy concerns, confidence, deterministic-input checksum, and Proposer-output checksum. It cannot silently replace the analysis content.

When AI review is mandatory, the primary role may use only an explicitly configured Azure fallback deployment. If both fail or return invalid output, the feature fails closed and G04 is not presented as reviewed.

#### Sub-issues

- `S2-F04-I01` — Backend/application contract
- `S2-F04-I02` — Persistence, API, durable event, and artifact contract
- `S2-F04-I03` — Frontend projection and interaction
- `S2-F04-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Generate AI-assisted analysis and decide G04 analysis acceptance**, then the backend performs only the authorized service operation, persists the result, emits the documented **ANALYSIS_AGENT_STARTED/COMPLETED/FAILED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **llm_invocations, usage_cost_records, analysis metadata, gate/decision records.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Sanitized model input manifest, structured response, human-readable analysis, usage/cost record, and G04 package.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G04 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G04 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.

#### Manual end-to-end test scenario

**Preconditions:** S1-F14, S2-F01, S2-F02; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Split-view analysis page separating machine facts from AI interpretation, model provenance, token/cost panel, invalid/failed state, and G04 controls.**.
    3. Trigger the primary action for **Generate AI-assisted analysis and decide G04 analysis acceptance** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G04** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can compare deterministic facts with a structured AI interpretation, inspect provenance/tokens/cost, and approve, modify, or reject G04. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `llm_invocations, usage_cost_records, analysis metadata, gate/decision records.` are retrievable through `POST /api/v1/runs/{id}/analysis; GET /api/v1/runs/{id}/analysis; POST /api/v1/runs/{id}/approvals/G04/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Sanitized model input manifest, structured response, human-readable analysis, usage/cost record, and G04 package.

    **Expected durable event:** ANALYSIS_AGENT_STARTED/COMPLETED/FAILED and G04 events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G04 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

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

S1-F14, S2-F01, S2-F02

#### Risks and edge cases

- Prompt injection
- secret leakage
- hallucinated facts
- schema mismatch
- model outage
- budget exhaustion
- and stale analysis inputs.

#### Detailed sub-issues

#### S2-F04-I01 — Implement backend application contract for Generate AI-assisted analysis and decide G04 analysis acceptance

  - **Parent feature:** S2-F04
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Generate AI-assisted analysis and decide G04 analysis acceptance so the feature has one authoritative service path.
  - **Context:** The Analysis Agent improves explanation and risk grouping but cannot alter deterministic facts, support status, or execute actions.
  - **Scope:** AnalysisAgentService through the LLM Gateway abstraction, bounded deterministic input artifact references, structured schema/Pydantic/semantic validation, prompt/schema versioning, retries, usage record, and G04 package.
  - **Out of scope:** Planning Agent, Proposer/Reviewer repair roles, arbitrary repository browsing, and support-level determination by AI.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G04 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/analysis; GET /api/v1/runs/{id}/analysis; POST /api/v1/runs/{id}/approvals/G04/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: AnalysisAgentService through the LLM Gateway abstraction, bounded deterministic input artifact references, structured schema/Pydantic/semantic validation, prompt/schema versioning, retries, usage record, and G04 package.
  - **Database impact:** Use or introduce the records summarized by: llm_invocations, usage_cost_records, analysis metadata, gate/decision records.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/analysis; GET /api/v1/runs/{id}/analysis; POST /api/v1/runs/{id}/approvals/G04/decisions
  - **Event impact:** Request durable events only through the transition/event service: ANALYSIS_AGENT_STARTED/COMPLETED/FAILED and G04 events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Sanitized model input manifest, structured response, human-readable analysis, usage/cost record, and G04 package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Prompt injection, secret leakage, hallucinated facts, schema mismatch, model outage, budget exhaustion, and stale analysis inputs.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G04 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S1-F14, S2-F01, S2-F02
  - **Suggested labels:** sprint-2, s2-f04, approval-capability, backend, g04, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F04-I02 — Persist and expose evidence contracts for Generate AI-assisted analysis and decide G04 analysis acceptance

  - **Parent feature:** S2-F04
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Generate AI-assisted analysis and decide G04 analysis acceptance observable and auditable.
  - **Context:** The Analysis Agent improves explanation and risk grouping but cannot alter deterministic facts, support status, or execute actions.
  - **Scope:** Persistence: llm_invocations, usage_cost_records, analysis metadata, gate/decision records. API: POST /api/v1/runs/{id}/analysis; GET /api/v1/runs/{id}/analysis; POST /api/v1/runs/{id}/approvals/G04/decisions. Events: ANALYSIS_AGENT_STARTED/COMPLETED/FAILED and G04 events. Artifacts: Sanitized model input manifest, structured response, human-readable analysis, usage/cost record, and G04 package.
  - **Out of scope:** Planning Agent, Proposer/Reviewer repair roles, arbitrary repository browsing, and support-level determination by AI.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: llm_invocations, usage_cost_records, analysis metadata, gate/decision records.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/analysis; GET /api/v1/runs/{id}/analysis; POST /api/v1/runs/{id}/approvals/G04/decisions; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: ANALYSIS_AGENT_STARTED/COMPLETED/FAILED and G04 events.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Sanitized model input manifest, structured response, human-readable analysis, usage/cost record, and G04 package.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G04 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S2-F04-I01
  - **Suggested labels:** sprint-2, s2-f04, approval-capability, api, g04, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F04-I03 — Build frontend experience for Generate AI-assisted analysis and decide G04 analysis acceptance

  - **Parent feature:** S2-F04
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Generate AI-assisted analysis and decide G04 analysis acceptance, using backend snapshots and durable events only.
  - **Context:** The Analysis Agent improves explanation and risk grouping but cannot alter deterministic facts, support status, or execute actions.
  - **Scope:** Split-view analysis page separating machine facts from AI interpretation, model provenance, token/cost panel, invalid/failed state, and G04 controls.
  - **Out of scope:** Planning Agent, Proposer/Reviewer repair roles, arbitrary repository browsing, and support-level determination by AI.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/analysis; GET /api/v1/runs/{id}/analysis; POST /api/v1/runs/{id}/approvals/G04/decisions` plus durable events `ANALYSIS_AGENT_STARTED/COMPLETED/FAILED and G04 events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Split-view analysis page separating machine facts from AI interpretation, model provenance, token/cost panel, invalid/failed state, and G04 controls.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/analysis; GET /api/v1/runs/{id}/analysis; POST /api/v1/runs/{id}/approvals/G04/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `ANALYSIS_AGENT_STARTED/COMPLETED/FAILED and G04 events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Sanitized model input manifest, structured response, human-readable analysis, usage/cost record, and G04 package.
  - **UI impact:** Implement: Split-view analysis page separating machine facts from AI interpretation, model provenance, token/cost panel, invalid/failed state, and G04 controls.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G04 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S2-F04-I02
  - **Suggested labels:** sprint-2, s2-f04, approval-capability, frontend, g04, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S2-F04-I04 — Verify and document Generate AI-assisted analysis and decide G04 analysis acceptance

  - **Parent feature:** S2-F04
  - **Issue type:** Testing
  - **Technical story:** Prove Generate AI-assisted analysis and decide G04 analysis acceptance through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** The Analysis Agent improves explanation and risk grouping but cannot alter deterministic facts, support status, or execute actions.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Planning Agent, Proposer/Reviewer repair roles, arbitrary repository browsing, and support-level determination by AI.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/analysis; GET /api/v1/runs/{id}/analysis; POST /api/v1/runs/{id}/approvals/G04/decisions` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `ANALYSIS_AGENT_STARTED/COMPLETED/FAILED and G04 events.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Sanitized model input manifest, structured response, human-readable analysis, usage/cost record, and G04 package.` where applicable.
  - **UI impact:** Execute the feature through `Split-view analysis page separating machine facts from AI interpretation, model provenance, token/cost panel, invalid/failed state, and G04 controls.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Prompt injection, secret leakage, hallucinated facts, schema mismatch, model outage, budget exhaustion, and stale analysis inputs.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G04 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S2-F04-I03
  - **Suggested labels:** sprint-2, s2-f04, approval-capability, testing, g04, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### S2-F05 — Resolve the family route, support level, and exact Stage 1 profile with G05

#### Feature identity

- **Sprint:** Sprint 2
- **Feature type:** Approval capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G05

#### User-observable outcome

A reviewer can see the deterministic 18.x→19.x→20.x→21.x ladder, support classification, exact Stage 1 Angular/CLI/Node/npm choices, blockers, and decide G05.

#### Context

Family acceptance and exact execution resolution are separate. The route and support truth come from the versioned compatibility catalogue, never an LLM.

**Governing specification sections:** 4, 17-18, 50-51, 56.6, 57-58, ADR-003/011

#### Scope

MVP 18.x to approved 21.x route, support levels, exact first-stage toolchain resolution, policy/version locking, and G05.

#### Out of scope

Angular 11-17 validated paths, Angular 22, executing commands, and LLM-selected versions.

#### Backend slice

- **Application service/components:** Versioned CompatibilityCatalogue, CompatibilityResolver, registry snapshot adapter, support policy, major-ladder generator, exact Stage 1 resolution, profile selection, checksum lock, and G05 package.
- **Domain aggregate/projection:** CompatibilityResolution, ExecutionProfile, ApprovalGate G05.
- **Persistence:** compatibility catalogue metadata, resolutions, registry snapshot metadata, selected profile, gate/decisions.
- **State/approval rule:** G05 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/feasibility; GET /api/v1/runs/{id}/feasibility; POST /api/v1/runs/{id}/approvals/G05/decisions`
- **Durable event:** COMPATIBILITY_RESOLUTION_STARTED/COMPLETED/BLOCKED and G05 events.
- **Artifact Store output:** Catalogue snapshot reference, route, support-level evidence, registry snapshot checksum, exact Stage 1 resolution, and feasibility package.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Feasibility view with stage ladder, support badges, exact profile table, candidate runtimes, warnings/blockers, and G05 controls.
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
→ Versioned CompatibilityCatalogue, CompatibilityResolver, registry snapshot adapter, support policy, major-ladder generator, exact Stage 1 resolution, profile selection, checksum lock, and G05 package.
→ compatibility catalogue metadata, resolutions, registry snapshot metadata, selected profile, gate/decisions.
→ ArtifactService finalizes evidence: Catalogue snapshot reference, route, support-level evidence, registry snapshot checksum, exact Stage 1 resolution, and feasibility package.
→ Transition/Event service persists and emits: COMPATIBILITY_RESOLUTION_STARTED/COMPLETED/BLOCKED and G05 events.
→ SSE replay or snapshot refresh
→ Feasibility view with stage ladder, support badges, exact profile table, candidate runtimes, warnings/blockers, and G05 controls.
```

#### Sub-issues

- `S2-F05-I01` — Backend/application contract
- `S2-F05-I02` — Persistence, API, durable event, and artifact contract
- `S2-F05-I03` — Frontend projection and interaction
- `S2-F05-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Resolve the family route, support level, and exact Stage 1 profile with G05**, then the backend performs only the authorized service operation, persists the result, emits the documented **COMPATIBILITY_RESOLUTION_STARTED/COMPLETED/BLOCKED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **compatibility catalogue metadata, resolutions, registry snapshot metadata, selected profile, gate/decisions.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Catalogue snapshot reference, route, support-level evidence, registry snapshot checksum, exact Stage 1 resolution, and feasibility package.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G05 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G05 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.

#### Manual end-to-end test scenario

**Preconditions:** S1-F09, S2-F04; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Feasibility view with stage ladder, support badges, exact profile table, candidate runtimes, warnings/blockers, and G05 controls.**.
    3. Trigger the primary action for **Resolve the family route, support level, and exact Stage 1 profile with G05** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G05** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can see the deterministic 18.x→19.x→20.x→21.x ladder, support classification, exact Stage 1 Angular/CLI/Node/npm choices, blockers, and decide G05. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `compatibility catalogue metadata, resolutions, registry snapshot metadata, selected profile, gate/decisions.` are retrievable through `POST /api/v1/runs/{id}/feasibility; GET /api/v1/runs/{id}/feasibility; POST /api/v1/runs/{id}/approvals/G05/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Catalogue snapshot reference, route, support-level evidence, registry snapshot checksum, exact Stage 1 resolution, and feasibility package.

    **Expected durable event:** COMPATIBILITY_RESOLUTION_STARTED/COMPLETED/BLOCKED and G05 events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G05 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

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

S1-F09, S2-F04

#### Risks and edge cases

- Registry drift
- incompatible exact patch
- private-package constraints
- unavailable runtime
- stale catalogue
- and labeling Angular 21 as latest.

#### Detailed sub-issues

#### S2-F05-I01 — Implement backend application contract for Resolve the family route, support level, and exact Stage 1 profile with G05

  - **Parent feature:** S2-F05
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Resolve the family route, support level, and exact Stage 1 profile with G05 so the feature has one authoritative service path.
  - **Context:** Family acceptance and exact execution resolution are separate. The route and support truth come from the versioned compatibility catalogue, never an LLM.
  - **Scope:** Versioned CompatibilityCatalogue, CompatibilityResolver, registry snapshot adapter, support policy, major-ladder generator, exact Stage 1 resolution, profile selection, checksum lock, and G05 package.
  - **Out of scope:** Angular 11-17 validated paths, Angular 22, executing commands, and LLM-selected versions.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G05 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/feasibility; GET /api/v1/runs/{id}/feasibility; POST /api/v1/runs/{id}/approvals/G05/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: Versioned CompatibilityCatalogue, CompatibilityResolver, registry snapshot adapter, support policy, major-ladder generator, exact Stage 1 resolution, profile selection, checksum lock, and G05 package.
  - **Database impact:** Use or introduce the records summarized by: compatibility catalogue metadata, resolutions, registry snapshot metadata, selected profile, gate/decisions.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/feasibility; GET /api/v1/runs/{id}/feasibility; POST /api/v1/runs/{id}/approvals/G05/decisions
  - **Event impact:** Request durable events only through the transition/event service: COMPATIBILITY_RESOLUTION_STARTED/COMPLETED/BLOCKED and G05 events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Catalogue snapshot reference, route, support-level evidence, registry snapshot checksum, exact Stage 1 resolution, and feasibility package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Registry drift, incompatible exact patch, private-package constraints, unavailable runtime, stale catalogue, and labeling Angular 21 as latest.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G05 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S1-F09, S2-F04
  - **Suggested labels:** sprint-2, s2-f05, approval-capability, backend, g05, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F05-I02 — Persist and expose evidence contracts for Resolve the family route, support level, and exact Stage 1 profile with G05

  - **Parent feature:** S2-F05
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Resolve the family route, support level, and exact Stage 1 profile with G05 observable and auditable.
  - **Context:** Family acceptance and exact execution resolution are separate. The route and support truth come from the versioned compatibility catalogue, never an LLM.
  - **Scope:** Persistence: compatibility catalogue metadata, resolutions, registry snapshot metadata, selected profile, gate/decisions. API: POST /api/v1/runs/{id}/feasibility; GET /api/v1/runs/{id}/feasibility; POST /api/v1/runs/{id}/approvals/G05/decisions. Events: COMPATIBILITY_RESOLUTION_STARTED/COMPLETED/BLOCKED and G05 events. Artifacts: Catalogue snapshot reference, route, support-level evidence, registry snapshot checksum, exact Stage 1 resolution, and feasibility package.
  - **Out of scope:** Angular 11-17 validated paths, Angular 22, executing commands, and LLM-selected versions.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: compatibility catalogue metadata, resolutions, registry snapshot metadata, selected profile, gate/decisions.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/feasibility; GET /api/v1/runs/{id}/feasibility; POST /api/v1/runs/{id}/approvals/G05/decisions; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: COMPATIBILITY_RESOLUTION_STARTED/COMPLETED/BLOCKED and G05 events.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Catalogue snapshot reference, route, support-level evidence, registry snapshot checksum, exact Stage 1 resolution, and feasibility package.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G05 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S2-F05-I01
  - **Suggested labels:** sprint-2, s2-f05, approval-capability, api, g05, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F05-I03 — Build frontend experience for Resolve the family route, support level, and exact Stage 1 profile with G05

  - **Parent feature:** S2-F05
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Resolve the family route, support level, and exact Stage 1 profile with G05, using backend snapshots and durable events only.
  - **Context:** Family acceptance and exact execution resolution are separate. The route and support truth come from the versioned compatibility catalogue, never an LLM.
  - **Scope:** Feasibility view with stage ladder, support badges, exact profile table, candidate runtimes, warnings/blockers, and G05 controls.
  - **Out of scope:** Angular 11-17 validated paths, Angular 22, executing commands, and LLM-selected versions.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/feasibility; GET /api/v1/runs/{id}/feasibility; POST /api/v1/runs/{id}/approvals/G05/decisions` plus durable events `COMPATIBILITY_RESOLUTION_STARTED/COMPLETED/BLOCKED and G05 events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Feasibility view with stage ladder, support badges, exact profile table, candidate runtimes, warnings/blockers, and G05 controls.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/feasibility; GET /api/v1/runs/{id}/feasibility; POST /api/v1/runs/{id}/approvals/G05/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `COMPATIBILITY_RESOLUTION_STARTED/COMPLETED/BLOCKED and G05 events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Catalogue snapshot reference, route, support-level evidence, registry snapshot checksum, exact Stage 1 resolution, and feasibility package.
  - **UI impact:** Implement: Feasibility view with stage ladder, support badges, exact profile table, candidate runtimes, warnings/blockers, and G05 controls.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G05 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S2-F05-I02
  - **Suggested labels:** sprint-2, s2-f05, approval-capability, frontend, g05, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S2-F05-I04 — Verify and document Resolve the family route, support level, and exact Stage 1 profile with G05

  - **Parent feature:** S2-F05
  - **Issue type:** Testing
  - **Technical story:** Prove Resolve the family route, support level, and exact Stage 1 profile with G05 through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Family acceptance and exact execution resolution are separate. The route and support truth come from the versioned compatibility catalogue, never an LLM.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Angular 11-17 validated paths, Angular 22, executing commands, and LLM-selected versions.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/feasibility; GET /api/v1/runs/{id}/feasibility; POST /api/v1/runs/{id}/approvals/G05/decisions` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `COMPATIBILITY_RESOLUTION_STARTED/COMPLETED/BLOCKED and G05 events.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Catalogue snapshot reference, route, support-level evidence, registry snapshot checksum, exact Stage 1 resolution, and feasibility package.` where applicable.
  - **UI impact:** Execute the feature through `Feasibility view with stage ladder, support badges, exact profile table, candidate runtimes, warnings/blockers, and G05 controls.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Registry drift, incompatible exact patch, private-package constraints, unavailable runtime, stale catalogue, and labeling Angular 21 as latest.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G05 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S2-F05-I03
  - **Suggested labels:** sprint-2, s2-f05, approval-capability, testing, g05, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### S2-F06 — Generate and inspect the MigrationPlan and first StageExecutionPlan

#### Feature identity

- **Sprint:** Sprint 2
- **Feature type:** Workflow capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A reviewer can inspect the complete family-level route and an immutable exact Stage 1 execution contract including structured commands, validation, builder decision, recovery, and forbidden changes.

#### Context

Execution needs an approved machine-readable contract distinct from explanatory planning text and actual command evidence.

**Governing specification sections:** 19-20, 26, 52.4, 60, 73.4

#### Scope

Plan generation and viewing; exact Stage 1, family-level later stages finalized later, structured commands, policies, and forbidden modernization.

#### Out of scope

Plan approval, plan modification, real command execution, and optional modernization.

#### Backend slice

- **Application service/components:** MigrationPlanService, StageExecutionPlanService, command-template references, validation/recovery/repair policies, BuildSystemDecision service, plan checksums, and semantic validation.
- **Domain aggregate/projection:** MigrationPlan, StageExecutionPlan, BuildSystemDecision.
- **Persistence:** migration_plans, stage_execution_plans, builder decisions, active-version pointers, artifact references.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/plans; GET /api/v1/runs/{id}/plan; GET /api/v1/runs/{id}/stages/{stageId}/plan`
- **Durable event:** MIGRATION_PLAN_CREATED and STAGE_PLAN_CREATED.
- **Artifact Store output:** Machine-readable plan, stage plan, builder decision, command manifest, validation matrix, recovery map, and forbidden-change policy.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Plan viewer with route timeline, exact Stage 1 tabs, structured argv display, builder decision, validation/recovery sections, and artifact checksums.
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
→ MigrationPlanService, StageExecutionPlanService, command-template references, validation/recovery/repair policies, BuildSystemDecision service, plan checksums, and semantic validation.
→ migration_plans, stage_execution_plans, builder decisions, active-version pointers, artifact references.
→ ArtifactService finalizes evidence: Machine-readable plan, stage plan, builder decision, command manifest, validation matrix, recovery map, and forbidden-change policy.
→ Transition/Event service persists and emits: MIGRATION_PLAN_CREATED and STAGE_PLAN_CREATED.
→ SSE replay or snapshot refresh
→ Plan viewer with route timeline, exact Stage 1 tabs, structured argv display, builder decision, validation/recovery sections, and artifact checksums.
```

#### Sub-issues

- `S2-F06-I01` — Backend/application contract
- `S2-F06-I02` — Persistence, API, durable event, and artifact contract
- `S2-F06-I03` — Frontend projection and interaction
- `S2-F06-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Generate and inspect the MigrationPlan and first StageExecutionPlan**, then the backend performs only the authorized service operation, persists the result, emits the documented **MIGRATION_PLAN_CREATED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **migration_plans, stage_execution_plans, builder decisions, active-version pointers, artifact references.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Machine-readable plan, stage plan, builder decision, command manifest, validation matrix, recovery map, and forbidden-change policy.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S2-F05; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Plan viewer with route timeline, exact Stage 1 tabs, structured argv display, builder decision, validation/recovery sections, and artifact checksums.**.
3. Trigger the primary action for **Generate and inspect the MigrationPlan and first StageExecutionPlan** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can inspect the complete family-level route and an immutable exact Stage 1 execution contract including structured commands, validation, builder decision, recovery, and forbidden changes. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `migration_plans, stage_execution_plans, builder decisions, active-version pointers, artifact references.` are retrievable through `POST /api/v1/runs/{id}/plans; GET /api/v1/runs/{id}/plan; GET /api/v1/runs/{id}/stages/{stageId}/plan` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Machine-readable plan, stage plan, builder decision, command manifest, validation matrix, recovery map, and forbidden-change policy.

**Expected durable event:** MIGRATION_PLAN_CREATED and STAGE_PLAN_CREATED.

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

S2-F05

#### Risks and edge cases

- Plan/command mismatch
- hidden shell string
- incomplete validation
- optional builder change slipping in
- exact-version drift
- and huge plan UI.

#### Detailed sub-issues

#### S2-F06-I01 — Implement backend application contract for Generate and inspect the MigrationPlan and first StageExecutionPlan

  - **Parent feature:** S2-F06
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Generate and inspect the MigrationPlan and first StageExecutionPlan so the feature has one authoritative service path.
  - **Context:** Execution needs an approved machine-readable contract distinct from explanatory planning text and actual command evidence.
  - **Scope:** MigrationPlanService, StageExecutionPlanService, command-template references, validation/recovery/repair policies, BuildSystemDecision service, plan checksums, and semantic validation.
  - **Out of scope:** Plan approval, plan modification, real command execution, and optional modernization.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/plans; GET /api/v1/runs/{id}/plan; GET /api/v1/runs/{id}/stages/{stageId}/plan`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: MigrationPlanService, StageExecutionPlanService, command-template references, validation/recovery/repair policies, BuildSystemDecision service, plan checksums, and semantic validation.
  - **Database impact:** Use or introduce the records summarized by: migration_plans, stage_execution_plans, builder decisions, active-version pointers, artifact references.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/plans; GET /api/v1/runs/{id}/plan; GET /api/v1/runs/{id}/stages/{stageId}/plan
  - **Event impact:** Request durable events only through the transition/event service: MIGRATION_PLAN_CREATED and STAGE_PLAN_CREATED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Machine-readable plan, stage plan, builder decision, command manifest, validation matrix, recovery map, and forbidden-change policy.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Plan/command mismatch, hidden shell string, incomplete validation, optional builder change slipping in, exact-version drift, and huge plan UI.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S2-F05
  - **Suggested labels:** sprint-2, s2-f06, workflow-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F06-I02 — Persist and expose evidence contracts for Generate and inspect the MigrationPlan and first StageExecutionPlan

  - **Parent feature:** S2-F06
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Generate and inspect the MigrationPlan and first StageExecutionPlan observable and auditable.
  - **Context:** Execution needs an approved machine-readable contract distinct from explanatory planning text and actual command evidence.
  - **Scope:** Persistence: migration_plans, stage_execution_plans, builder decisions, active-version pointers, artifact references. API: POST /api/v1/runs/{id}/plans; GET /api/v1/runs/{id}/plan; GET /api/v1/runs/{id}/stages/{stageId}/plan. Events: MIGRATION_PLAN_CREATED and STAGE_PLAN_CREATED. Artifacts: Machine-readable plan, stage plan, builder decision, command manifest, validation matrix, recovery map, and forbidden-change policy.
  - **Out of scope:** Plan approval, plan modification, real command execution, and optional modernization.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: migration_plans, stage_execution_plans, builder decisions, active-version pointers, artifact references.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/plans; GET /api/v1/runs/{id}/plan; GET /api/v1/runs/{id}/stages/{stageId}/plan; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: MIGRATION_PLAN_CREATED and STAGE_PLAN_CREATED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Machine-readable plan, stage plan, builder decision, command manifest, validation matrix, recovery map, and forbidden-change policy.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S2-F06-I01
  - **Suggested labels:** sprint-2, s2-f06, workflow-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F06-I03 — Build frontend experience for Generate and inspect the MigrationPlan and first StageExecutionPlan

  - **Parent feature:** S2-F06
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Generate and inspect the MigrationPlan and first StageExecutionPlan, using backend snapshots and durable events only.
  - **Context:** Execution needs an approved machine-readable contract distinct from explanatory planning text and actual command evidence.
  - **Scope:** Plan viewer with route timeline, exact Stage 1 tabs, structured argv display, builder decision, validation/recovery sections, and artifact checksums.
  - **Out of scope:** Plan approval, plan modification, real command execution, and optional modernization.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/plans; GET /api/v1/runs/{id}/plan; GET /api/v1/runs/{id}/stages/{stageId}/plan` plus durable events `MIGRATION_PLAN_CREATED and STAGE_PLAN_CREATED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Plan viewer with route timeline, exact Stage 1 tabs, structured argv display, builder decision, validation/recovery sections, and artifact checksums.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/plans; GET /api/v1/runs/{id}/plan; GET /api/v1/runs/{id}/stages/{stageId}/plan` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `MIGRATION_PLAN_CREATED and STAGE_PLAN_CREATED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Machine-readable plan, stage plan, builder decision, command manifest, validation matrix, recovery map, and forbidden-change policy.
  - **UI impact:** Implement: Plan viewer with route timeline, exact Stage 1 tabs, structured argv display, builder decision, validation/recovery sections, and artifact checksums.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S2-F06-I02
  - **Suggested labels:** sprint-2, s2-f06, workflow-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S2-F06-I04 — Verify and document Generate and inspect the MigrationPlan and first StageExecutionPlan

  - **Parent feature:** S2-F06
  - **Issue type:** Testing
  - **Technical story:** Prove Generate and inspect the MigrationPlan and first StageExecutionPlan through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Execution needs an approved machine-readable contract distinct from explanatory planning text and actual command evidence.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Plan approval, plan modification, real command execution, and optional modernization.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/plans; GET /api/v1/runs/{id}/plan; GET /api/v1/runs/{id}/stages/{stageId}/plan` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `MIGRATION_PLAN_CREATED and STAGE_PLAN_CREATED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Machine-readable plan, stage plan, builder decision, command manifest, validation matrix, recovery map, and forbidden-change policy.` where applicable.
  - **UI impact:** Execute the feature through `Plan viewer with route timeline, exact Stage 1 tabs, structured argv display, builder decision, validation/recovery sections, and artifact checksums.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Plan/command mismatch, hidden shell string, incomplete validation, optional builder change slipping in, exact-version drift, and huge plan UI.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S2-F06-I03
  - **Suggested labels:** sprint-2, s2-f06, workflow-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### S2-F07 — Review the deterministic plan through a checksum-bound Planning chain and decide G06

#### Feature identity

- **Sprint:** Sprint 2
- **Feature type:** Approval capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G06

#### User-observable outcome

A reviewer can request a bounded plan modification, compare immutable versions, read an AI planning explanation, and approve the current checksum-bound plan through G06.

#### Context

Approved plans never mutate in place; any command/toolchain/policy change invalidates dependent approval and creates a new version.

**Governing specification sections:** 12, 19.3, 52.4, 56.7, 60.4-60.5

#### Scope

Immutable revision, staleness, explanatory agent, G06, and proof that stage start is blocked before approval.

#### Out of scope

Free-form command editing, auto approval, executing Stage 1, and later-stage exact resolution.

#### Backend slice

- **Application service/components:** PlanRevisionService, deterministic diff between versions, staleness propagation, PlanningAgent narrative over approved facts, structured output/usage tracking, G06 gate, and stage-start blocker.
- **Domain aggregate/projection:** MigrationPlanVersion, StageExecutionPlanVersion, LLMInvocation, ApprovalGate G06.
- **Persistence:** New immutable plan versions, active pointer, stale approvals, planning invocation/cost, gate decisions.
- **State/approval rule:** G06 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/plan/revisions; POST /api/v1/runs/{id}/plan/explanation; POST /api/v1/runs/{id}/approvals/G06/decisions`
- **Durable event:** PLAN_REVISION_CREATED, APPROVAL_MARKED_STALE, PLANNING_AGENT_COMPLETED, and G06 events.
- **Artifact Store output:** Plan-version diff, new plan artifacts, Planning Agent explanation, usage/cost record, and G06 evidence package.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Plan review page with version selector, diff, modification form constrained to approved fields, AI explanation separated from executable truth, stale banner, and G06 controls.
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
→ PlanRevisionService, deterministic diff between versions, staleness propagation, PlanningAgent narrative over approved facts, structured output/usage tracking, G06 gate, and stage-start blocker.
→ New immutable plan versions, active pointer, stale approvals, planning invocation/cost, gate decisions.
→ ArtifactService finalizes evidence: Plan-version diff, new plan artifacts, Planning Agent explanation, usage/cost record, and G06 evidence package.
→ Transition/Event service persists and emits: PLAN_REVISION_CREATED, APPROVAL_MARKED_STALE, PLANNING_AGENT_COMPLETED, and G06 events.
→ SSE replay or snapshot refresh
→ Plan review page with version selector, diff, modification form constrained to approved fields, AI explanation separated from executable truth, stale banner, and G06 controls.
```

#### Mandatory Planning phase review chain

The MigrationPlan, StageExecutionPlan, exact versions, commands, runtime profile, builder decision, validation policy, and recovery policy remain deterministic and immutable.

```text
approved deterministic plan and checksums
→ phase Proposer creates a bounded human-readable explanation
→ phase Reviewer validates evidence and checksum references
→ final reviewed planning artifact
→ G06 human decision
```

A modification request invokes `PlanRevisionService`, creates a new immutable plan version, marks dependent approvals stale, and then produces a new explanation/review chain. No LLM may edit the executable plan directly. Approval-sensitive Planning review fails closed after the configured Azure primary and fallback roles are exhausted.

#### Sub-issues

- `S2-F07-I01` — Backend/application contract
- `S2-F07-I02` — Persistence, API, durable event, and artifact contract
- `S2-F07-I03` — Frontend projection and interaction
- `S2-F07-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Revise, explain, and approve the migration plan through G06**, then the backend performs only the authorized service operation, persists the result, emits the documented **PLAN_REVISION_CREATED** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **New immutable plan versions, active pointer, stale approvals, planning invocation/cost, gate decisions.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Plan-version diff, new plan artifacts, Planning Agent explanation, usage/cost record, and G06 evidence package.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G06 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G06 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.

#### Manual end-to-end test scenario

**Preconditions:** S2-F06; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Plan review page with version selector, diff, modification form constrained to approved fields, AI explanation separated from executable truth, stale banner, and G06 controls.**.
    3. Trigger the primary action for **Revise, explain, and approve the migration plan through G06** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G06** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can request a bounded plan modification, compare immutable versions, read an AI planning explanation, and approve the current checksum-bound plan through G06. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `New immutable plan versions, active pointer, stale approvals, planning invocation/cost, gate decisions.` are retrievable through `POST /api/v1/runs/{id}/plan/revisions; POST /api/v1/runs/{id}/plan/explanation; POST /api/v1/runs/{id}/approvals/G06/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Plan-version diff, new plan artifacts, Planning Agent explanation, usage/cost record, and G06 evidence package.

    **Expected durable event:** PLAN_REVISION_CREATED, APPROVAL_MARKED_STALE, PLANNING_AGENT_COMPLETED, and G06 events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G06 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

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

S2-F06

#### Risks and edge cases

- Unbounded modification
- stale plan approval
- AI inventing commands
- hidden exact-version change
- idempotency conflict
- and starting a stage on old plan.

#### Detailed sub-issues

#### S2-F07-I01 — Implement backend application contract for Revise, explain, and approve the migration plan through G06

  - **Parent feature:** S2-F07
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Revise, explain, and approve the migration plan through G06 so the feature has one authoritative service path.
  - **Context:** Approved plans never mutate in place; any command/toolchain/policy change invalidates dependent approval and creates a new version.
  - **Scope:** PlanRevisionService, deterministic diff between versions, staleness propagation, PlanningAgent narrative over approved facts, structured output/usage tracking, G06 gate, and stage-start blocker.
  - **Out of scope:** Free-form command editing, auto approval, executing Stage 1, and later-stage exact resolution.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G06 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/plan/revisions; POST /api/v1/runs/{id}/plan/explanation; POST /api/v1/runs/{id}/approvals/G06/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: PlanRevisionService, deterministic diff between versions, staleness propagation, PlanningAgent narrative over approved facts, structured output/usage tracking, G06 gate, and stage-start blocker.
  - **Database impact:** Use or introduce the records summarized by: New immutable plan versions, active pointer, stale approvals, planning invocation/cost, gate decisions.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/plan/revisions; POST /api/v1/runs/{id}/plan/explanation; POST /api/v1/runs/{id}/approvals/G06/decisions
  - **Event impact:** Request durable events only through the transition/event service: PLAN_REVISION_CREATED, APPROVAL_MARKED_STALE, PLANNING_AGENT_COMPLETED, and G06 events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Plan-version diff, new plan artifacts, Planning Agent explanation, usage/cost record, and G06 evidence package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Unbounded modification, stale plan approval, AI inventing commands, hidden exact-version change, idempotency conflict, and starting a stage on old plan.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G06 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S2-F06
  - **Suggested labels:** sprint-2, s2-f07, approval-capability, backend, g06, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F07-I02 — Persist and expose evidence contracts for Revise, explain, and approve the migration plan through G06

  - **Parent feature:** S2-F07
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Revise, explain, and approve the migration plan through G06 observable and auditable.
  - **Context:** Approved plans never mutate in place; any command/toolchain/policy change invalidates dependent approval and creates a new version.
  - **Scope:** Persistence: New immutable plan versions, active pointer, stale approvals, planning invocation/cost, gate decisions. API: POST /api/v1/runs/{id}/plan/revisions; POST /api/v1/runs/{id}/plan/explanation; POST /api/v1/runs/{id}/approvals/G06/decisions. Events: PLAN_REVISION_CREATED, APPROVAL_MARKED_STALE, PLANNING_AGENT_COMPLETED, and G06 events. Artifacts: Plan-version diff, new plan artifacts, Planning Agent explanation, usage/cost record, and G06 evidence package.
  - **Out of scope:** Free-form command editing, auto approval, executing Stage 1, and later-stage exact resolution.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: New immutable plan versions, active pointer, stale approvals, planning invocation/cost, gate decisions.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/plan/revisions; POST /api/v1/runs/{id}/plan/explanation; POST /api/v1/runs/{id}/approvals/G06/decisions; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: PLAN_REVISION_CREATED, APPROVAL_MARKED_STALE, PLANNING_AGENT_COMPLETED, and G06 events.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Plan-version diff, new plan artifacts, Planning Agent explanation, usage/cost record, and G06 evidence package.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G06 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S2-F07-I01
  - **Suggested labels:** sprint-2, s2-f07, approval-capability, api, g06, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S2-F07-I03 — Build frontend experience for Revise, explain, and approve the migration plan through G06

  - **Parent feature:** S2-F07
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Revise, explain, and approve the migration plan through G06, using backend snapshots and durable events only.
  - **Context:** Approved plans never mutate in place; any command/toolchain/policy change invalidates dependent approval and creates a new version.
  - **Scope:** Plan review page with version selector, diff, modification form constrained to approved fields, AI explanation separated from executable truth, stale banner, and G06 controls.
  - **Out of scope:** Free-form command editing, auto approval, executing Stage 1, and later-stage exact resolution.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/plan/revisions; POST /api/v1/runs/{id}/plan/explanation; POST /api/v1/runs/{id}/approvals/G06/decisions` plus durable events `PLAN_REVISION_CREATED, APPROVAL_MARKED_STALE, PLANNING_AGENT_COMPLETED, and G06 events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Plan review page with version selector, diff, modification form constrained to approved fields, AI explanation separated from executable truth, stale banner, and G06 controls.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/plan/revisions; POST /api/v1/runs/{id}/plan/explanation; POST /api/v1/runs/{id}/approvals/G06/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `PLAN_REVISION_CREATED, APPROVAL_MARKED_STALE, PLANNING_AGENT_COMPLETED, and G06 events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Plan-version diff, new plan artifacts, Planning Agent explanation, usage/cost record, and G06 evidence package.
  - **UI impact:** Implement: Plan review page with version selector, diff, modification form constrained to approved fields, AI explanation separated from executable truth, stale banner, and G06 controls.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G06 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S2-F07-I02
  - **Suggested labels:** sprint-2, s2-f07, approval-capability, frontend, g06, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S2-F07-I04 — Verify and document Revise, explain, and approve the migration plan through G06

  - **Parent feature:** S2-F07
  - **Issue type:** Testing
  - **Technical story:** Prove Revise, explain, and approve the migration plan through G06 through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Approved plans never mutate in place; any command/toolchain/policy change invalidates dependent approval and creates a new version.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Free-form command editing, auto approval, executing Stage 1, and later-stage exact resolution.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/plan/revisions; POST /api/v1/runs/{id}/plan/explanation; POST /api/v1/runs/{id}/approvals/G06/decisions` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `PLAN_REVISION_CREATED, APPROVAL_MARKED_STALE, PLANNING_AGENT_COMPLETED, and G06 events.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Plan-version diff, new plan artifacts, Planning Agent explanation, usage/cost record, and G06 evidence package.` where applicable.
  - **UI impact:** Execute the feature through `Plan review page with version selector, diff, modification form constrained to approved fields, AI explanation separated from executable truth, stale banner, and G06 controls.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Unbounded modification, stale plan approval, AI inventing commands, hidden exact-version change, idempotency conflict, and starting a stage on old plan.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G06 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S2-F07-I03
  - **Suggested labels:** sprint-2, s2-f07, approval-capability, testing, g06, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### D.2.5 Sprint integration tests

- Baseline execution integration with fake/real safe npm profiles and complete evidence.

- Known-failure fingerprint and strict/qualified policy regression tests.

- Parallel discovery determinism and artifact isolation tests.

- LLM schema/semantic validation, prompt injection, secret redaction, retries, and cost tests.

- Compatibility family normalization, exact Stage 1 locking, catalogue checksum, and plan-revision staleness tests.


### D.2.6 Sprint manual demonstration

Create baseline sandbox; inspect environment; run install/build/tests/lint; qualify baseline and approve G03; inspect deterministic findings and AI analysis then approve G04; resolve 18→19→20→21 and exact Stage 1 profile then approve G05; inspect plan, create a revision, view Planning Agent explanation, approve G06; prove G06 blocks stage start.


#### Demonstration checklist

1. Create baseline sandbox.

2. Inspect environment.

3. Run install/build/tests/lint.

4. Qualify baseline and approve G03.

5. Inspect deterministic findings and AI analysis then approve G04.

6. Resolve 18→19→20→21 and exact Stage 1 profile then approve G05.

7. Inspect plan, create a revision, view Planning Agent explanation, approve G06.

8. Prove G06 blocks stage start..


### D.2.7 Sprint exit criteria

- G03–G06 are manually demonstrated and stale-safe.

- Machine facts and AI interpretations are visibly separate.

- Angular 18.x patch variants normalize correctly.

- The route is one major at a time and Angular 21.x is labeled approved target, not latest.

- The first StageExecutionPlan contains only structured command references.

- No Angular update has executed.


### D.2.8 Risks carried into the next sprint

Generalized command/process ownership, stage mutation, full validation, cancellation, and copy-forward are delivered in Sprint 3.


### Sprint 2 integration tests

- Deterministic discovery reproducibility against the approved snapshot and baseline fingerprint.
- Azure gateway tests for missing configuration, role routing, fallback eligibility, Responses parsing, optional Chat Completions capability adapter, `store=false`, token extraction, content filtering, schema/semantic failures, append-only ledger, and estimated-cost calculation.
- Analysis and Planning review-chain tests with fake model clients, checksum mismatch, Reviewer rejection, bounded revision, and fail-closed behavior.
- G04–G06 stale-state, stale-artifact, plan-revision, idempotency, restart, SSE replay, and frontend projection tests.
- Separately gated live Azure tests for readiness, smoke, one structured phase Proposer response, one structured Reviewer response, and provider usage extraction. The normal suite must not require Azure availability.

### Sprint 2 manual demonstration

1. Start from the G03-approved baseline.
2. Inspect deterministic discovery and behavior-sensitive findings.
3. View redacted LLM readiness and execute a small smoke check.
4. Inspect the append-only invocation record, tokens, latency, schema status, fallback status, and estimated cost.
5. Run the Analysis Proposer/Reviewer chain, demonstrate one bounded revision, and approve G04.
6. Resolve Angular 18.x→19.x→20.x→21.x, support level, and exact Stage 1 profile; approve G05.
7. Inspect the deterministic MigrationPlan and StageExecutionPlan.
8. Request a plan modification and prove a new immutable version invalidates the previous explanation and approval.
9. Run the Planning Proposer/Reviewer chain and approve G06.
10. Attempt stage start with stale or missing G06 and confirm it is blocked.

### Sprint 2 exit criteria

- Every AI call uses the production backend gateway and append-only ledger.
- Deterministic facts and plans remain authoritative and unchanged by model output.
- G04 and G06 are backed by checksum-bound Proposer/Reviewer chains and fail closed when mandatory review is unavailable or invalid.
- G05 locks the major route, support level, and exact Stage 1 profile.
- No migration command or workspace transformation occurs.
