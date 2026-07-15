
## Sprint 4 — Failure Evidence, Two-LLM Repair, Recovery, Final Assurance, Delivery, Reporting, and Runtime Proof

**Dependency:** Sprint 3 integrated stage engine and Sprint 2 production Azure gateway  
**Human gates:** G10, G11, G13, G14, G15  
**Feature count:** 15 vertical features / 60 bounded issues

### Sprint goal

Complete the MVP with deterministic failure evidence and routing, checksum-bound Repair Proposer/Reviewer governance, exact persisted patch application, safe recovery, evidence-grounded Assistant help, independent final assurance, atomic delivery, deterministic reporting with optional AI narrative, and a real Angular 18.x→21.x proof.

### Features in implementation order

1. **S4-F01 — Capture FailureEvidence and parse deterministic diagnostics**
2. **S4-F02 — Route failures with C-Lite and show environment or retry actions**
3. **S4-F03 — Build and inspect a bounded sanitized RepairContextPack**
4. **S4-F04 — Generate a checksum-bound Repair Proposer candidate**
5. **S4-F05 — Review the Repair Proposer candidate with a non-authoring Reviewer**
6. **S4-F06 — Persist the reviewed proposal and decide G10 Apply or Reject**
7. **S4-F07 — Validate and apply only the exact persisted repair diff**
8. **S4-F08 — Run patch preflight, resume normal validation, and decide G11**
9. **S4-F09 — Stop no-progress repair loops and reconstruct or roll back safely**
10. **S4-F10 — Reconcile interrupted commands, leases, artifacts, and graph state on startup**
11. **S4-F11 — Explain authoritative migration state through the AI Assistant**
12. **S4-F12 — Run independent final assurance and decide G13**
13. **S4-F13 — Create a delivery candidate and publish atomically through G14**
14. **S4-F14 — Generate the deterministic evidence report, optional AI narrative, and decide G15**
15. **S4-F15 — Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart**

### S4-F01 — Capture FailureEvidence and parse deterministic diagnostics

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Repair capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A reviewer can open a failed command and inspect immutable raw logs, normalized npm/Angular CLI/TypeScript/template/test/generic diagnostics, locations, fingerprints, and baseline origin.

#### Context

Repair may begin only from a real failed command with deterministic evidence, never from a speculative LLM diagnosis.

**Governing specification sections:** 28, 43.2, 64.1-64.3, 70.3

#### Scope

All required MVP parser families, evidence schema, fingerprints, origin, and UI.

#### Out of scope

C-Lite routing action, LLM context, patch proposal, and environment remediation execution.

#### Backend slice

- **Application service/components:** FailureEvidenceBuilder, parser registry, parser adapters, normalized diagnostic schema, failure/origin fingerprints, baseline comparator, and Artifact Store registration before failure transition.
- **Domain aggregate/projection:** Failure, FailureDiagnostic, CommandExecution relation.
- **Persistence:** failures and failure_diagnostics metadata plus artifact references and transition events.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/commands/{commandId}/failure-evidence; GET /api/v1/runs/{id}/failures/{failureId}`
- **Durable event:** FAILURE_CAPTURED and FAILURE_DIAGNOSTICS_PARSED.
- **Artifact Store output:** Raw stdout/stderr references, structured FailureEvidence JSON, parser report, normalized diagnostics, and origin comparison.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** FailureEvidence viewer with raw/normalized tabs, code/file filters, baseline origin, fingerprint, parser confidence, and unknown state.
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
→ FailureEvidenceBuilder, parser registry, parser adapters, normalized diagnostic schema, failure/origin fingerprints, baseline comparator, and Artifact Store registration before failure transition.
→ failures and failure_diagnostics metadata plus artifact references and transition events.
→ ArtifactService finalizes evidence: Raw stdout/stderr references, structured FailureEvidence JSON, parser report, normalized diagnostics, and origin comparison.
→ Transition/Event service persists and emits: FAILURE_CAPTURED and FAILURE_DIAGNOSTICS_PARSED.
→ SSE replay or snapshot refresh
→ FailureEvidence viewer with raw/normalized tabs, code/file filters, baseline origin, fingerprint, parser confidence, and unknown state.
```

#### Sub-issues

- `S4-F01-I01` — Backend/application contract
- `S4-F01-I02` — Persistence, API, durable event, and artifact contract
- `S4-F01-I03` — Frontend projection and interaction
- `S4-F01-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Capture FailureEvidence and parse deterministic diagnostics**, then the backend performs only the authorized service operation, persists the result, emits **FAILURE_CAPTURED**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **failures and failure_diagnostics metadata plus artifact references and transition events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Raw stdout/stderr references, structured FailureEvidence JSON, parser report, normalized diagnostics, and origin comparison.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S3-F02, S3-F12; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **FailureEvidence viewer with raw/normalized tabs, code/file filters, baseline origin, fingerprint, parser confidence, and unknown state.**.
3. Trigger the primary action for **Capture FailureEvidence and parse deterministic diagnostics** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can open a failed command and inspect immutable raw logs, normalized npm/Angular CLI/TypeScript/template/test/generic diagnostics, locations, fingerprints, and baseline origin. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `failures and failure_diagnostics metadata plus artifact references and transition events.` are retrievable through `POST /api/v1/runs/{id}/commands/{commandId}/failure-evidence; GET /api/v1/runs/{id}/failures/{failureId}` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Raw stdout/stderr references, structured FailureEvidence JSON, parser report, normalized diagnostics, and origin comparison.

**Expected durable event:** FAILURE_CAPTURED and FAILURE_DIAGNOSTICS_PARSED.

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

S3-F02, S3-F12

#### Risks and edge cases

- Parser false certainty
- log truncation
- line-number drift
- unstable fingerprints
- secret leakage
- and failure transition before artifacts exist.

#### Detailed sub-issues

#### S4-F01-I01 — Implement backend application contract for Capture FailureEvidence and parse deterministic diagnostics

  - **Parent feature:** S4-F01
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Capture FailureEvidence and parse deterministic diagnostics so the feature has one authoritative service path.
  - **Context:** Repair may begin only from a real failed command with deterministic evidence, never from a speculative LLM diagnosis.
  - **Scope:** FailureEvidenceBuilder, parser registry, parser adapters, normalized diagnostic schema, failure/origin fingerprints, baseline comparator, and Artifact Store registration before failure transition.
  - **Out of scope:** C-Lite routing action, LLM context, patch proposal, and environment remediation execution.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/commands/{commandId}/failure-evidence; GET /api/v1/runs/{id}/failures/{failureId}`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: FailureEvidenceBuilder, parser registry, parser adapters, normalized diagnostic schema, failure/origin fingerprints, baseline comparator, and Artifact Store registration before failure transition.
  - **Database impact:** Use or introduce the records summarized by: failures and failure_diagnostics metadata plus artifact references and transition events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/commands/{commandId}/failure-evidence; GET /api/v1/runs/{id}/failures/{failureId}
  - **Event impact:** Request durable events only through the transition/event service: FAILURE_CAPTURED and FAILURE_DIAGNOSTICS_PARSED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Raw stdout/stderr references, structured FailureEvidence JSON, parser report, normalized diagnostics, and origin comparison.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Parser false certainty, log truncation, line-number drift, unstable fingerprints, secret leakage, and failure transition before artifacts exist.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F02, S3-F12
  - **Suggested labels:** sprint-4, s4-f01, repair-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F01-I02 — Persist and expose evidence contracts for Capture FailureEvidence and parse deterministic diagnostics

  - **Parent feature:** S4-F01
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Capture FailureEvidence and parse deterministic diagnostics observable and auditable.
  - **Context:** Repair may begin only from a real failed command with deterministic evidence, never from a speculative LLM diagnosis.
  - **Scope:** Persistence: failures and failure_diagnostics metadata plus artifact references and transition events.. API: POST /api/v1/runs/{id}/commands/{commandId}/failure-evidence; GET /api/v1/runs/{id}/failures/{failureId}. Events: FAILURE_CAPTURED and FAILURE_DIAGNOSTICS_PARSED.. Artifacts: Raw stdout/stderr references, structured FailureEvidence JSON, parser report, normalized diagnostics, and origin comparison.
  - **Out of scope:** C-Lite routing action, LLM context, patch proposal, and environment remediation execution.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: failures and failure_diagnostics metadata plus artifact references and transition events.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/commands/{commandId}/failure-evidence; GET /api/v1/runs/{id}/failures/{failureId}; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: FAILURE_CAPTURED and FAILURE_DIAGNOSTICS_PARSED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Raw stdout/stderr references, structured FailureEvidence JSON, parser report, normalized diagnostics, and origin comparison.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F01-I01
  - **Suggested labels:** sprint-4, s4-f01, repair-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F01-I03 — Build frontend experience for Capture FailureEvidence and parse deterministic diagnostics

  - **Parent feature:** S4-F01
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Capture FailureEvidence and parse deterministic diagnostics, using backend snapshots and durable events only.
  - **Context:** Repair may begin only from a real failed command with deterministic evidence, never from a speculative LLM diagnosis.
  - **Scope:** FailureEvidence viewer with raw/normalized tabs, code/file filters, baseline origin, fingerprint, parser confidence, and unknown state.
  - **Out of scope:** C-Lite routing action, LLM context, patch proposal, and environment remediation execution.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/commands/{commandId}/failure-evidence; GET /api/v1/runs/{id}/failures/{failureId}` plus durable events `FAILURE_CAPTURED and FAILURE_DIAGNOSTICS_PARSED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: FailureEvidence viewer with raw/normalized tabs, code/file filters, baseline origin, fingerprint, parser confidence, and unknown state.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/commands/{commandId}/failure-evidence; GET /api/v1/runs/{id}/failures/{failureId}` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `FAILURE_CAPTURED and FAILURE_DIAGNOSTICS_PARSED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Raw stdout/stderr references, structured FailureEvidence JSON, parser report, normalized diagnostics, and origin comparison.
  - **UI impact:** Implement: FailureEvidence viewer with raw/normalized tabs, code/file filters, baseline origin, fingerprint, parser confidence, and unknown state.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F01-I02
  - **Suggested labels:** sprint-4, s4-f01, repair-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S4-F01-I04 — Verify and document Capture FailureEvidence and parse deterministic diagnostics

  - **Parent feature:** S4-F01
  - **Issue type:** Testing
  - **Technical story:** Prove Capture FailureEvidence and parse deterministic diagnostics through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Repair may begin only from a real failed command with deterministic evidence, never from a speculative LLM diagnosis.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** C-Lite routing action, LLM context, patch proposal, and environment remediation execution.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/commands/{commandId}/failure-evidence; GET /api/v1/runs/{id}/failures/{failureId}` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `FAILURE_CAPTURED and FAILURE_DIAGNOSTICS_PARSED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Raw stdout/stderr references, structured FailureEvidence JSON, parser report, normalized diagnostics, and origin comparison.` where applicable.
  - **UI impact:** Execute the feature through `FailureEvidence viewer with raw/normalized tabs, code/file filters, baseline origin, fingerprint, parser confidence, and unknown state.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Parser false certainty, log truncation, line-number drift, unstable fingerprints, secret leakage, and failure transition before artifacts exist.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F01-I03
  - **Suggested labels:** sprint-4, s4-f01, repair-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### S4-F02 — Route failures with C-Lite and show environment or retry actions

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Repair capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A user can see whether a failure is code/config, dependency, environment/user action, retryable external, or unknown, with a safe next action and no code patch for environment blockers.

#### Context

Deterministic top-level routing prevents wasted LLM calls and unsafe source changes for proxy, certificate, disk, permission, or runtime failures.

**Governing specification sections:** 28.2-28.5, 32, 64.1, 70.4

#### Scope

Five routes, environment and retry handling, diagnostic hold, and UI.

#### Out of scope

Automated environment repair, LLM repair execution, unlimited retries, and changing source for auth/proxy errors.

#### Backend slice

- **Application service/components:** CLiteRouter, rule/confidence model, environment remediation checklist builder, retry policy, diagnostic-hold transition, semantic-attempt accounting exclusions, and safe rerun authorization.
- **Domain aggregate/projection:** FailureRoute and RepairChain placeholder.
- **Persistence:** Route decision, confidence, policy version, action records, state/events.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry`
- **Durable event:** FAILURE_CLASSIFIED, ENVIRONMENT_ACTION_REQUIRED, EXTERNAL_RETRY_SCHEDULED, DIAGNOSTIC_HOLD_ENTERED.
- **Artifact Store output:** Classification decision, rule evidence, remediation checklist, and retry outcome.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Failure route card with explanation, confidence, approved action buttons, environment checklist, retry progress, and no-patch notice.
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
→ CLiteRouter, rule/confidence model, environment remediation checklist builder, retry policy, diagnostic-hold transition, semantic-attempt accounting exclusions, and safe rerun authorization.
→ Route decision, confidence, policy version, action records, state/events.
→ ArtifactService finalizes evidence: Classification decision, rule evidence, remediation checklist, and retry outcome.
→ Transition/Event service persists and emits: FAILURE_CLASSIFIED, ENVIRONMENT_ACTION_REQUIRED, EXTERNAL_RETRY_SCHEDULED, DIAGNOSTIC_HOLD_ENTERED.
→ SSE replay or snapshot refresh
→ Failure route card with explanation, confidence, approved action buttons, environment checklist, retry progress, and no-patch notice.
```

#### Sub-issues

- `S4-F02-I01` — Backend/application contract
- `S4-F02-I02` — Persistence, API, durable event, and artifact contract
- `S4-F02-I03` — Frontend projection and interaction
- `S4-F02-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Route failures with C-Lite and show environment or retry actions**, then the backend performs only the authorized service operation, persists the result, emits **FAILURE_CLASSIFIED,**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Route decision, confidence, policy version, action records, state/events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Classification decision, rule evidence, remediation checklist, and retry outcome.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S4-F01; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Failure route card with explanation, confidence, approved action buttons, environment checklist, retry progress, and no-patch notice.**.
3. Trigger the primary action for **Route failures with C-Lite and show environment or retry actions** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can see whether a failure is code/config, dependency, environment/user action, retryable external, or unknown, with a safe next action and no code patch for environment blockers. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Route decision, confidence, policy version, action records, state/events.` are retrievable through `POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Classification decision, rule evidence, remediation checklist, and retry outcome.

**Expected durable event:** FAILURE_CLASSIFIED, ENVIRONMENT_ACTION_REQUIRED, EXTERNAL_RETRY_SCHEDULED, DIAGNOSTIC_HOLD_ENTERED.

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

S4-F01

#### Risks and edge cases

- Misrouting dependency issue
- retry storm
- environment secrets
- user action not revalidated
- unknown treated as repairable
- and semantic attempt wrongly consumed.

#### Detailed sub-issues

#### S4-F02-I01 — Implement backend application contract for Route failures with C-Lite and show environment or retry actions

  - **Parent feature:** S4-F02
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Route failures with C-Lite and show environment or retry actions so the feature has one authoritative service path.
  - **Context:** Deterministic top-level routing prevents wasted LLM calls and unsafe source changes for proxy, certificate, disk, permission, or runtime failures.
  - **Scope:** CLiteRouter, rule/confidence model, environment remediation checklist builder, retry policy, diagnostic-hold transition, semantic-attempt accounting exclusions, and safe rerun authorization.
  - **Out of scope:** Automated environment repair, LLM repair execution, unlimited retries, and changing source for auth/proxy errors.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: CLiteRouter, rule/confidence model, environment remediation checklist builder, retry policy, diagnostic-hold transition, semantic-attempt accounting exclusions, and safe rerun authorization.
  - **Database impact:** Use or introduce the records summarized by: Route decision, confidence, policy version, action records, state/events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry
  - **Event impact:** Request durable events only through the transition/event service: FAILURE_CLASSIFIED, ENVIRONMENT_ACTION_REQUIRED, EXTERNAL_RETRY_SCHEDULED, DIAGNOSTIC_HOLD_ENTERED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Classification decision, rule evidence, remediation checklist, and retry outcome.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Misrouting dependency issue, retry storm, environment secrets, user action not revalidated, unknown treated as repairable, and semantic attempt wrongly consumed.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F01
  - **Suggested labels:** sprint-4, s4-f02, repair-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F02-I02 — Persist and expose evidence contracts for Route failures with C-Lite and show environment or retry actions

  - **Parent feature:** S4-F02
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Route failures with C-Lite and show environment or retry actions observable and auditable.
  - **Context:** Deterministic top-level routing prevents wasted LLM calls and unsafe source changes for proxy, certificate, disk, permission, or runtime failures.
  - **Scope:** Persistence: Route decision, confidence, policy version, action records, state/events.. API: POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry. Events: FAILURE_CLASSIFIED, ENVIRONMENT_ACTION_REQUIRED, EXTERNAL_RETRY_SCHEDULED, DIAGNOSTIC_HOLD_ENTERED.. Artifacts: Classification decision, rule evidence, remediation checklist, and retry outcome.
  - **Out of scope:** Automated environment repair, LLM repair execution, unlimited retries, and changing source for auth/proxy errors.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Route decision, confidence, policy version, action records, state/events.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: FAILURE_CLASSIFIED, ENVIRONMENT_ACTION_REQUIRED, EXTERNAL_RETRY_SCHEDULED, DIAGNOSTIC_HOLD_ENTERED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Classification decision, rule evidence, remediation checklist, and retry outcome.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F02-I01
  - **Suggested labels:** sprint-4, s4-f02, repair-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F02-I03 — Build frontend experience for Route failures with C-Lite and show environment or retry actions

  - **Parent feature:** S4-F02
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Route failures with C-Lite and show environment or retry actions, using backend snapshots and durable events only.
  - **Context:** Deterministic top-level routing prevents wasted LLM calls and unsafe source changes for proxy, certificate, disk, permission, or runtime failures.
  - **Scope:** Failure route card with explanation, confidence, approved action buttons, environment checklist, retry progress, and no-patch notice.
  - **Out of scope:** Automated environment repair, LLM repair execution, unlimited retries, and changing source for auth/proxy errors.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry` plus durable events `FAILURE_CLASSIFIED, ENVIRONMENT_ACTION_REQUIRED, EXTERNAL_RETRY_SCHEDULED, DIAGNOSTIC_HOLD_ENTERED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Failure route card with explanation, confidence, approved action buttons, environment checklist, retry progress, and no-patch notice.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `FAILURE_CLASSIFIED, ENVIRONMENT_ACTION_REQUIRED, EXTERNAL_RETRY_SCHEDULED, DIAGNOSTIC_HOLD_ENTERED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Classification decision, rule evidence, remediation checklist, and retry outcome.
  - **UI impact:** Implement: Failure route card with explanation, confidence, approved action buttons, environment checklist, retry progress, and no-patch notice.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F02-I02
  - **Suggested labels:** sprint-4, s4-f02, repair-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S4-F02-I04 — Verify and document Route failures with C-Lite and show environment or retry actions

  - **Parent feature:** S4-F02
  - **Issue type:** Testing
  - **Technical story:** Prove Route failures with C-Lite and show environment or retry actions through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Deterministic top-level routing prevents wasted LLM calls and unsafe source changes for proxy, certificate, disk, permission, or runtime failures.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Automated environment repair, LLM repair execution, unlimited retries, and changing source for auth/proxy errors.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/failures/{failureId}/classify; GET /api/v1/runs/{id}/failures/{failureId}/route; POST /api/v1/runs/{id}/failures/{failureId}/retry` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `FAILURE_CLASSIFIED, ENVIRONMENT_ACTION_REQUIRED, EXTERNAL_RETRY_SCHEDULED, DIAGNOSTIC_HOLD_ENTERED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Classification decision, rule evidence, remediation checklist, and retry outcome.` where applicable.
  - **UI impact:** Execute the feature through `Failure route card with explanation, confidence, approved action buttons, environment checklist, retry progress, and no-patch notice.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Misrouting dependency issue, retry storm, environment secrets, user action not revalidated, unknown treated as repairable, and semantic attempt wrongly consumed.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F02-I03
  - **Suggested labels:** sprint-4, s4-f02, repair-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### S4-F03 — Build and inspect a bounded sanitized RepairContextPack

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Repair capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A reviewer can see exactly which evidence excerpts and files will be model-visible, why each was selected, checksums, redactions, token budget, and forbidden capabilities.

#### Context

Repository content is untrusted data; the model cannot freely browse the workspace or receive secrets.

**Governing specification sections:** 30, 40.5, 64.4, 68.6-68.7

#### Scope

Bounded context v1, sanitization, provenance, one expansion mechanism, and UI.

#### Out of scope

Calling Azure OpenAI, editing context manually, arbitrary file browsing, and patch generation.

#### Backend slice

- **Application service/components:** RepairContextPackBuilder, deterministic selection priority, excerpt/full-file checksum binding, component/template/import relations, prior-attempt inclusion, secret sanitizer, context budget, and one governed expansion hook.
- **Domain aggregate/projection:** RepairAttempt and RepairContextPack metadata.
- **Persistence:** repair_attempts, context-pack metadata, selection reasons, checksums, sanitizer record, artifact refs.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/failures/{failureId}/repair-context; GET /api/v1/runs/{id}/repair-contexts/{contextId}`
- **Durable event:** REPAIR_CONTEXT_CREATED or REPAIR_CONTEXT_BLOCKED.
- **Artifact Store output:** Sanitized context pack, selection manifest, redaction report, token estimate, and forbidden-action policy.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Context inspector with selected files/excerpts, reasons, checksums, redaction indicators, budget meter, and blocked-sensitive-content state.
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
→ RepairContextPackBuilder, deterministic selection priority, excerpt/full-file checksum binding, component/template/import relations, prior-attempt inclusion, secret sanitizer, context budget, and one governed expansion hook.
→ repair_attempts, context-pack metadata, selection reasons, checksums, sanitizer record, artifact refs.
→ ArtifactService finalizes evidence: Sanitized context pack, selection manifest, redaction report, token estimate, and forbidden-action policy.
→ Transition/Event service persists and emits: REPAIR_CONTEXT_CREATED or REPAIR_CONTEXT_BLOCKED.
→ SSE replay or snapshot refresh
→ Context inspector with selected files/excerpts, reasons, checksums, redaction indicators, budget meter, and blocked-sensitive-content state.
```

#### Sub-issues

- `S4-F03-I01` — Backend/application contract
- `S4-F03-I02` — Persistence, API, durable event, and artifact contract
- `S4-F03-I03` — Frontend projection and interaction
- `S4-F03-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Build and inspect a bounded sanitized RepairContextPack**, then the backend performs only the authorized service operation, persists the result, emits **REPAIR_CONTEXT_CREATED**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **repair_attempts, context-pack metadata, selection reasons, checksums, sanitizer record, artifact refs.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Sanitized context pack, selection manifest, redaction report, token estimate, and forbidden-action policy.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Execution authority:** Given any attempt to bypass the registered command template, approved plan, exact profile, workspace alias, or `shell=false` policy, when authorization runs, then execution is rejected before process creation.

#### Manual end-to-end test scenario

**Preconditions:** S4-F01, S4-F02; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Context inspector with selected files/excerpts, reasons, checksums, redaction indicators, budget meter, and blocked-sensitive-content state.**.
3. Trigger the primary action for **Build and inspect a bounded sanitized RepairContextPack** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can see exactly which evidence excerpts and files will be model-visible, why each was selected, checksums, redactions, token budget, and forbidden capabilities. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `repair_attempts, context-pack metadata, selection reasons, checksums, sanitizer record, artifact refs.` are retrievable through `POST /api/v1/runs/{id}/failures/{failureId}/repair-context; GET /api/v1/runs/{id}/repair-contexts/{contextId}` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Sanitized context pack, selection manifest, redaction report, token estimate, and forbidden-action policy.

**Expected durable event:** REPAIR_CONTEXT_CREATED or REPAIR_CONTEXT_BLOCKED.

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

S4-F01, S4-F02

#### Risks and edge cases

- Secret missed by sanitizer
- prompt injection
- excessive context
- stale file checksum
- missing diagnostic relation
- and excerpt misleading without context.

#### Detailed sub-issues

#### S4-F03-I01 — Implement backend application contract for Build and inspect a bounded sanitized RepairContextPack

  - **Parent feature:** S4-F03
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Build and inspect a bounded sanitized RepairContextPack so the feature has one authoritative service path.
  - **Context:** Repository content is untrusted data; the model cannot freely browse the workspace or receive secrets.
  - **Scope:** RepairContextPackBuilder, deterministic selection priority, excerpt/full-file checksum binding, component/template/import relations, prior-attempt inclusion, secret sanitizer, context budget, and one governed expansion hook.
  - **Out of scope:** Calling Azure OpenAI, editing context manually, arbitrary file browsing, and patch generation.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/failures/{failureId}/repair-context; GET /api/v1/runs/{id}/repair-contexts/{contextId}`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: RepairContextPackBuilder, deterministic selection priority, excerpt/full-file checksum binding, component/template/import relations, prior-attempt inclusion, secret sanitizer, context budget, and one governed expansion hook.
  - **Database impact:** Use or introduce the records summarized by: repair_attempts, context-pack metadata, selection reasons, checksums, sanitizer record, artifact refs.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/failures/{failureId}/repair-context; GET /api/v1/runs/{id}/repair-contexts/{contextId}
  - **Event impact:** Request durable events only through the transition/event service: REPAIR_CONTEXT_CREATED or REPAIR_CONTEXT_BLOCKED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Sanitized context pack, selection manifest, redaction report, token estimate, and forbidden-action policy.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Secret missed by sanitizer, prompt injection, excessive context, stale file checksum, missing diagnostic relation, and excerpt misleading without context.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F01, S4-F02
  - **Suggested labels:** sprint-4, s4-f03, repair-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F03-I02 — Persist and expose evidence contracts for Build and inspect a bounded sanitized RepairContextPack

  - **Parent feature:** S4-F03
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Build and inspect a bounded sanitized RepairContextPack observable and auditable.
  - **Context:** Repository content is untrusted data; the model cannot freely browse the workspace or receive secrets.
  - **Scope:** Persistence: repair_attempts, context-pack metadata, selection reasons, checksums, sanitizer record, artifact refs.. API: POST /api/v1/runs/{id}/failures/{failureId}/repair-context; GET /api/v1/runs/{id}/repair-contexts/{contextId}. Events: REPAIR_CONTEXT_CREATED or REPAIR_CONTEXT_BLOCKED.. Artifacts: Sanitized context pack, selection manifest, redaction report, token estimate, and forbidden-action policy.
  - **Out of scope:** Calling Azure OpenAI, editing context manually, arbitrary file browsing, and patch generation.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: repair_attempts, context-pack metadata, selection reasons, checksums, sanitizer record, artifact refs.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/failures/{failureId}/repair-context; GET /api/v1/runs/{id}/repair-contexts/{contextId}; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: REPAIR_CONTEXT_CREATED or REPAIR_CONTEXT_BLOCKED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Sanitized context pack, selection manifest, redaction report, token estimate, and forbidden-action policy.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F03-I01
  - **Suggested labels:** sprint-4, s4-f03, repair-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F03-I03 — Build frontend experience for Build and inspect a bounded sanitized RepairContextPack

  - **Parent feature:** S4-F03
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Build and inspect a bounded sanitized RepairContextPack, using backend snapshots and durable events only.
  - **Context:** Repository content is untrusted data; the model cannot freely browse the workspace or receive secrets.
  - **Scope:** Context inspector with selected files/excerpts, reasons, checksums, redaction indicators, budget meter, and blocked-sensitive-content state.
  - **Out of scope:** Calling Azure OpenAI, editing context manually, arbitrary file browsing, and patch generation.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/failures/{failureId}/repair-context; GET /api/v1/runs/{id}/repair-contexts/{contextId}` plus durable events `REPAIR_CONTEXT_CREATED or REPAIR_CONTEXT_BLOCKED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Context inspector with selected files/excerpts, reasons, checksums, redaction indicators, budget meter, and blocked-sensitive-content state.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/failures/{failureId}/repair-context; GET /api/v1/runs/{id}/repair-contexts/{contextId}` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `REPAIR_CONTEXT_CREATED or REPAIR_CONTEXT_BLOCKED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Sanitized context pack, selection manifest, redaction report, token estimate, and forbidden-action policy.
  - **UI impact:** Implement: Context inspector with selected files/excerpts, reasons, checksums, redaction indicators, budget meter, and blocked-sensitive-content state.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F03-I02
  - **Suggested labels:** sprint-4, s4-f03, repair-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F03-I04 — Verify and document Build and inspect a bounded sanitized RepairContextPack

  - **Parent feature:** S4-F03
  - **Issue type:** Testing
  - **Technical story:** Prove Build and inspect a bounded sanitized RepairContextPack through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Repository content is untrusted data; the model cannot freely browse the workspace or receive secrets.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Calling Azure OpenAI, editing context manually, arbitrary file browsing, and patch generation.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/failures/{failureId}/repair-context; GET /api/v1/runs/{id}/repair-contexts/{contextId}` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `REPAIR_CONTEXT_CREATED or REPAIR_CONTEXT_BLOCKED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Sanitized context pack, selection manifest, redaction report, token estimate, and forbidden-action policy.` where applicable.
  - **UI impact:** Execute the feature through `Context inspector with selected files/excerpts, reasons, checksums, redaction indicators, budget meter, and blocked-sensitive-content state.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Secret missed by sanitizer, prompt injection, excessive context, stale file checksum, missing diagnostic relation, and excerpt misleading without context.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F03-I03
  - **Suggested labels:** sprint-4, s4-f03, repair-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---


### S4-F04 — Generate a checksum-bound Repair Proposer candidate

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Repair capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A reviewer can invoke the Proposer on one eligible FailureEvidence/ContextPack and inspect its evidence-backed diagnosis, minimal strategy, exact unified diff, changed files, risks, and usage.

#### Context

Only the Proposer LLM may author a repair diff; output remains an untrusted proposal until deterministic validation and Reviewer acceptance.

**Governing specification sections:** 29.1, 29.4, 64.5, 64.7

#### Scope

Proposer role, one candidate diff, structured/semantic validation, bounded failure behavior, and UI.

#### Out of scope

Reviewer decision, human Apply, patch application, command execution, and direct filesystem writes.

#### Backend slice

- **Application service/components:** ProposerService using gateway role/prompt/schema, deterministic input references, candidate/insufficient/not-repairable statuses, diff parse, changed-file consistency, forbidden-action checks, lineage binding, and retry limits.
- **Domain aggregate/projection:** RepairAttempt, LLMInvocation, ProposerCandidate.
- **Persistence:** Proposer invocation/result metadata, status, context lineage, usage/cost, artifact refs.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer`
- **Durable event:** PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED.
- **Artifact Store output:** Structured Proposer response, exact proposed diff, semantic validation report, changed-file inventory, usage/cost.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Proposer viewer with diagnosis, evidence refs, strategy, read-only diff, risk notes, validation errors, model provenance, and usage.
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
→ ProposerService using gateway role/prompt/schema, deterministic input references, candidate/insufficient/not-repairable statuses, diff parse, changed-file consistency, forbidden-action checks, lineage binding, and retry limits.
→ Proposer invocation/result metadata, status, context lineage, usage/cost, artifact refs.
→ ArtifactService finalizes evidence: Structured Proposer response, exact proposed diff, semantic validation report, changed-file inventory, usage/cost.
→ Transition/Event service persists and emits: PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED.
→ SSE replay or snapshot refresh
→ Proposer viewer with diagnosis, evidence refs, strategy, read-only diff, risk notes, validation errors, model provenance, and usage.
```

#### Required repair Proposer lineage

The Proposer call uses the Sprint 2 gateway and persists this lineage before its output can be reviewed:

```text
base workspace fingerprint
→ FailureEvidence checksum
→ RepairContextPack checksum
→ deterministic repair artifact checksum
→ repair Proposer invocation ID
→ Proposer output checksum
→ proposed diff checksum
```

The output contains root cause, fix strategy, evidence references, changed files, one unified diff, risk, confidence, validation impact, and optional bounded context request. No deterministic fallback may author a repair diff. Only an explicitly configured Azure fallback deployment is eligible.

#### Sub-issues

- `S4-F04-I01` — Backend/application contract
- `S4-F04-I02` — Persistence, API, durable event, and artifact contract
- `S4-F04-I03` — Frontend projection and interaction
- `S4-F04-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Generate and review a Proposer repair candidate**, then the backend performs only the authorized service operation, persists the result, emits **PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED.**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Proposer invocation/result metadata, status, context lineage, usage/cost, artifact refs.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Structured Proposer response, exact proposed diff, semantic validation report, changed-file inventory, usage/cost.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S4-F03, S2-F03; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Proposer viewer with diagnosis, evidence refs, strategy, read-only diff, risk notes, validation errors, model provenance, and usage.**.
3. Trigger the primary action for **Generate and review a Proposer repair candidate** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can invoke the Proposer on one eligible FailureEvidence/ContextPack and inspect its evidence-backed diagnosis, minimal strategy, exact unified diff, changed files, risks, and usage. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Proposer invocation/result metadata, status, context lineage, usage/cost, artifact refs.` are retrievable through `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Structured Proposer response, exact proposed diff, semantic validation report, changed-file inventory, usage/cost.

**Expected durable event:** PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED.

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

S4-F03, S2-F03

#### Risks and edge cases

- Hallucinated API/package
- invalid diff
- scope expansion
- test weakening
- hidden modernization
- stale context
- and model claiming approval.

#### Detailed sub-issues

#### S4-F04-I01 — Implement backend application contract for Generate and review a Proposer repair candidate

  - **Parent feature:** S4-F04
  - **Issue type:** Agent
  - **Technical story:** Implement the bounded backend/application behavior for Generate and review a Proposer repair candidate so the feature has one authoritative service path.
  - **Context:** Only the Proposer LLM may author a repair diff; output remains an untrusted proposal until deterministic validation and Reviewer acceptance.
  - **Scope:** ProposerService using gateway role/prompt/schema, deterministic input references, candidate/insufficient/not-repairable statuses, diff parse, changed-file consistency, forbidden-action checks, lineage binding, and retry limits.
  - **Out of scope:** Reviewer decision, human Apply, patch application, command execution, and direct filesystem writes.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: ProposerService using gateway role/prompt/schema, deterministic input references, candidate/insufficient/not-repairable statuses, diff parse, changed-file consistency, forbidden-action checks, lineage binding, and retry limits.
  - **Database impact:** Use or introduce the records summarized by: Proposer invocation/result metadata, status, context lineage, usage/cost, artifact refs.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer
  - **Event impact:** Request durable events only through the transition/event service: PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Structured Proposer response, exact proposed diff, semantic validation report, changed-file inventory, usage/cost.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Hallucinated API/package, invalid diff, scope expansion, test weakening, hidden modernization, stale context, and model claiming approval.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's agent behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F03, S2-F03
  - **Suggested labels:** sprint-4, s4-f04, repair-capability, agent, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F04-I02 — Persist and expose evidence contracts for Generate and review a Proposer repair candidate

  - **Parent feature:** S4-F04
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Generate and review a Proposer repair candidate observable and auditable.
  - **Context:** Only the Proposer LLM may author a repair diff; output remains an untrusted proposal until deterministic validation and Reviewer acceptance.
  - **Scope:** Persistence: Proposer invocation/result metadata, status, context lineage, usage/cost, artifact refs.. API: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer. Events: PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED.. Artifacts: Structured Proposer response, exact proposed diff, semantic validation report, changed-file inventory, usage/cost.
  - **Out of scope:** Reviewer decision, human Apply, patch application, command execution, and direct filesystem writes.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Proposer invocation/result metadata, status, context lineage, usage/cost, artifact refs.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Structured Proposer response, exact proposed diff, semantic validation report, changed-file inventory, usage/cost.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F04-I01
  - **Suggested labels:** sprint-4, s4-f04, repair-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F04-I03 — Build frontend experience for Generate and review a Proposer repair candidate

  - **Parent feature:** S4-F04
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Generate and review a Proposer repair candidate, using backend snapshots and durable events only.
  - **Context:** Only the Proposer LLM may author a repair diff; output remains an untrusted proposal until deterministic validation and Reviewer acceptance.
  - **Scope:** Proposer viewer with diagnosis, evidence refs, strategy, read-only diff, risk notes, validation errors, model provenance, and usage.
  - **Out of scope:** Reviewer decision, human Apply, patch application, command execution, and direct filesystem writes.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer` plus durable events `PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Proposer viewer with diagnosis, evidence refs, strategy, read-only diff, risk notes, validation errors, model provenance, and usage.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Structured Proposer response, exact proposed diff, semantic validation report, changed-file inventory, usage/cost.
  - **UI impact:** Implement: Proposer viewer with diagnosis, evidence refs, strategy, read-only diff, risk notes, validation errors, model provenance, and usage.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F04-I02
  - **Suggested labels:** sprint-4, s4-f04, repair-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F04-I04 — Verify and document Generate and review a Proposer repair candidate

  - **Parent feature:** S4-F04
  - **Issue type:** Testing
  - **Technical story:** Prove Generate and review a Proposer repair candidate through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Only the Proposer LLM may author a repair diff; output remains an untrusted proposal until deterministic validation and Reviewer acceptance.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Reviewer decision, human Apply, patch application, command execution, and direct filesystem writes.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/proposer` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Structured Proposer response, exact proposed diff, semantic validation report, changed-file inventory, usage/cost.` where applicable.
  - **UI impact:** Execute the feature through `Proposer viewer with diagnosis, evidence refs, strategy, read-only diff, risk notes, validation errors, model provenance, and usage.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Hallucinated API/package, invalid diff, scope expansion, test weakening, hidden modernization, stale context, and model claiming approval.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F04-I03
  - **Suggested labels:** sprint-4, s4-f04, repair-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---


### S4-F05 — Review the Repair Proposer candidate with a non-authoring Reviewer

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Repair capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A reviewer can see an independent Reviewer accept, request revision, reject, or request context; one demonstrated revision returns to the Proposer, and any Reviewer diff field is rejected.

#### Context

Critique is separated from authorship to preserve lineage and prevent a hidden replacement patch.

**Governing specification sections:** 29.1, 29.5, 64.6-64.8

#### Scope

Reviewer role, prohibited diff schema, max revision/context cycles, revised Proposer lineage, and UI.

#### Out of scope

Human approval, patch application, unlimited review loops, and reviewer-edited patch.

#### Backend slice

- **Application service/components:** ReviewerService with schema explicitly excluding diff, evidence/minimality/parity/security checks, semantic validation, bounded revision/context expansion counters, and Proposer revision lineage.
- **Domain aggregate/projection:** ReviewDecision and RepairAttempt counters.
- **Persistence:** review_decisions, revision/context counters, LLM invocations/usage, artifact refs.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions`
- **Durable event:** REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED.
- **Artifact Store output:** Reviewer structured response, critique/revision instructions, schema-validation evidence, revised Proposer candidate where applicable.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Side-by-side Proposer/Reviewer view, decision badge, critique, revision timeline, context-expansion status, and explicit 'Reviewer never authors a diff' notice.
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
→ ReviewerService with schema explicitly excluding diff, evidence/minimality/parity/security checks, semantic validation, bounded revision/context expansion counters, and Proposer revision lineage.
→ review_decisions, revision/context counters, LLM invocations/usage, artifact refs.
→ ArtifactService finalizes evidence: Reviewer structured response, critique/revision instructions, schema-validation evidence, revised Proposer candidate where applicable.
→ Transition/Event service persists and emits: REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED.
→ SSE replay or snapshot refresh
→ Side-by-side Proposer/Reviewer view, decision badge, critique, revision timeline, context-expansion status, and explicit 'Reviewer never authors a diff' notice.
```

#### Required non-authoring Reviewer contract

The Reviewer receives and explicitly references the FailureEvidence checksum, RepairContextPack checksum, deterministic repair artifact checksum, Proposer output checksum, and diff checksum. Its schema contains no patch or diff field.

Allowed decisions are `accept`, `request_revision`, `reject`, and `insufficient_context`. Any diff-like output, missing checksum, stale evidence, or unsupported claim is rejected. A deterministic text fallback cannot produce an accepted repair review.

#### Sub-issues

- `S4-F05-I01` — Backend/application contract
- `S4-F05-I02` — Persistence, API, durable event, and artifact contract
- `S4-F05-I03` — Frontend projection and interaction
- `S4-F05-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Review a Proposer candidate with non-authoring Reviewer and bounded revision**, then the backend performs only the authorized service operation, persists the result, emits **REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **review_decisions, revision/context counters, LLM invocations/usage, artifact refs.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Reviewer structured response, critique/revision instructions, schema-validation evidence, revised Proposer candidate where applicable.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S4-F04; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Side-by-side Proposer/Reviewer view, decision badge, critique, revision timeline, context-expansion status, and explicit 'Reviewer never authors a diff' notice.**.
3. Trigger the primary action for **Review a Proposer candidate with non-authoring Reviewer and bounded revision** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can see an independent Reviewer accept, request revision, reject, or request context; one demonstrated revision returns to the Proposer, and any Reviewer diff field is rejected. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `review_decisions, revision/context counters, LLM invocations/usage, artifact refs.` are retrievable through `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Reviewer structured response, critique/revision instructions, schema-validation evidence, revised Proposer candidate where applicable.

**Expected durable event:** REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED.

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

S4-F04

#### Risks and edge cases

- Reviewer smuggling patch in text
- circular revisions
- inconsistent evidence refs
- independent-role configuration error
- and context expansion exposing secrets.

#### Detailed sub-issues

#### S4-F05-I01 — Implement backend application contract for Review a Proposer candidate with non-authoring Reviewer and bounded revision

  - **Parent feature:** S4-F05
  - **Issue type:** Agent
  - **Technical story:** Implement the bounded backend/application behavior for Review a Proposer candidate with non-authoring Reviewer and bounded revision so the feature has one authoritative service path.
  - **Context:** Critique is separated from authorship to preserve lineage and prevent a hidden replacement patch.
  - **Scope:** ReviewerService with schema explicitly excluding diff, evidence/minimality/parity/security checks, semantic validation, bounded revision/context expansion counters, and Proposer revision lineage.
  - **Out of scope:** Human approval, patch application, unlimited review loops, and reviewer-edited patch.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: ReviewerService with schema explicitly excluding diff, evidence/minimality/parity/security checks, semantic validation, bounded revision/context expansion counters, and Proposer revision lineage.
  - **Database impact:** Use or introduce the records summarized by: review_decisions, revision/context counters, LLM invocations/usage, artifact refs.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions
  - **Event impact:** Request durable events only through the transition/event service: REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Reviewer structured response, critique/revision instructions, schema-validation evidence, revised Proposer candidate where applicable.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Reviewer smuggling patch in text, circular revisions, inconsistent evidence refs, independent-role configuration error, and context expansion exposing secrets.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's agent behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F04
  - **Suggested labels:** sprint-4, s4-f05, repair-capability, agent, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F05-I02 — Persist and expose evidence contracts for Review a Proposer candidate with non-authoring Reviewer and bounded revision

  - **Parent feature:** S4-F05
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Review a Proposer candidate with non-authoring Reviewer and bounded revision observable and auditable.
  - **Context:** Critique is separated from authorship to preserve lineage and prevent a hidden replacement patch.
  - **Scope:** Persistence: review_decisions, revision/context counters, LLM invocations/usage, artifact refs.. API: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions. Events: REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED.. Artifacts: Reviewer structured response, critique/revision instructions, schema-validation evidence, revised Proposer candidate where applicable.
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

#### S4-F05-I03 — Build frontend experience for Review a Proposer candidate with non-authoring Reviewer and bounded revision

  - **Parent feature:** S4-F05
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Review a Proposer candidate with non-authoring Reviewer and bounded revision, using backend snapshots and durable events only.
  - **Context:** Critique is separated from authorship to preserve lineage and prevent a hidden replacement patch.
  - **Scope:** Side-by-side Proposer/Reviewer view, decision badge, critique, revision timeline, context-expansion status, and explicit 'Reviewer never authors a diff' notice.
  - **Out of scope:** Human approval, patch application, unlimited review loops, and reviewer-edited patch.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions` plus durable events `REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Side-by-side Proposer/Reviewer view, decision badge, critique, revision timeline, context-expansion status, and explicit 'Reviewer never authors a diff' notice.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Reviewer structured response, critique/revision instructions, schema-validation evidence, revised Proposer candidate where applicable.
  - **UI impact:** Implement: Side-by-side Proposer/Reviewer view, decision badge, critique, revision timeline, context-expansion status, and explicit 'Reviewer never authors a diff' notice.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F05-I02
  - **Suggested labels:** sprint-4, s4-f05, repair-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S4-F05-I04 — Verify and document Review a Proposer candidate with non-authoring Reviewer and bounded revision

  - **Parent feature:** S4-F05
  - **Issue type:** Testing
  - **Technical story:** Prove Review a Proposer candidate with non-authoring Reviewer and bounded revision through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Critique is separated from authorship to preserve lineage and prevent a hidden replacement patch.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Human approval, patch application, unlimited review loops, and reviewer-edited patch.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/reviewer; POST /api/v1/runs/{id}/repair-attempts/{attemptId}/revisions` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT and PROPOSER_REVISION_COMPLETED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Reviewer structured response, critique/revision instructions, schema-validation evidence, revised Proposer candidate where applicable.` where applicable.
  - **UI impact:** Execute the feature through `Side-by-side Proposer/Reviewer view, decision badge, critique, revision timeline, context-expansion status, and explicit 'Reviewer never authors a diff' notice.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Reviewer smuggling patch in text, circular revisions, inconsistent evidence refs, independent-role configuration error, and context expansion exposing secrets.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F05-I03
  - **Suggested labels:** sprint-4, s4-f05, repair-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### S4-F06 — Persist the reviewed proposal and decide G10 Apply or Reject

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Approval capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G10

#### User-observable outcome

A human can inspect the exact accepted Proposer diff and Reviewer decision, then Apply or Reject G10; the decision is bound to proposal checksum, state, plan, and workspace fingerprint.

#### Context

LLM acceptance is advisory. Human authorization is mandatory before any repair mutation.

**Governing specification sections:** 12.5, 29.2, 31.1-31.2, 56.12, 64.9

#### Scope

Accepted-proposal persistence, exact read-only evidence, G10, and no raw diff in UI request.

#### Out of scope

Patch dry run/application, modifying proposal in UI, auto-apply, and repair validation.

#### Backend slice

- **Application service/components:** RepairProposalService, exact diff persistence/checksum, pre-apply fingerprint, model/prompt/schema provenance, risk package, G10 gate, stale condition evaluation, and decision consequences.
- **Domain aggregate/projection:** RepairProposal, ApprovalGate G10, UserDecision.
- **Persistence:** repair_proposals, proposal status/checksum, gate binding, decisions, lineage and events.
- **State/approval rule:** G10 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions`
- **Durable event:** REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.
- **Artifact Store output:** Exact immutable accepted diff, proposal manifest, Reviewer decision, lineage/provenance, risk report, and G10 package.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Repair approval page with read-only diff, failure/context/proposer/reviewer timeline, checksum/fingerprint, risk warnings, Apply/Reject controls, and stale-state message.
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
→ RepairProposalService, exact diff persistence/checksum, pre-apply fingerprint, model/prompt/schema provenance, risk package, G10 gate, stale condition evaluation, and decision consequences.
→ repair_proposals, proposal status/checksum, gate binding, decisions, lineage and events.
→ ArtifactService finalizes evidence: Exact immutable accepted diff, proposal manifest, Reviewer decision, lineage/provenance, risk report, and G10 package.
→ Transition/Event service persists and emits: REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.
→ SSE replay or snapshot refresh
→ Repair approval page with read-only diff, failure/context/proposer/reviewer timeline, checksum/fingerprint, risk warnings, Apply/Reject controls, and stale-state message.
```

#### G10 evidence binding

The G10 package binds the exact base workspace fingerprint, failure, context, deterministic repair artifact, Proposer invocation/output, diff, Reviewer invocation/output, deterministic policy-validation report, state version, plan version, and artifact-set checksum. The frontend submits identifiers and checksums only; it never resends or edits the authoritative diff.

#### Sub-issues

- `S4-F06-I01` — Backend/application contract
- `S4-F06-I02` — Persistence, API, durable event, and artifact contract
- `S4-F06-I03` — Frontend projection and interaction
- `S4-F06-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Persist an accepted proposal and decide G10 Apply or Reject**, then the backend performs only the authorized service operation, persists the result, emits **REPAIR_PROPOSAL_READY**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **repair_proposals, proposal status/checksum, gate binding, decisions, lineage and events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Exact immutable accepted diff, proposal manifest, Reviewer decision, lineage/provenance, risk report, and G10 package.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G10 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G10 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.

#### Manual end-to-end test scenario

**Preconditions:** S4-F05; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Repair approval page with read-only diff, failure/context/proposer/reviewer timeline, checksum/fingerprint, risk warnings, Apply/Reject controls, and stale-state message.**.
    3. Trigger the primary action for **Persist an accepted proposal and decide G10 Apply or Reject** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G10** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A human can inspect the exact accepted Proposer diff and Reviewer decision, then Apply or Reject G10; the decision is bound to proposal checksum, state, plan, and workspace fingerprint. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `repair_proposals, proposal status/checksum, gate binding, decisions, lineage and events.` are retrievable through `GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Exact immutable accepted diff, proposal manifest, Reviewer decision, lineage/provenance, risk report, and G10 package.

    **Expected durable event:** REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G10 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

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

S4-F05

#### Risks and edge cases

- Stale workspace
- UI resubmitting altered diff
- checksum mismatch
- wrong attempt lineage
- high-risk file approval
- and double Apply.

#### Detailed sub-issues

#### S4-F06-I01 — Implement backend application contract for Persist an accepted proposal and decide G10 Apply or Reject

  - **Parent feature:** S4-F06
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Persist an accepted proposal and decide G10 Apply or Reject so the feature has one authoritative service path.
  - **Context:** LLM acceptance is advisory. Human authorization is mandatory before any repair mutation.
  - **Scope:** RepairProposalService, exact diff persistence/checksum, pre-apply fingerprint, model/prompt/schema provenance, risk package, G10 gate, stale condition evaluation, and decision consequences.
  - **Out of scope:** Patch dry run/application, modifying proposal in UI, auto-apply, and repair validation.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G10 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: RepairProposalService, exact diff persistence/checksum, pre-apply fingerprint, model/prompt/schema provenance, risk package, G10 gate, stale condition evaluation, and decision consequences.
  - **Database impact:** Use or introduce the records summarized by: repair_proposals, proposal status/checksum, gate binding, decisions, lineage and events.
  - **API impact:** Define service-facing request/response models supporting: GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions
  - **Event impact:** Request durable events only through the transition/event service: REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Exact immutable accepted diff, proposal manifest, Reviewer decision, lineage/provenance, risk report, and G10 package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Stale workspace, UI resubmitting altered diff, checksum mismatch, wrong attempt lineage, high-risk file approval, and double Apply.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G10 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F05
  - **Suggested labels:** sprint-4, s4-f06, approval-capability, backend, g10, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F06-I02 — Persist and expose evidence contracts for Persist an accepted proposal and decide G10 Apply or Reject

  - **Parent feature:** S4-F06
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Persist an accepted proposal and decide G10 Apply or Reject observable and auditable.
  - **Context:** LLM acceptance is advisory. Human authorization is mandatory before any repair mutation.
  - **Scope:** Persistence: repair_proposals, proposal status/checksum, gate binding, decisions, lineage and events.. API: GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions. Events: REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.. Artifacts: Exact immutable accepted diff, proposal manifest, Reviewer decision, lineage/provenance, risk report, and G10 package.
  - **Out of scope:** Patch dry run/application, modifying proposal in UI, auto-apply, and repair validation.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: repair_proposals, proposal status/checksum, gate binding, decisions, lineage and events.
  - **API impact:** Implement and document: GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Exact immutable accepted diff, proposal manifest, Reviewer decision, lineage/provenance, risk report, and G10 package.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G10 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F06-I01
  - **Suggested labels:** sprint-4, s4-f06, approval-capability, api, g10, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F06-I03 — Build frontend experience for Persist an accepted proposal and decide G10 Apply or Reject

  - **Parent feature:** S4-F06
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Persist an accepted proposal and decide G10 Apply or Reject, using backend snapshots and durable events only.
  - **Context:** LLM acceptance is advisory. Human authorization is mandatory before any repair mutation.
  - **Scope:** Repair approval page with read-only diff, failure/context/proposer/reviewer timeline, checksum/fingerprint, risk warnings, Apply/Reject controls, and stale-state message.
  - **Out of scope:** Patch dry run/application, modifying proposal in UI, auto-apply, and repair validation.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions` plus durable events `REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Repair approval page with read-only diff, failure/context/proposer/reviewer timeline, checksum/fingerprint, risk warnings, Apply/Reject controls, and stale-state message.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Exact immutable accepted diff, proposal manifest, Reviewer decision, lineage/provenance, risk report, and G10 package.
  - **UI impact:** Implement: Repair approval page with read-only diff, failure/context/proposer/reviewer timeline, checksum/fingerprint, risk warnings, Apply/Reject controls, and stale-state message.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G10 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F06-I02
  - **Suggested labels:** sprint-4, s4-f06, approval-capability, frontend, g10, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S4-F06-I04 — Verify and document Persist an accepted proposal and decide G10 Apply or Reject

  - **Parent feature:** S4-F06
  - **Issue type:** Testing
  - **Technical story:** Prove Persist an accepted proposal and decide G10 Apply or Reject through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** LLM acceptance is advisory. Human authorization is mandatory before any repair mutation.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Patch dry run/application, modifying proposal in UI, auto-apply, and repair validation.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `GET /api/v1/runs/{id}/repair-proposals/{proposalId}; POST /api/v1/runs/{id}/approvals/G10/decisions` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `REPAIR_PROPOSAL_READY and G10 approval/rejection/stale events.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Exact immutable accepted diff, proposal manifest, Reviewer decision, lineage/provenance, risk report, and G10 package.` where applicable.
  - **UI impact:** Execute the feature through `Repair approval page with read-only diff, failure/context/proposer/reviewer timeline, checksum/fingerprint, risk warnings, Apply/Reject controls, and stale-state message.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Stale workspace, UI resubmitting altered diff, checksum mismatch, wrong attempt lineage, high-risk file approval, and double Apply.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G10 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F06-I03
  - **Suggested labels:** sprint-4, s4-f06, approval-capability, testing, g10, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### S4-F07 — Validate and apply only the exact persisted repair diff

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Repair capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

After G10 Apply, a user can see checksum/fingerprint/path/scope/applicability checks and either an exact successful patch application with ledger or a fail-closed rejection.

#### Context

PatchApplyService, not the UI or LLM, owns controlled mutation and must reject stale, escaping, or inapplicable proposals.

**Governing specification sections:** 31, 40, 64.10, 67.7, 68.3

#### Scope

Safe exact patch apply, stale/path protection, dry run, idempotency, ledger, and UI.

#### Out of scope

Patch preflight/build/test validation, automatic conflict resolution, manual patch editing, and arbitrary file creation outside approved scope.

#### Backend slice

- **Application service/components:** PatchSafetyService and PatchApplyService for proposal reload, idempotency, checksum, state/plan/fingerprint checks, unified diff parsing, relative-path confinement, changed-file/risk checks, dry run, exact apply, post-fingerprint, and ledger.
- **Domain aggregate/projection:** RepairProposal apply state, PatchLedgerEntry, WorkspaceFingerprint.
- **Persistence:** Patch apply metadata/idempotency, ledger, post-fingerprint, command/transition events.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/repair-proposals/{proposalId}/apply; GET /api/v1/runs/{id}/repair-proposals/{proposalId}/apply-result`
- **Durable event:** REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED.
- **Artifact Store output:** Patch safety report, dry-run result, exact applied diff reference, patch ledger, pre/post fingerprints, and failure evidence.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Apply progress/results panel listing every safety check, exact outcome, stale/path/applicability errors, and immutable ledger link.
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
→ PatchSafetyService and PatchApplyService for proposal reload, idempotency, checksum, state/plan/fingerprint checks, unified diff parsing, relative-path confinement, changed-file/risk checks, dry run, exact apply, post-fingerprint, and ledger.
→ Patch apply metadata/idempotency, ledger, post-fingerprint, command/transition events.
→ ArtifactService finalizes evidence: Patch safety report, dry-run result, exact applied diff reference, patch ledger, pre/post fingerprints, and failure evidence.
→ Transition/Event service persists and emits: REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED.
→ SSE replay or snapshot refresh
→ Apply progress/results panel listing every safety check, exact outcome, stale/path/applicability errors, and immutable ledger link.
```

#### Exact apply lineage

`PatchSafetyService` verifies the complete G10 lineage, current fingerprint, plan version, relative paths, allowed changed-file scope, unified-diff syntax, applicability dry-run, and idempotency. `PatchApplyService` applies only the stored diff and writes a patch ledger plus post-apply fingerprint. A stale proposal is never refreshed or adapted automatically.

#### Sub-issues

- `S4-F07-I01` — Backend/application contract
- `S4-F07-I02` — Persistence, API, durable event, and artifact contract
- `S4-F07-I03` — Frontend projection and interaction
- `S4-F07-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Validate and apply only the exact persisted repair diff**, then the backend performs only the authorized service operation, persists the result, emits **REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED.**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Patch apply metadata/idempotency, ledger, post-fingerprint, command/transition events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Patch safety report, dry-run result, exact applied diff reference, patch ledger, pre/post fingerprints, and failure evidence.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S4-F06; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Apply progress/results panel listing every safety check, exact outcome, stale/path/applicability errors, and immutable ledger link.**.
3. Trigger the primary action for **Validate and apply only the exact persisted repair diff** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** After G10 Apply, a user can see checksum/fingerprint/path/scope/applicability checks and either an exact successful patch application with ledger or a fail-closed rejection. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Patch apply metadata/idempotency, ledger, post-fingerprint, command/transition events.` are retrievable through `POST /api/v1/runs/{id}/repair-proposals/{proposalId}/apply; GET /api/v1/runs/{id}/repair-proposals/{proposalId}/apply-result` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Patch safety report, dry-run result, exact applied diff reference, patch ledger, pre/post fingerprints, and failure evidence.

**Expected durable event:** REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED.

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

S4-F06

#### Risks and edge cases

- Path traversal
- symlink escape
- line-ending mismatch
- partial apply
- workspace change race
- duplicate request
- high-risk scope mismatch
- and rollback boundary.

#### Detailed sub-issues

#### S4-F07-I01 — Implement backend application contract for Validate and apply only the exact persisted repair diff

  - **Parent feature:** S4-F07
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Validate and apply only the exact persisted repair diff so the feature has one authoritative service path.
  - **Context:** PatchApplyService, not the UI or LLM, owns controlled mutation and must reject stale, escaping, or inapplicable proposals.
  - **Scope:** PatchSafetyService and PatchApplyService for proposal reload, idempotency, checksum, state/plan/fingerprint checks, unified diff parsing, relative-path confinement, changed-file/risk checks, dry run, exact apply, post-fingerprint, and ledger.
  - **Out of scope:** Patch preflight/build/test validation, automatic conflict resolution, manual patch editing, and arbitrary file creation outside approved scope.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/repair-proposals/{proposalId}/apply; GET /api/v1/runs/{id}/repair-proposals/{proposalId}/apply-result`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: PatchSafetyService and PatchApplyService for proposal reload, idempotency, checksum, state/plan/fingerprint checks, unified diff parsing, relative-path confinement, changed-file/risk checks, dry run, exact apply, post-fingerprint, and ledger.
  - **Database impact:** Use or introduce the records summarized by: Patch apply metadata/idempotency, ledger, post-fingerprint, command/transition events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/repair-proposals/{proposalId}/apply; GET /api/v1/runs/{id}/repair-proposals/{proposalId}/apply-result
  - **Event impact:** Request durable events only through the transition/event service: REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Patch safety report, dry-run result, exact applied diff reference, patch ledger, pre/post fingerprints, and failure evidence.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Path traversal, symlink escape, line-ending mismatch, partial apply, workspace change race, duplicate request, high-risk scope mismatch, and rollback boundary.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F06
  - **Suggested labels:** sprint-4, s4-f07, repair-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F07-I02 — Persist and expose evidence contracts for Validate and apply only the exact persisted repair diff

  - **Parent feature:** S4-F07
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Validate and apply only the exact persisted repair diff observable and auditable.
  - **Context:** PatchApplyService, not the UI or LLM, owns controlled mutation and must reject stale, escaping, or inapplicable proposals.
  - **Scope:** Persistence: Patch apply metadata/idempotency, ledger, post-fingerprint, command/transition events.. API: POST /api/v1/runs/{id}/repair-proposals/{proposalId}/apply; GET /api/v1/runs/{id}/repair-proposals/{proposalId}/apply-result. Events: REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED.. Artifacts: Patch safety report, dry-run result, exact applied diff reference, patch ledger, pre/post fingerprints, and failure evidence.
  - **Out of scope:** Patch preflight/build/test validation, automatic conflict resolution, manual patch editing, and arbitrary file creation outside approved scope.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Patch apply metadata/idempotency, ledger, post-fingerprint, command/transition events.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/repair-proposals/{proposalId}/apply; GET /api/v1/runs/{id}/repair-proposals/{proposalId}/apply-result; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Patch safety report, dry-run result, exact applied diff reference, patch ledger, pre/post fingerprints, and failure evidence.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F07-I01
  - **Suggested labels:** sprint-4, s4-f07, repair-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F07-I03 — Build frontend experience for Validate and apply only the exact persisted repair diff

  - **Parent feature:** S4-F07
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Validate and apply only the exact persisted repair diff, using backend snapshots and durable events only.
  - **Context:** PatchApplyService, not the UI or LLM, owns controlled mutation and must reject stale, escaping, or inapplicable proposals.
  - **Scope:** Apply progress/results panel listing every safety check, exact outcome, stale/path/applicability errors, and immutable ledger link.
  - **Out of scope:** Patch preflight/build/test validation, automatic conflict resolution, manual patch editing, and arbitrary file creation outside approved scope.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/repair-proposals/{proposalId}/apply; GET /api/v1/runs/{id}/repair-proposals/{proposalId}/apply-result` plus durable events `REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Apply progress/results panel listing every safety check, exact outcome, stale/path/applicability errors, and immutable ledger link.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/repair-proposals/{proposalId}/apply; GET /api/v1/runs/{id}/repair-proposals/{proposalId}/apply-result` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Patch safety report, dry-run result, exact applied diff reference, patch ledger, pre/post fingerprints, and failure evidence.
  - **UI impact:** Implement: Apply progress/results panel listing every safety check, exact outcome, stale/path/applicability errors, and immutable ledger link.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F07-I02
  - **Suggested labels:** sprint-4, s4-f07, repair-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F07-I04 — Verify and document Validate and apply only the exact persisted repair diff

  - **Parent feature:** S4-F07
  - **Issue type:** Testing
  - **Technical story:** Prove Validate and apply only the exact persisted repair diff through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** PatchApplyService, not the UI or LLM, owns controlled mutation and must reject stale, escaping, or inapplicable proposals.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Patch preflight/build/test validation, automatic conflict resolution, manual patch editing, and arbitrary file creation outside approved scope.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/repair-proposals/{proposalId}/apply; GET /api/v1/runs/{id}/repair-proposals/{proposalId}/apply-result` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Patch safety report, dry-run result, exact applied diff reference, patch ledger, pre/post fingerprints, and failure evidence.` where applicable.
  - **UI impact:** Execute the feature through `Apply progress/results panel listing every safety check, exact outcome, stale/path/applicability errors, and immutable ledger link.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Path traversal, symlink escape, line-ending mismatch, partial apply, workspace change race, duplicate request, high-risk scope mismatch, and rollback boundary.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F07-I03
  - **Suggested labels:** sprint-4, s4-f07, repair-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---


### S4-F08 — Run patch preflight, resume normal validation, and decide G11

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Approval capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G11

#### User-observable outcome

A reviewer can see deterministic patch preflight, the earliest invalidated normal validation boundary, full rerun evidence, error delta, and decide G11 repair validation acceptance.

#### Context

Patch preflight is fast feedback only; the repair must use the same ExecutionProfile and normal stage pipeline.

**Governing specification sections:** 31.5, 32.1, 56.12, 64.11-64.12

#### Scope

Preflight, normal-pipeline reuse, same profile, fresh evidence on failure, G11, and UI.

#### Out of scope

No-progress policy across multiple attempts, startup recovery, final assurance, and stage auto-completion.

#### Backend slice

- **Application service/components:** PatchPreflightValidator, invalidation-boundary resolver, StageValidation resume command, same-profile/plan enforcement, error-delta calculator, G11 package, and fresh-failure hook.
- **Domain aggregate/projection:** RepairAttempt, ValidationRun, ApprovalGate G11.
- **Persistence:** Preflight results, validation rerun references, error delta, attempt outcome, gate/decision records.
- **State/approval rule:** G11 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/validate; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/validation; POST /api/v1/runs/{id}/approvals/G11/decisions`
- **Durable event:** PATCH_PREFLIGHT_COMPLETED, REPAIR_VALIDATION_STARTED/COMPLETED/FAILED and G11 events.
- **Artifact Store output:** Patch preflight report, invalidation decision, rerun logs/results, error delta, repair validation summary, and G11 package.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Repair validation timeline showing preflight versus authoritative gates, profile/plan match, rerun evidence, delta, fresh failure link, and G11 controls.
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
→ PatchPreflightValidator, invalidation-boundary resolver, StageValidation resume command, same-profile/plan enforcement, error-delta calculator, G11 package, and fresh-failure hook.
→ Preflight results, validation rerun references, error delta, attempt outcome, gate/decision records.
→ ArtifactService finalizes evidence: Patch preflight report, invalidation decision, rerun logs/results, error delta, repair validation summary, and G11 package.
→ Transition/Event service persists and emits: PATCH_PREFLIGHT_COMPLETED, REPAIR_VALIDATION_STARTED/COMPLETED/FAILED and G11 events.
→ SSE replay or snapshot refresh
→ Repair validation timeline showing preflight versus authoritative gates, profile/plan match, rerun evidence, delta, fresh failure link, and G11 controls.
```

#### Sub-issues

- `S4-F08-I01` — Backend/application contract
- `S4-F08-I02` — Persistence, API, durable event, and artifact contract
- `S4-F08-I03` — Frontend projection and interaction
- `S4-F08-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Run patch preflight, resume normal validation, and decide G11**, then the backend performs only the authorized service operation, persists the result, emits **PATCH_PREFLIGHT_COMPLETED,**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Preflight results, validation rerun references, error delta, attempt outcome, gate/decision records.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Patch preflight report, invalidation decision, rerun logs/results, error delta, repair validation summary, and G11 package.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G11 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G11 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.

#### Manual end-to-end test scenario

**Preconditions:** S4-F07, S3-F13; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Repair validation timeline showing preflight versus authoritative gates, profile/plan match, rerun evidence, delta, fresh failure link, and G11 controls.**.
    3. Trigger the primary action for **Run patch preflight, resume normal validation, and decide G11** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G11** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can see deterministic patch preflight, the earliest invalidated normal validation boundary, full rerun evidence, error delta, and decide G11 repair validation acceptance. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `Preflight results, validation rerun references, error delta, attempt outcome, gate/decision records.` are retrievable through `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/validate; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/validation; POST /api/v1/runs/{id}/approvals/G11/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Patch preflight report, invalidation decision, rerun logs/results, error delta, repair validation summary, and G11 package.

    **Expected durable event:** PATCH_PREFLIGHT_COMPLETED, REPAIR_VALIDATION_STARTED/COMPLETED/FAILED and G11 events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G11 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

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

S4-F07, S3-F13

#### Risks and edge cases

- Treating preflight as pass
- skipping invalidated install/build/test
- wrong profile
- stale prior evidence
- approval bypassing failed build
- and failure evidence reuse.

#### Detailed sub-issues

#### S4-F08-I01 — Implement backend application contract for Run patch preflight, resume normal validation, and decide G11

  - **Parent feature:** S4-F08
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Run patch preflight, resume normal validation, and decide G11 so the feature has one authoritative service path.
  - **Context:** Patch preflight is fast feedback only; the repair must use the same ExecutionProfile and normal stage pipeline.
  - **Scope:** PatchPreflightValidator, invalidation-boundary resolver, StageValidation resume command, same-profile/plan enforcement, error-delta calculator, G11 package, and fresh-failure hook.
  - **Out of scope:** No-progress policy across multiple attempts, startup recovery, final assurance, and stage auto-completion.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G11 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/validate; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/validation; POST /api/v1/runs/{id}/approvals/G11/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: PatchPreflightValidator, invalidation-boundary resolver, StageValidation resume command, same-profile/plan enforcement, error-delta calculator, G11 package, and fresh-failure hook.
  - **Database impact:** Use or introduce the records summarized by: Preflight results, validation rerun references, error delta, attempt outcome, gate/decision records.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/validate; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/validation; POST /api/v1/runs/{id}/approvals/G11/decisions
  - **Event impact:** Request durable events only through the transition/event service: PATCH_PREFLIGHT_COMPLETED, REPAIR_VALIDATION_STARTED/COMPLETED/FAILED and G11 events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Patch preflight report, invalidation decision, rerun logs/results, error delta, repair validation summary, and G11 package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Treating preflight as pass, skipping invalidated install/build/test, wrong profile, stale prior evidence, approval bypassing failed build, and failure evidence reuse.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G11 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F07, S3-F13
  - **Suggested labels:** sprint-4, s4-f08, approval-capability, backend, g11, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F08-I02 — Persist and expose evidence contracts for Run patch preflight, resume normal validation, and decide G11

  - **Parent feature:** S4-F08
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Run patch preflight, resume normal validation, and decide G11 observable and auditable.
  - **Context:** Patch preflight is fast feedback only; the repair must use the same ExecutionProfile and normal stage pipeline.
  - **Scope:** Persistence: Preflight results, validation rerun references, error delta, attempt outcome, gate/decision records.. API: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/validate; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/validation; POST /api/v1/runs/{id}/approvals/G11/decisions. Events: PATCH_PREFLIGHT_COMPLETED, REPAIR_VALIDATION_STARTED/COMPLETED/FAILED and G11 events.. Artifacts: Patch preflight report, invalidation decision, rerun logs/results, error delta, repair validation summary, and G11 package.
  - **Out of scope:** No-progress policy across multiple attempts, startup recovery, final assurance, and stage auto-completion.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Preflight results, validation rerun references, error delta, attempt outcome, gate/decision records.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/repair-attempts/{attemptId}/validate; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/validation; POST /api/v1/runs/{id}/approvals/G11/decisions; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: PATCH_PREFLIGHT_COMPLETED, REPAIR_VALIDATION_STARTED/COMPLETED/FAILED and G11 events.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Patch preflight report, invalidation decision, rerun logs/results, error delta, repair validation summary, and G11 package.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G11 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F08-I01
  - **Suggested labels:** sprint-4, s4-f08, approval-capability, api, g11, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F08-I03 — Build frontend experience for Run patch preflight, resume normal validation, and decide G11

  - **Parent feature:** S4-F08
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Run patch preflight, resume normal validation, and decide G11, using backend snapshots and durable events only.
  - **Context:** Patch preflight is fast feedback only; the repair must use the same ExecutionProfile and normal stage pipeline.
  - **Scope:** Repair validation timeline showing preflight versus authoritative gates, profile/plan match, rerun evidence, delta, fresh failure link, and G11 controls.
  - **Out of scope:** No-progress policy across multiple attempts, startup recovery, final assurance, and stage auto-completion.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/validate; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/validation; POST /api/v1/runs/{id}/approvals/G11/decisions` plus durable events `PATCH_PREFLIGHT_COMPLETED, REPAIR_VALIDATION_STARTED/COMPLETED/FAILED and G11 events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Repair validation timeline showing preflight versus authoritative gates, profile/plan match, rerun evidence, delta, fresh failure link, and G11 controls.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/validate; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/validation; POST /api/v1/runs/{id}/approvals/G11/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `PATCH_PREFLIGHT_COMPLETED, REPAIR_VALIDATION_STARTED/COMPLETED/FAILED and G11 events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Patch preflight report, invalidation decision, rerun logs/results, error delta, repair validation summary, and G11 package.
  - **UI impact:** Implement: Repair validation timeline showing preflight versus authoritative gates, profile/plan match, rerun evidence, delta, fresh failure link, and G11 controls.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G11 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F08-I02
  - **Suggested labels:** sprint-4, s4-f08, approval-capability, frontend, g11, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F08-I04 — Verify and document Run patch preflight, resume normal validation, and decide G11

  - **Parent feature:** S4-F08
  - **Issue type:** Testing
  - **Technical story:** Prove Run patch preflight, resume normal validation, and decide G11 through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Patch preflight is fast feedback only; the repair must use the same ExecutionProfile and normal stage pipeline.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** No-progress policy across multiple attempts, startup recovery, final assurance, and stage auto-completion.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/repair-attempts/{attemptId}/validate; GET /api/v1/runs/{id}/repair-attempts/{attemptId}/validation; POST /api/v1/runs/{id}/approvals/G11/decisions` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `PATCH_PREFLIGHT_COMPLETED, REPAIR_VALIDATION_STARTED/COMPLETED/FAILED and G11 events.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Patch preflight report, invalidation decision, rerun logs/results, error delta, repair validation summary, and G11 package.` where applicable.
  - **UI impact:** Execute the feature through `Repair validation timeline showing preflight versus authoritative gates, profile/plan match, rerun evidence, delta, fresh failure link, and G11 controls.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Treating preflight as pass, skipping invalidated install/build/test, wrong profile, stale prior evidence, approval bypassing failed build, and failure evidence reuse.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G11 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F08-I03
  - **Suggested labels:** sprint-4, s4-f08, approval-capability, testing, g11, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---


### S4-F09 — Stop no-progress repair loops and reconstruct or roll back safely

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Repair capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A reviewer can see attempt counts, patch/failure fingerprints, error deltas, duplicate/no-progress decisions, rollback or stage reconstruction, and diagnostic hold after policy limits.

#### Context

Bounded repair protects cost, source parity, and delivery predictability; repeated equivalent patches must never loop.

**Governing specification sections:** 29.3, 32.2-32.4, 64.7-64.8, 64.13, 70.5

#### Scope

Duplicate/no-progress protection, limits, rollback/reconstruction, fresh attempt lineage, and UI.

#### Out of scope

Automatic business-level resolution, unlimited human overrides, and cross-run learning.

#### Backend slice

- **Application service/components:** RepairProgressService, semantic patch normalization/fingerprints, failure-set comparison, max-three applied attempts, revision/transport counters separation, rollback checkpoint or WorkspaceManager reconstruction, and diagnostic-hold transitions.
- **Domain aggregate/projection:** RepairChain, RepairAttempt, MigrationStage repair status.
- **Persistence:** Attempt counters/outcomes, no-progress decisions, rollback/reconstruction records, state/events.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `GET /api/v1/runs/{id}/repair-chains/{chainId}; POST /api/v1/runs/{id}/repair-chains/{chainId}/recover`
- **Durable event:** DUPLICATE_PATCH_REJECTED, NO_PROGRESS_DETECTED, REPAIR_ROLLED_BACK, STAGE_RECONSTRUCTED, ATTEMPT_LIMIT_REACHED.
- **Artifact Store output:** Attempt lineage, fingerprint comparison, error-delta history, rollback/reconstruction report, and diagnostic-hold summary.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Repair history view with attempts/revisions/transport retries separated, progress chart/table, stop reason, recovery action, and diagnostic-hold state.
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
→ RepairProgressService, semantic patch normalization/fingerprints, failure-set comparison, max-three applied attempts, revision/transport counters separation, rollback checkpoint or WorkspaceManager reconstruction, and diagnostic-hold transitions.
→ Attempt counters/outcomes, no-progress decisions, rollback/reconstruction records, state/events.
→ ArtifactService finalizes evidence: Attempt lineage, fingerprint comparison, error-delta history, rollback/reconstruction report, and diagnostic-hold summary.
→ Transition/Event service persists and emits: DUPLICATE_PATCH_REJECTED, NO_PROGRESS_DETECTED, REPAIR_ROLLED_BACK, STAGE_RECONSTRUCTED, ATTEMPT_LIMIT_REACHED.
→ SSE replay or snapshot refresh
→ Repair history view with attempts/revisions/transport retries separated, progress chart/table, stop reason, recovery action, and diagnostic-hold state.
```

#### Sub-issues

- `S4-F09-I01` — Backend/application contract
- `S4-F09-I02` — Persistence, API, durable event, and artifact contract
- `S4-F09-I03` — Frontend projection and interaction
- `S4-F09-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Stop no-progress repair loops and reconstruct or roll back safely**, then the backend performs only the authorized service operation, persists the result, emits **DUPLICATE_PATCH_REJECTED,**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Attempt counters/outcomes, no-progress decisions, rollback/reconstruction records, state/events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Attempt lineage, fingerprint comparison, error-delta history, rollback/reconstruction report, and diagnostic-hold summary.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S4-F08; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Repair history view with attempts/revisions/transport retries separated, progress chart/table, stop reason, recovery action, and diagnostic-hold state.**.
3. Trigger the primary action for **Stop no-progress repair loops and reconstruct or roll back safely** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A reviewer can see attempt counts, patch/failure fingerprints, error deltas, duplicate/no-progress decisions, rollback or stage reconstruction, and diagnostic hold after policy limits. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Attempt counters/outcomes, no-progress decisions, rollback/reconstruction records, state/events.` are retrievable through `GET /api/v1/runs/{id}/repair-chains/{chainId}; POST /api/v1/runs/{id}/repair-chains/{chainId}/recover` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Attempt lineage, fingerprint comparison, error-delta history, rollback/reconstruction report, and diagnostic-hold summary.

**Expected durable event:** DUPLICATE_PATCH_REJECTED, NO_PROGRESS_DETECTED, REPAIR_ROLLED_BACK, STAGE_RECONSTRUCTED, ATTEMPT_LIMIT_REACHED.

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

S4-F08

#### Risks and edge cases

- Equivalent patch normalization false positive
- rollback incomplete
- reconstruction from wrong input
- attempts miscounted
- cost race
- and high-risk change escalation.

#### Detailed sub-issues

#### S4-F09-I01 — Implement backend application contract for Stop no-progress repair loops and reconstruct or roll back safely

  - **Parent feature:** S4-F09
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Stop no-progress repair loops and reconstruct or roll back safely so the feature has one authoritative service path.
  - **Context:** Bounded repair protects cost, source parity, and delivery predictability; repeated equivalent patches must never loop.
  - **Scope:** RepairProgressService, semantic patch normalization/fingerprints, failure-set comparison, max-three applied attempts, revision/transport counters separation, rollback checkpoint or WorkspaceManager reconstruction, and diagnostic-hold transitions.
  - **Out of scope:** Automatic business-level resolution, unlimited human overrides, and cross-run learning.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `GET /api/v1/runs/{id}/repair-chains/{chainId}; POST /api/v1/runs/{id}/repair-chains/{chainId}/recover`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: RepairProgressService, semantic patch normalization/fingerprints, failure-set comparison, max-three applied attempts, revision/transport counters separation, rollback checkpoint or WorkspaceManager reconstruction, and diagnostic-hold transitions.
  - **Database impact:** Use or introduce the records summarized by: Attempt counters/outcomes, no-progress decisions, rollback/reconstruction records, state/events.
  - **API impact:** Define service-facing request/response models supporting: GET /api/v1/runs/{id}/repair-chains/{chainId}; POST /api/v1/runs/{id}/repair-chains/{chainId}/recover
  - **Event impact:** Request durable events only through the transition/event service: DUPLICATE_PATCH_REJECTED, NO_PROGRESS_DETECTED, REPAIR_ROLLED_BACK, STAGE_RECONSTRUCTED, ATTEMPT_LIMIT_REACHED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Attempt lineage, fingerprint comparison, error-delta history, rollback/reconstruction report, and diagnostic-hold summary.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Equivalent patch normalization false positive, rollback incomplete, reconstruction from wrong input, attempts miscounted, cost race, and high-risk change escalation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F08
  - **Suggested labels:** sprint-4, s4-f09, repair-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F09-I02 — Persist and expose evidence contracts for Stop no-progress repair loops and reconstruct or roll back safely

  - **Parent feature:** S4-F09
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Stop no-progress repair loops and reconstruct or roll back safely observable and auditable.
  - **Context:** Bounded repair protects cost, source parity, and delivery predictability; repeated equivalent patches must never loop.
  - **Scope:** Persistence: Attempt counters/outcomes, no-progress decisions, rollback/reconstruction records, state/events.. API: GET /api/v1/runs/{id}/repair-chains/{chainId}; POST /api/v1/runs/{id}/repair-chains/{chainId}/recover. Events: DUPLICATE_PATCH_REJECTED, NO_PROGRESS_DETECTED, REPAIR_ROLLED_BACK, STAGE_RECONSTRUCTED, ATTEMPT_LIMIT_REACHED.. Artifacts: Attempt lineage, fingerprint comparison, error-delta history, rollback/reconstruction report, and diagnostic-hold summary.
  - **Out of scope:** Automatic business-level resolution, unlimited human overrides, and cross-run learning.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Attempt counters/outcomes, no-progress decisions, rollback/reconstruction records, state/events.
  - **API impact:** Implement and document: GET /api/v1/runs/{id}/repair-chains/{chainId}; POST /api/v1/runs/{id}/repair-chains/{chainId}/recover; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: DUPLICATE_PATCH_REJECTED, NO_PROGRESS_DETECTED, REPAIR_ROLLED_BACK, STAGE_RECONSTRUCTED, ATTEMPT_LIMIT_REACHED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Attempt lineage, fingerprint comparison, error-delta history, rollback/reconstruction report, and diagnostic-hold summary.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F09-I01
  - **Suggested labels:** sprint-4, s4-f09, repair-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F09-I03 — Build frontend experience for Stop no-progress repair loops and reconstruct or roll back safely

  - **Parent feature:** S4-F09
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Stop no-progress repair loops and reconstruct or roll back safely, using backend snapshots and durable events only.
  - **Context:** Bounded repair protects cost, source parity, and delivery predictability; repeated equivalent patches must never loop.
  - **Scope:** Repair history view with attempts/revisions/transport retries separated, progress chart/table, stop reason, recovery action, and diagnostic-hold state.
  - **Out of scope:** Automatic business-level resolution, unlimited human overrides, and cross-run learning.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `GET /api/v1/runs/{id}/repair-chains/{chainId}; POST /api/v1/runs/{id}/repair-chains/{chainId}/recover` plus durable events `DUPLICATE_PATCH_REJECTED, NO_PROGRESS_DETECTED, REPAIR_ROLLED_BACK, STAGE_RECONSTRUCTED, ATTEMPT_LIMIT_REACHED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Repair history view with attempts/revisions/transport retries separated, progress chart/table, stop reason, recovery action, and diagnostic-hold state.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `GET /api/v1/runs/{id}/repair-chains/{chainId}; POST /api/v1/runs/{id}/repair-chains/{chainId}/recover` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `DUPLICATE_PATCH_REJECTED, NO_PROGRESS_DETECTED, REPAIR_ROLLED_BACK, STAGE_RECONSTRUCTED, ATTEMPT_LIMIT_REACHED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Attempt lineage, fingerprint comparison, error-delta history, rollback/reconstruction report, and diagnostic-hold summary.
  - **UI impact:** Implement: Repair history view with attempts/revisions/transport retries separated, progress chart/table, stop reason, recovery action, and diagnostic-hold state.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F09-I02
  - **Suggested labels:** sprint-4, s4-f09, repair-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F09-I04 — Verify and document Stop no-progress repair loops and reconstruct or roll back safely

  - **Parent feature:** S4-F09
  - **Issue type:** Testing
  - **Technical story:** Prove Stop no-progress repair loops and reconstruct or roll back safely through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Bounded repair protects cost, source parity, and delivery predictability; repeated equivalent patches must never loop.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Automatic business-level resolution, unlimited human overrides, and cross-run learning.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `GET /api/v1/runs/{id}/repair-chains/{chainId}; POST /api/v1/runs/{id}/repair-chains/{chainId}/recover` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `DUPLICATE_PATCH_REJECTED, NO_PROGRESS_DETECTED, REPAIR_ROLLED_BACK, STAGE_RECONSTRUCTED, ATTEMPT_LIMIT_REACHED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Attempt lineage, fingerprint comparison, error-delta history, rollback/reconstruction report, and diagnostic-hold summary.` where applicable.
  - **UI impact:** Execute the feature through `Repair history view with attempts/revisions/transport retries separated, progress chart/table, stop reason, recovery action, and diagnostic-hold state.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Equivalent patch normalization false positive, rollback incomplete, reconstruction from wrong input, attempts miscounted, cost race, and high-risk change escalation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F09-I03
  - **Suggested labels:** sprint-4, s4-f09, repair-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---


### S4-F10 — Reconcile interrupted commands, leases, artifacts, and graph state on startup

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Operational capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

After a controlled backend restart, an operator can see stale ownership and artifact inconsistencies reconciled, waiting approvals preserved, and work resumed/reconstructed only from a proven boundary.

#### Context

SQLite is authoritative and LangGraph checkpoints are resume hints; restart must not duplicate mutation or invent evidence.

**Governing specification sections:** 10.3, 33, 35, 54.8-54.9, 65.6, 70.7-70.8

#### Scope

Startup command/lease/artifact/graph reconciliation, safe resume/reconstruct decisions, and UI.

#### Out of scope

Distributed recovery, cross-host process adoption, silent artifact repair, and permanent retention deletion.

#### Backend slice

- **Application service/components:** StartupReconciliationService for backend instance ID, stale leases/commands, mutation-category recovery, graph reconstruction from SQLite, artifact temp/orphan/missing/hash checks, workspace quarantine, and Transition Service recovery states.
- **Domain aggregate/projection:** WorkerLease, CommandExecution, Artifact reconciliation records, MigrationRun/Stage recovery state.
- **Persistence:** Reconciliation run/results, interrupted statuses, lease updates, artifact integrity findings, transitions/events.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/operator/reconciliation; GET /api/v1/operator/reconciliation/latest; POST /api/v1/runs/{id}/resume`
- **Durable event:** RECONCILIATION_STARTED/COMPLETED, COMMAND_INTERRUPTED, ARTIFACT_INTEGRITY_FAILED, RUN_RECOVERY_READY/DIAGNOSTIC_HOLD.
- **Artifact Store output:** Startup reconciliation report, artifact mismatch list, workspace recovery decision, and graph reconstruction summary.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Operator recovery dashboard and run resume panel with proven boundary, preserved approval, quarantine links, and blocked/failure states.
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
→ StartupReconciliationService for backend instance ID, stale leases/commands, mutation-category recovery, graph reconstruction from SQLite, artifact temp/orphan/missing/hash checks, workspace quarantine, and Transition Service recovery states.
→ Reconciliation run/results, interrupted statuses, lease updates, artifact integrity findings, transitions/events.
→ ArtifactService finalizes evidence: Startup reconciliation report, artifact mismatch list, workspace recovery decision, and graph reconstruction summary.
→ Transition/Event service persists and emits: RECONCILIATION_STARTED/COMPLETED, COMMAND_INTERRUPTED, ARTIFACT_INTEGRITY_FAILED, RUN_RECOVERY_READY/DIAGNOSTIC_HOLD.
→ SSE replay or snapshot refresh
→ Operator recovery dashboard and run resume panel with proven boundary, preserved approval, quarantine links, and blocked/failure states.
```

#### Sub-issues

- `S4-F10-I01` — Backend/application contract
- `S4-F10-I02` — Persistence, API, durable event, and artifact contract
- `S4-F10-I03` — Frontend projection and interaction
- `S4-F10-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Reconcile interrupted commands, leases, artifacts, and graph state on startup**, then the backend performs only the authorized service operation, persists the result, emits **RECONCILIATION_STARTED/COMPLETED,**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Reconciliation run/results, interrupted statuses, lease updates, artifact integrity findings, transitions/events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Startup reconciliation report, artifact mismatch list, workspace recovery decision, and graph reconstruction summary.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Execution authority:** Given any attempt to bypass the registered command template, approved plan, exact profile, workspace alias, or `shell=false` policy, when authorization runs, then execution is rejected before process creation.

#### Manual end-to-end test scenario

**Preconditions:** S3-F04, S3-F14, S4-F09; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Operator recovery dashboard and run resume panel with proven boundary, preserved approval, quarantine links, and blocked/failure states.**.
3. Trigger the primary action for **Reconcile interrupted commands, leases, artifacts, and graph state on startup** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** After a controlled backend restart, an operator can see stale ownership and artifact inconsistencies reconciled, waiting approvals preserved, and work resumed/reconstructed only from a proven boundary. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Reconciliation run/results, interrupted statuses, lease updates, artifact integrity findings, transitions/events.` are retrievable through `POST /api/v1/operator/reconciliation; GET /api/v1/operator/reconciliation/latest; POST /api/v1/runs/{id}/resume` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Startup reconciliation report, artifact mismatch list, workspace recovery decision, and graph reconstruction summary.

**Expected durable event:** RECONCILIATION_STARTED/COMPLETED, COMMAND_INTERRUPTED, ARTIFACT_INTEGRITY_FAILED, RUN_RECOVERY_READY/DIAGNOSTIC_HOLD.

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

S3-F04, S3-F14, S4-F09

#### Risks and edge cases

- PID reuse
- old backend process still alive
- artifact mismatch
- checkpoint newer than DB
- unsafe mid-update resume
- duplicate command
- and operator choosing invalid boundary.

#### Detailed sub-issues

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

#### S4-F10-I02 — Persist and expose evidence contracts for Reconcile interrupted commands, leases, artifacts, and graph state on startup

  - **Parent feature:** S4-F10
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Reconcile interrupted commands, leases, artifacts, and graph state on startup observable and auditable.
  - **Context:** SQLite is authoritative and LangGraph checkpoints are resume hints; restart must not duplicate mutation or invent evidence.
  - **Scope:** Persistence: Reconciliation run/results, interrupted statuses, lease updates, artifact integrity findings, transitions/events.. API: POST /api/v1/operator/reconciliation; GET /api/v1/operator/reconciliation/latest; POST /api/v1/runs/{id}/resume. Events: RECONCILIATION_STARTED/COMPLETED, COMMAND_INTERRUPTED, ARTIFACT_INTEGRITY_FAILED, RUN_RECOVERY_READY/DIAGNOSTIC_HOLD.. Artifacts: Startup reconciliation report, artifact mismatch list, workspace recovery decision, and graph reconstruction summary.
  - **Out of scope:** Distributed recovery, cross-host process adoption, silent artifact repair, and permanent retention deletion.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Reconciliation run/results, interrupted statuses, lease updates, artifact integrity findings, transitions/events.
  - **API impact:** Implement and document: POST /api/v1/operator/reconciliation; GET /api/v1/operator/reconciliation/latest; POST /api/v1/runs/{id}/resume; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: RECONCILIATION_STARTED/COMPLETED, COMMAND_INTERRUPTED, ARTIFACT_INTEGRITY_FAILED, RUN_RECOVERY_READY/DIAGNOSTIC_HOLD.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Startup reconciliation report, artifact mismatch list, workspace recovery decision, and graph reconstruction summary.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F10-I01
  - **Suggested labels:** sprint-4, s4-f10, operational-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F10-I03 — Build frontend experience for Reconcile interrupted commands, leases, artifacts, and graph state on startup

  - **Parent feature:** S4-F10
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Reconcile interrupted commands, leases, artifacts, and graph state on startup, using backend snapshots and durable events only.
  - **Context:** SQLite is authoritative and LangGraph checkpoints are resume hints; restart must not duplicate mutation or invent evidence.
  - **Scope:** Operator recovery dashboard and run resume panel with proven boundary, preserved approval, quarantine links, and blocked/failure states.
  - **Out of scope:** Distributed recovery, cross-host process adoption, silent artifact repair, and permanent retention deletion.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/operator/reconciliation; GET /api/v1/operator/reconciliation/latest; POST /api/v1/runs/{id}/resume` plus durable events `RECONCILIATION_STARTED/COMPLETED, COMMAND_INTERRUPTED, ARTIFACT_INTEGRITY_FAILED, RUN_RECOVERY_READY/DIAGNOSTIC_HOLD.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Operator recovery dashboard and run resume panel with proven boundary, preserved approval, quarantine links, and blocked/failure states.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/operator/reconciliation; GET /api/v1/operator/reconciliation/latest; POST /api/v1/runs/{id}/resume` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `RECONCILIATION_STARTED/COMPLETED, COMMAND_INTERRUPTED, ARTIFACT_INTEGRITY_FAILED, RUN_RECOVERY_READY/DIAGNOSTIC_HOLD.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Startup reconciliation report, artifact mismatch list, workspace recovery decision, and graph reconstruction summary.
  - **UI impact:** Implement: Operator recovery dashboard and run resume panel with proven boundary, preserved approval, quarantine links, and blocked/failure states.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F10-I02
  - **Suggested labels:** sprint-4, s4-f10, operational-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F10-I04 — Verify and document Reconcile interrupted commands, leases, artifacts, and graph state on startup

  - **Parent feature:** S4-F10
  - **Issue type:** Testing
  - **Technical story:** Prove Reconcile interrupted commands, leases, artifacts, and graph state on startup through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** SQLite is authoritative and LangGraph checkpoints are resume hints; restart must not duplicate mutation or invent evidence.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Distributed recovery, cross-host process adoption, silent artifact repair, and permanent retention deletion.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/operator/reconciliation; GET /api/v1/operator/reconciliation/latest; POST /api/v1/runs/{id}/resume` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `RECONCILIATION_STARTED/COMPLETED, COMMAND_INTERRUPTED, ARTIFACT_INTEGRITY_FAILED, RUN_RECOVERY_READY/DIAGNOSTIC_HOLD.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Startup reconciliation report, artifact mismatch list, workspace recovery decision, and graph reconstruction summary.` where applicable.
  - **UI impact:** Execute the feature through `Operator recovery dashboard and run resume panel with proven boundary, preserved approval, quarantine links, and blocked/failure states.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: PID reuse, old backend process still alive, artifact mismatch, checkpoint newer than DB, unsafe mid-update resume, duplicate command, and operator choosing invalid boundary.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F10-I03
  - **Suggested labels:** sprint-4, s4-f10, operational-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---


### S4-F11 — Explain authoritative migration state through the AI Assistant

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Product capability
- **Priority:** Should
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A user can ask what is happening, why approval is needed, what failed or changed, which evidence exists, and token/cost usage; answers cite approved state/artifacts and cannot execute or approve.

#### Context

The Assistant improves comprehension but remains read-only and subordinate to authoritative services.

**Governing specification sections:** 37-39, 52.6, 68.6

#### Scope

Read-only evidence-grounded Assistant for run/stage/repair/report explanation.

#### Out of scope

Direct command/file tools, silent approval, raw secret exposure, unrestricted filesystem search, and autonomous workflow changes.

#### Backend slice

- **Application service/components:** AssistantContextService selecting authoritative state and approved artifacts, sanitized bounded prompt, structured answer with evidence refs/proof labels, LLM usage/cost, and explicit forbidden-action policy.
- **Domain aggregate/projection:** AssistantConversation metadata and LLMInvocation.
- **Persistence:** Conversation/message metadata, artifact refs, usage/cost; no hidden chain-of-thought.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/assistant/messages; GET /api/v1/runs/{id}/assistant/messages`
- **Durable event:** ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED.
- **Artifact Store output:** Sanitized assistant input manifest, structured answer, evidence citations, and usage record.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Chat panel with suggested questions, evidence links, proof labels, streaming/progress, empty/error/budget-blocked states, and disabled mutation/approval actions.
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
→ AssistantContextService selecting authoritative state and approved artifacts, sanitized bounded prompt, structured answer with evidence refs/proof labels, LLM usage/cost, and explicit forbidden-action policy.
→ Conversation/message metadata, artifact refs, usage/cost; no hidden chain-of-thought.
→ ArtifactService finalizes evidence: Sanitized assistant input manifest, structured answer, evidence citations, and usage record.
→ Transition/Event service persists and emits: ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED.
→ SSE replay or snapshot refresh
→ Chat panel with suggested questions, evidence links, proof labels, streaming/progress, empty/error/budget-blocked states, and disabled mutation/approval actions.
```

#### Assistant LLM policy

- Use the shared Sprint 2 gateway with the `assistant` role and append-only invocation ledger.
- Build each stateless request (`store=false`) from the authoritative state snapshot, approved artifact references, bounded safe previews, the current question, and a bounded recent conversation window.
- Never grant unrestricted filesystem browsing, command execution, file mutation, state transition, or gate approval.
- Natural-language answers may use a typed/redacted envelope without a strict domain schema. Any navigation, artifact-open, or approval intent uses a separate structured intent schema.
- An approval intent is not an approval; it must invoke the normal approval API with current state and checksum validation.
- A deterministic read-only fallback explanation is allowed during Azure outage and must be visibly labelled as `deterministic_fallback`.

#### Sub-issues

- `S4-F11-I01` — Backend/application contract
- `S4-F11-I02` — Persistence, API, durable event, and artifact contract
- `S4-F11-I03` — Frontend projection and interaction
- `S4-F11-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Explain authoritative migration state through the AI Assistant**, then the backend performs only the authorized service operation, persists the result, emits **ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED.**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Conversation/message metadata, artifact refs, usage/cost; no hidden chain-of-thought.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Sanitized assistant input manifest, structured answer, evidence citations, and usage record.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S2-F03, S4-F10; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Chat panel with suggested questions, evidence links, proof labels, streaming/progress, empty/error/budget-blocked states, and disabled mutation/approval actions.**.
3. Trigger the primary action for **Explain authoritative migration state through the AI Assistant** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** A user can ask what is happening, why approval is needed, what failed or changed, which evidence exists, and token/cost usage; answers cite approved state/artifacts and cannot execute or approve. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Conversation/message metadata, artifact refs, usage/cost; no hidden chain-of-thought.` are retrievable through `POST /api/v1/runs/{id}/assistant/messages; GET /api/v1/runs/{id}/assistant/messages` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** Sanitized assistant input manifest, structured answer, evidence citations, and usage record.

**Expected durable event:** ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED.

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

S2-F03, S4-F10

#### Risks and edge cases

- Hallucinated status
- prompt injection
- stale evidence
- unauthorized artifact
- chat interpreted as approval
- secret leakage
- and high cost.

#### Detailed sub-issues

#### S4-F11-I01 — Implement backend application contract for Explain authoritative migration state through the AI Assistant

  - **Parent feature:** S4-F11
  - **Issue type:** Agent
  - **Technical story:** Implement the bounded backend/application behavior for Explain authoritative migration state through the AI Assistant so the feature has one authoritative service path.
  - **Context:** The Assistant improves comprehension but remains read-only and subordinate to authoritative services.
  - **Scope:** AssistantContextService selecting authoritative state and approved artifacts, sanitized bounded prompt, structured answer with evidence refs/proof labels, LLM usage/cost, and explicit forbidden-action policy.
  - **Out of scope:** Direct command/file tools, silent approval, raw secret exposure, unrestricted filesystem search, and autonomous workflow changes.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/assistant/messages; GET /api/v1/runs/{id}/assistant/messages`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: AssistantContextService selecting authoritative state and approved artifacts, sanitized bounded prompt, structured answer with evidence refs/proof labels, LLM usage/cost, and explicit forbidden-action policy.
  - **Database impact:** Use or introduce the records summarized by: Conversation/message metadata, artifact refs, usage/cost; no hidden chain-of-thought.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/assistant/messages; GET /api/v1/runs/{id}/assistant/messages
  - **Event impact:** Request durable events only through the transition/event service: ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Sanitized assistant input manifest, structured answer, evidence citations, and usage record.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Hallucinated status, prompt injection, stale evidence, unauthorized artifact, chat interpreted as approval, secret leakage, and high cost.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's agent behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S2-F03, S4-F10
  - **Suggested labels:** sprint-4, s4-f11, product-capability, agent, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F11-I02 — Persist and expose evidence contracts for Explain authoritative migration state through the AI Assistant

  - **Parent feature:** S4-F11
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Explain authoritative migration state through the AI Assistant observable and auditable.
  - **Context:** The Assistant improves comprehension but remains read-only and subordinate to authoritative services.
  - **Scope:** Persistence: Conversation/message metadata, artifact refs, usage/cost; no hidden chain-of-thought.. API: POST /api/v1/runs/{id}/assistant/messages; GET /api/v1/runs/{id}/assistant/messages. Events: ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED.. Artifacts: Sanitized assistant input manifest, structured answer, evidence citations, and usage record.
  - **Out of scope:** Direct command/file tools, silent approval, raw secret exposure, unrestricted filesystem search, and autonomous workflow changes.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Conversation/message metadata, artifact refs, usage/cost; no hidden chain-of-thought.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/assistant/messages; GET /api/v1/runs/{id}/assistant/messages; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Sanitized assistant input manifest, structured answer, evidence citations, and usage record.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F11-I01
  - **Suggested labels:** sprint-4, s4-f11, product-capability, api, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F11-I03 — Build frontend experience for Explain authoritative migration state through the AI Assistant

  - **Parent feature:** S4-F11
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Explain authoritative migration state through the AI Assistant, using backend snapshots and durable events only.
  - **Context:** The Assistant improves comprehension but remains read-only and subordinate to authoritative services.
  - **Scope:** Chat panel with suggested questions, evidence links, proof labels, streaming/progress, empty/error/budget-blocked states, and disabled mutation/approval actions.
  - **Out of scope:** Direct command/file tools, silent approval, raw secret exposure, unrestricted filesystem search, and autonomous workflow changes.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/assistant/messages; GET /api/v1/runs/{id}/assistant/messages` plus durable events `ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Chat panel with suggested questions, evidence links, proof labels, streaming/progress, empty/error/budget-blocked states, and disabled mutation/approval actions.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/assistant/messages; GET /api/v1/runs/{id}/assistant/messages` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Sanitized assistant input manifest, structured answer, evidence citations, and usage record.
  - **UI impact:** Implement: Chat panel with suggested questions, evidence links, proof labels, streaming/progress, empty/error/budget-blocked states, and disabled mutation/approval actions.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F11-I02
  - **Suggested labels:** sprint-4, s4-f11, product-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S4-F11-I04 — Verify and document Explain authoritative migration state through the AI Assistant

  - **Parent feature:** S4-F11
  - **Issue type:** Testing
  - **Technical story:** Prove Explain authoritative migration state through the AI Assistant through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** The Assistant improves comprehension but remains read-only and subordinate to authoritative services.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Direct command/file tools, silent approval, raw secret exposure, unrestricted filesystem search, and autonomous workflow changes.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/assistant/messages; GET /api/v1/runs/{id}/assistant/messages` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Sanitized assistant input manifest, structured answer, evidence citations, and usage record.` where applicable.
  - **UI impact:** Execute the feature through `Chat panel with suggested questions, evidence links, proof labels, streaming/progress, empty/error/budget-blocked states, and disabled mutation/approval actions.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Hallucinated status, prompt injection, stale evidence, unauthorized artifact, chat interpreted as approval, secret leakage, and high cost.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F11-I03
  - **Suggested labels:** sprint-4, s4-f11, product-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### S4-F12 — Run independent final assurance and decide G13

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Approval capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G13

#### User-observable outcome

A reviewer can create a fresh final-assurance sandbox, run exact clean install/version/build/tests/conditional checks, inspect independent assurance dimensions and source integrity, then decide G13.

#### Context

Stage-local success is insufficient for delivery; the final candidate must be proven in a clean independent workspace.

**Governing specification sections:** 24, 43-44, 56.14, 63.11

#### Scope

Independent final clean validation, source integrity, honest assurance, G13, and UI.

#### Out of scope

Automated browser/visual tooling, external security/quality tools, delivery publication, and report acceptance.

#### Backend slice

- **Application service/components:** FinalAssuranceService, WorkspaceManager final sandbox, exact frozen profile/plan, clean install/version/build/test/conditional checks, route/backend comparison, source integrity verification, assurance aggregation, and G13 package.
- **Domain aggregate/projection:** FinalAssuranceRun, AssuranceStatus, ApprovalGate G13.
- **Persistence:** Final assurance metadata/results, source integrity status, gate/decisions, artifacts/events.
- **State/approval rule:** G13 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions`
- **Durable event:** FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.
- **Artifact Store output:** Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Final assurance page with clean-workspace evidence, gate matrix, independent technical/parity/security/quality/delivery cards, manual/deferred items, source integrity, and G13 controls.
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
→ FinalAssuranceService, WorkspaceManager final sandbox, exact frozen profile/plan, clean install/version/build/test/conditional checks, route/backend comparison, source integrity verification, assurance aggregation, and G13 package.
→ Final assurance metadata/results, source integrity status, gate/decisions, artifacts/events.
→ ArtifactService finalizes evidence: Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.
→ Transition/Event service persists and emits: FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.
→ SSE replay or snapshot refresh
→ Final assurance page with clean-workspace evidence, gate matrix, independent technical/parity/security/quality/delivery cards, manual/deferred items, source integrity, and G13 controls.
```

#### Sub-issues

- `S4-F12-I01` — Backend/application contract
- `S4-F12-I02` — Persistence, API, durable event, and artifact contract
- `S4-F12-I03` — Frontend projection and interaction
- `S4-F12-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Run independent final assurance and decide G13**, then the backend performs only the authorized service operation, persists the result, emits **FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Final assurance metadata/results, source integrity status, gate/decisions, artifacts/events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G13 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G13 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.

#### Manual end-to-end test scenario

**Preconditions:** S3-F14, S4-F08, S4-F10; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Final assurance page with clean-workspace evidence, gate matrix, independent technical/parity/security/quality/delivery cards, manual/deferred items, source integrity, and G13 controls.**.
    3. Trigger the primary action for **Run independent final assurance and decide G13** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G13** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can create a fresh final-assurance sandbox, run exact clean install/version/build/tests/conditional checks, inspect independent assurance dimensions and source integrity, then decide G13. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `Final assurance metadata/results, source integrity status, gate/decisions, artifacts/events.` are retrievable through `POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.

    **Expected durable event:** FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G13 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

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

S3-F14, S4-F08, S4-F10

#### Risks and edge cases

- Reusing stage node_modules
- final profile drift
- incomplete project matrix
- manual status shown as pass
- source changed since snapshot
- and final gate bypass.

#### Detailed sub-issues

#### S4-F12-I01 — Implement backend application contract for Run independent final assurance and decide G13

  - **Parent feature:** S4-F12
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Run independent final assurance and decide G13 so the feature has one authoritative service path.
  - **Context:** Stage-local success is insufficient for delivery; the final candidate must be proven in a clean independent workspace.
  - **Scope:** FinalAssuranceService, WorkspaceManager final sandbox, exact frozen profile/plan, clean install/version/build/test/conditional checks, route/backend comparison, source integrity verification, assurance aggregation, and G13 package.
  - **Out of scope:** Automated browser/visual tooling, external security/quality tools, delivery publication, and report acceptance.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G13 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: FinalAssuranceService, WorkspaceManager final sandbox, exact frozen profile/plan, clean install/version/build/test/conditional checks, route/backend comparison, source integrity verification, assurance aggregation, and G13 package.
  - **Database impact:** Use or introduce the records summarized by: Final assurance metadata/results, source integrity status, gate/decisions, artifacts/events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions
  - **Event impact:** Request durable events only through the transition/event service: FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Reusing stage node_modules, final profile drift, incomplete project matrix, manual status shown as pass, source changed since snapshot, and final gate bypass.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G13 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S3-F14, S4-F08, S4-F10
  - **Suggested labels:** sprint-4, s4-f12, approval-capability, backend, g13, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F12-I02 — Persist and expose evidence contracts for Run independent final assurance and decide G13

  - **Parent feature:** S4-F12
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Run independent final assurance and decide G13 observable and auditable.
  - **Context:** Stage-local success is insufficient for delivery; the final candidate must be proven in a clean independent workspace.
  - **Scope:** Persistence: Final assurance metadata/results, source integrity status, gate/decisions, artifacts/events.. API: POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions. Events: FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.. Artifacts: Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.
  - **Out of scope:** Automated browser/visual tooling, external security/quality tools, delivery publication, and report acceptance.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Final assurance metadata/results, source integrity status, gate/decisions, artifacts/events.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G13 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F12-I01
  - **Suggested labels:** sprint-4, s4-f12, approval-capability, api, g13, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F12-I03 — Build frontend experience for Run independent final assurance and decide G13

  - **Parent feature:** S4-F12
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Run independent final assurance and decide G13, using backend snapshots and durable events only.
  - **Context:** Stage-local success is insufficient for delivery; the final candidate must be proven in a clean independent workspace.
  - **Scope:** Final assurance page with clean-workspace evidence, gate matrix, independent technical/parity/security/quality/delivery cards, manual/deferred items, source integrity, and G13 controls.
  - **Out of scope:** Automated browser/visual tooling, external security/quality tools, delivery publication, and report acceptance.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions` plus durable events `FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Final assurance page with clean-workspace evidence, gate matrix, independent technical/parity/security/quality/delivery cards, manual/deferred items, source integrity, and G13 controls.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.
  - **UI impact:** Implement: Final assurance page with clean-workspace evidence, gate matrix, independent technical/parity/security/quality/delivery cards, manual/deferred items, source integrity, and G13 controls.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G13 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F12-I02
  - **Suggested labels:** sprint-4, s4-f12, approval-capability, frontend, g13, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F12-I04 — Verify and document Run independent final assurance and decide G13

  - **Parent feature:** S4-F12
  - **Issue type:** Testing
  - **Technical story:** Prove Run independent final assurance and decide G13 through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Stage-local success is insufficient for delivery; the final candidate must be proven in a clean independent workspace.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Automated browser/visual tooling, external security/quality tools, delivery publication, and report acceptance.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/final-assurance; GET /api/v1/runs/{id}/final-assurance; POST /api/v1/runs/{id}/approvals/G13/decisions` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED and G13 events.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Final workspace manifest/fingerprint, clean install/build/test logs, exact version inventory, route/backend comparisons, source integrity proof, assurance summary, G13 package.` where applicable.
  - **UI impact:** Execute the feature through `Final assurance page with clean-workspace evidence, gate matrix, independent technical/parity/security/quality/delivery cards, manual/deferred items, source integrity, and G13 controls.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Reusing stage node_modules, final profile drift, incomplete project matrix, manual status shown as pass, source changed since snapshot, and final gate bypass.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G13 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F12-I03
  - **Suggested labels:** sprint-4, s4-f12, approval-capability, testing, g13, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---


### S4-F13 — Create a delivery candidate and publish atomically through G14

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Approval capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G14

#### User-observable outcome

A reviewer can inspect the exact generated output root, clean delivery manifest/fingerprint, original-source integrity proof, and destination safety, decide G14, and publish `<resolved-output-root>/migrated-app` atomically or fail closed without exposing a partial final directory.

#### Context

Final output appears only under the generated external output root and only from the approved final fingerprint after independent verification, unchanged-original-source proof, destination revalidation, and human delivery authority.

**Governing specification sections:** 33-35, 53.9, 56.15, 68.10, 70.10

#### Scope

Candidate copied from the approved final stage workspace, manifest/fingerprint, source-integrity recheck, generated-output destination safety, G14, atomic/fail-closed publication to `migrated-app/`, and UI.

#### Out of scope

Cloud deployment, Git push/PR, backend migration, and publishing before final assurance.

#### Backend slice

- **Application service/components:** DeliveryService for candidate copy from the approved final stage workspace, exclusions, manifest/fingerprint, original-source fingerprint revalidation, target-parent/output-root containment revalidation, managed-output and overwrite policy, G14 package, idempotent publication to the exact registered `migrated-app` alias, same-volume atomic rename or two-phase fail-closed fallback, and source/snapshot/final binding.
- **Domain aggregate/projection:** DeliveryRecord, ApprovalGate G14.
- **Persistence:** delivery_records, target-parent/generated-output/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.
- **State/approval rule:** G14 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish`
- **Durable event:** DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.
- **Artifact Store output:** Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, generated-output destination safety report, managed-output ownership report, G14 package, and publication record.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Delivery review page with target parent, generated output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.
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
→ DeliveryService for candidate copy from the approved final stage workspace, exclusions, manifest/fingerprint, original-source fingerprint revalidation, target-parent/output-root containment revalidation, managed-output and overwrite policy, G14 package, idempotent publication to the exact registered `migrated-app` alias, same-volume atomic rename or two-phase fail-closed fallback, and source/snapshot/final binding.
→ delivery_records, target-parent/generated-output/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.
→ ArtifactService finalizes evidence: Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, generated-output destination safety report, managed-output ownership report, G14 package, and publication record.
→ Transition/Event service persists and emits: DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.
→ SSE replay or snapshot refresh
→ Delivery review page with target parent, generated output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.
```

#### Sub-issues

- `S4-F13-I01` — Backend/application contract
- `S4-F13-I02` — Persistence, API, durable event, and artifact contract
- `S4-F13-I03` — Frontend projection and interaction
- `S4-F13-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Create a delivery candidate and publish atomically through G14**, then the backend performs only the authorized service operation, persists the result, emits **DELIVERY_CANDIDATE_READY,**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **delivery_records, target-parent/generated-output/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, generated-output destination safety report, managed-output ownership report, G14 package, and publication record.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G14 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G14 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.
- **Repository/source isolation:** Given publication starts, when all paths are revalidated, then the external source and platform repository are read-only/out-of-scope and only registered product-owned candidate and destination aliases may be touched.
- **Destination contract:** Given publication succeeds, when the generated output root is inspected, then `migrated-app/` exactly matches the approved candidate fingerprint and no temporary or partial final directory is presented as successful.
- **Source integrity:** Given the original source fingerprint differs from the G02-approved boundary, when G14 or publication is attempted, then delivery is blocked and the changed source is reported without mutation.

#### Manual end-to-end test scenario

**Preconditions:** S4-F12; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Delivery review page with target parent, generated output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.**.
    3. Trigger the primary action for **Create a delivery candidate and publish atomically through G14** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G14** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can inspect the exact generated output root, clean delivery manifest/fingerprint, original-source integrity proof, and destination safety, decide G14, and publish `<resolved-output-root>/migrated-app` atomically or fail closed without exposing a partial final directory. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `delivery_records, target-parent/generated-output/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.` are retrievable through `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, generated-output destination safety report, managed-output ownership report, G14 package, and publication record.

    **Expected durable event:** DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G14 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

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

S4-F12

#### Risks and edge cases

- Cross-volume rename or an unavailable atomic-rename boundary
- Target parent or generated output root changed after G14 evidence creation
- Existing unmanaged `migrated-app/` or ownership ambiguity
- Original external source changed after G02
- Partial copy, disk exhaustion, or file locks during two-phase fallback
- Reparse-point or containment escape into the source or platform repository
- Duplicate publication or conflicting idempotency payload

#### Detailed sub-issues

#### S4-F13-I01 — Implement backend application contract for Create a delivery candidate and publish atomically through G14

  - **Parent feature:** S4-F13
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Create a delivery candidate and publish atomically through G14 so the feature has one authoritative service path.
  - **Context:** Final output appears only under the generated external output root and only from the approved final fingerprint after independent verification, unchanged-original-source proof, destination revalidation, and human delivery authority.
  - **Scope:** DeliveryService for candidate copy from the approved final stage workspace, exclusions, manifest/fingerprint, original-source fingerprint revalidation, target-parent/output-root containment revalidation, managed-output and overwrite policy, G14 package, idempotent publication to the exact registered `migrated-app` alias, same-volume atomic rename or two-phase fail-closed fallback, and source/snapshot/final binding.
  - **Out of scope:** Cloud deployment, Git push/PR, backend migration, and publishing before final assurance.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G14 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: DeliveryService for candidate copy from the approved final stage workspace, exclusions, manifest/fingerprint, original-source fingerprint revalidation, target-parent/output-root containment revalidation, managed-output and overwrite policy, G14 package, idempotent publication to the exact registered `migrated-app` alias, same-volume atomic rename or two-phase fail-closed fallback, and source/snapshot/final binding.
  - **Database impact:** Use or introduce the records summarized by: delivery_records, target-parent/generated-output/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish
  - **Event impact:** Request durable events only through the transition/event service: DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, generated-output destination safety report, managed-output ownership report, G14 package, and publication record.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Cross-volume rename, target parent or generated output changed after approval, existing unmanaged `migrated-app`, partial copy, disk exhaustion, file locks, platform-repository/source path escape, changed original source, and duplicate publication.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G14 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F12
  - **Suggested labels:** sprint-4, s4-f13, approval-capability, backend, g14, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F13-I02 — Persist and expose evidence contracts for Create a delivery candidate and publish atomically through G14

  - **Parent feature:** S4-F13
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Create a delivery candidate and publish atomically through G14 observable and auditable.
  - **Context:** Final output appears only under the generated external output root and only from the approved final fingerprint after independent verification, unchanged-original-source proof, destination revalidation, and human delivery authority.
  - **Scope:** Persistence: delivery_records, target-parent/generated-output/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.. API: POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish. Events: DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.. Artifacts: Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, generated-output destination safety report, managed-output ownership report, G14 package, and publication record.
  - **Out of scope:** Cloud deployment, Git push/PR, backend migration, and publishing before final assurance.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: delivery_records, target-parent/generated-output/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, generated-output destination safety report, managed-output ownership report, G14 package, and publication record.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G14 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F13-I01
  - **Suggested labels:** sprint-4, s4-f13, approval-capability, api, g14, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F13-I03 — Build frontend experience for Create a delivery candidate and publish atomically through G14

  - **Parent feature:** S4-F13
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Create a delivery candidate and publish atomically through G14, using backend snapshots and durable events only.
  - **Context:** Final output appears only under the generated external output root and only from the approved final fingerprint after independent verification, unchanged-original-source proof, destination revalidation, and human delivery authority.
  - **Scope:** Delivery review page with target parent, generated output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.
  - **Out of scope:** Cloud deployment, Git push/PR, backend migration, and publishing before final assurance.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish` plus durable events `DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Delivery review page with target parent, generated output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, generated-output destination safety report, managed-output ownership report, G14 package, and publication record.
  - **UI impact:** Implement: Delivery review page with target parent, generated output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G14 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F13-I02
  - **Suggested labels:** sprint-4, s4-f13, approval-capability, frontend, g14, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F13-I04 — Verify and document Create a delivery candidate and publish atomically through G14

  - **Parent feature:** S4-F13
  - **Issue type:** Testing
  - **Technical story:** Prove Create a delivery candidate and publish atomically through G14 through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** Final output appears only under the generated external output root and only from the approved final fingerprint after independent verification, unchanged-original-source proof, destination revalidation, and human delivery authority.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Cloud deployment, Git push/PR, backend migration, and publishing before final assurance.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, generated-output destination safety report, managed-output ownership report, G14 package, and publication record.` where applicable.
  - **UI impact:** Execute the feature through `Delivery review page with target parent, generated output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Cross-volume rename, target parent or generated output changed after approval, existing unmanaged `migrated-app`, partial copy, disk exhaustion, file locks, platform-repository/source path escape, changed original source, and duplicate publication.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G14 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F13-I03
  - **Suggested labels:** sprint-4, s4-f13, approval-capability, testing, g14, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---


### S4-F14 — Generate the deterministic evidence report, optional AI narrative, and decide G15

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Reporting capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G15

#### User-observable outcome

A lead can view/download a complete report covering stages, approvals, commands, failures, repairs, source integrity, delivery, proof labels, manual/deferred items, and input/output/total token costs, then decide G15.

#### Context

The report is an evidence index and honest assurance summary, not a narrative that invents unexecuted success.

**Governing specification sections:** 39, 44, 47-50, 52.7, 56.16, 72

#### Scope

Complete evidence/cost report, optional narrative only over facts, proof validation, viewer/download, G15, and run completion.

#### Out of scope

PDF unless separately approved, hidden chain-of-thought, cached/reasoning token metrics, and claiming external scans passed.

#### Backend slice

- **Application service/components:** ReportService and optional ReportAgent constrained to authoritative facts, report schema/proof-label validator, artifact index builder, token/cost aggregator, manual/deferred status validator, G15 package, and immutable report generation.
- **Domain aggregate/projection:** FinalReport, UsageCostSummary, ApprovalGate G15.
- **Persistence:** Report metadata/version/checksum, aggregate usage/cost, gate decisions, completion transition.
- **State/approval rule:** G15 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions`
- **Durable event:** REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.
- **Artifact Store output:** Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Markdown report viewer with navigation, proof badges, approval timeline, artifact links, usage/cost table, unresolved items, download, and G15 controls.
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
→ ReportService and optional ReportAgent constrained to authoritative facts, report schema/proof-label validator, artifact index builder, token/cost aggregator, manual/deferred status validator, G15 package, and immutable report generation.
→ Report metadata/version/checksum, aggregate usage/cost, gate decisions, completion transition.
→ ArtifactService finalizes evidence: Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.
→ Transition/Event service persists and emits: REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.
→ SSE replay or snapshot refresh
→ Markdown report viewer with navigation, proof badges, approval timeline, artifact links, usage/cost table, unresolved items, download, and G15 controls.
```

#### Deterministic report truth and optional narrative

`ReportService` deterministically generates every authoritative field: states, stages, commands, approvals, artifacts, failures, repairs, source-integrity evidence, assurance statuses, delivery evidence, proof labels, manual/deferred items, token usage, and estimated cost.

The optional `report_narrator` role may generate an executive summary, stage narrative, risk explanation, and chronology over the immutable report facts. It cannot change machine-generated fields. If Azure is unavailable, a deterministic narrative template is used, the report is labelled as not LLM-narrated, and G15 may still proceed.

All locally calculated prices are displayed as **estimated cost using the project pricing snapshot**, never as the Azure invoice.

#### Sub-issues

- `S4-F14-I01` — Backend/application contract
- `S4-F14-I02` — Persistence, API, durable event, and artifact contract
- `S4-F14-I03` — Frontend projection and interaction
- `S4-F14-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Generate, view, download, and accept the final evidence and cost report through G15**, then the backend performs only the authorized service operation, persists the result, emits **REPORT_GENERATION_STARTED/READY/FAILED,**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Report metadata/version/checksum, aggregate usage/cost, gate decisions, completion transition.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G15 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G15 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.

#### Manual end-to-end test scenario

**Preconditions:** S4-F11, S4-F13; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Markdown report viewer with navigation, proof badges, approval timeline, artifact links, usage/cost table, unresolved items, download, and G15 controls.**.
    3. Trigger the primary action for **Generate, view, download, and accept the final evidence and cost report through G15** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G15** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A lead can view/download a complete report covering stages, approvals, commands, failures, repairs, source integrity, delivery, proof labels, manual/deferred items, and input/output/total token costs, then decide G15. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `Report metadata/version/checksum, aggregate usage/cost, gate decisions, completion transition.` are retrievable through `POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.

    **Expected durable event:** REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.

    **Negative test:** Repeat with an invalid path/input, stale state version, missing prerequisite/approval, tampered checksum, or simulated backend/provider/process failure appropriate to the feature. Confirm no unauthorized mutation or progression occurs.
- **Expected approval record:** append-only G15 decision bound to the active checksum/version/fingerprint; stale replay does not advance state.

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

S4-F11, S4-F13

#### Risks and edge cases

- Missing artifact
- report overclaim
- cost rounding/config mismatch
- broken links
- sensitive logs exposed
- stale delivery data
- and accepting incomplete report.

#### Detailed sub-issues

#### S4-F14-I01 — Implement backend application contract for Generate, view, download, and accept the final evidence and cost report through G15

  - **Parent feature:** S4-F14
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Generate, view, download, and accept the final evidence and cost report through G15 so the feature has one authoritative service path.
  - **Context:** The report is an evidence index and honest assurance summary, not a narrative that invents unexecuted success.
  - **Scope:** ReportService and optional ReportAgent constrained to authoritative facts, report schema/proof-label validator, artifact index builder, token/cost aggregator, manual/deferred status validator, G15 package, and immutable report generation.
  - **Out of scope:** PDF unless separately approved, hidden chain-of-thought, cached/reasoning token metrics, and claiming external scans passed.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. G15 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: ReportService and optional ReportAgent constrained to authoritative facts, report schema/proof-label validator, artifact index builder, token/cost aggregator, manual/deferred status validator, G15 package, and immutable report generation.
  - **Database impact:** Use or introduce the records summarized by: Report metadata/version/checksum, aggregate usage/cost, gate decisions, completion transition.
  - **API impact:** Define service-facing request/response models supporting: POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions
  - **Event impact:** Request durable events only through the transition/event service: REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Missing artifact, report overclaim, cost rounding/config mismatch, broken links, sensitive logs exposed, stale delivery data, and accepting incomplete report.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G15 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F11, S4-F13
  - **Suggested labels:** sprint-4, s4-f14, reporting-capability, backend, g15, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F14-I02 — Persist and expose evidence contracts for Generate, view, download, and accept the final evidence and cost report through G15

  - **Parent feature:** S4-F14
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Generate, view, download, and accept the final evidence and cost report through G15 observable and auditable.
  - **Context:** The report is an evidence index and honest assurance summary, not a narrative that invents unexecuted success.
  - **Scope:** Persistence: Report metadata/version/checksum, aggregate usage/cost, gate decisions, completion transition.. API: POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions. Events: REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.. Artifacts: Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.
  - **Out of scope:** PDF unless separately approved, hidden chain-of-thought, cached/reasoning token metrics, and claiming external scans passed.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Report metadata/version/checksum, aggregate usage/cost, gate decisions, completion transition.
  - **API impact:** Implement and document: POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.
  - **UI impact:** Expose all IDs/statuses needed by the frontend; do not expose unsafe absolute paths or secrets.
  - **Security considerations:** Validate artifact containment and checksum, prevent silent overwrite and approval replay, sanitize response fields, and authorize actor/run access.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's api behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
- Given/When/Then: Given G15 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
  - **Automated tests:** Repository and API integration tests with temporary SQLite/WAL and Artifact Store; transaction rollback, checksum mismatch, missing file, duplicate idempotency, stale version, and event-after-commit tests.
  - **Manual verification contribution:** Provides the API, persisted evidence, and event that the UI will display during the feature demonstration.
  - **Dependencies:** S4-F14-I01
  - **Suggested labels:** sprint-4, s4-f14, reporting-capability, api, g15, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F14-I03 — Build frontend experience for Generate, view, download, and accept the final evidence and cost report through G15

  - **Parent feature:** S4-F14
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Generate, view, download, and accept the final evidence and cost report through G15, using backend snapshots and durable events only.
  - **Context:** The report is an evidence index and honest assurance summary, not a narrative that invents unexecuted success.
  - **Scope:** Markdown report viewer with navigation, proof badges, approval timeline, artifact links, usage/cost table, unresolved items, download, and G15 controls.
  - **Out of scope:** PDF unless separately approved, hidden chain-of-thought, cached/reasoning token metrics, and claiming external scans passed.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions` plus durable events `REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Markdown report viewer with navigation, proof badges, approval timeline, artifact links, usage/cost table, unresolved items, download, and G15 controls.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.
  - **UI impact:** Implement: Markdown report viewer with navigation, proof badges, approval timeline, artifact links, usage/cost table, unresolved items, download, and G15 controls.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G15 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F14-I02
  - **Suggested labels:** sprint-4, s4-f14, reporting-capability, frontend, g15, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Low

#### S4-F14-I04 — Verify and document Generate, view, download, and accept the final evidence and cost report through G15

  - **Parent feature:** S4-F14
  - **Issue type:** Testing
  - **Technical story:** Prove Generate, view, download, and accept the final evidence and cost report through G15 through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** The report is an evidence index and honest assurance summary, not a narrative that invents unexecuted success.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** PDF unless separately approved, hidden chain-of-thought, cached/reasoning token metrics, and claiming external scans passed.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `POST /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report; GET /api/v1/runs/{id}/report/download; POST /api/v1/runs/{id}/approvals/G15/decisions` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `REPORT_GENERATION_STARTED/READY/FAILED, G15 events, RUN_COMPLETED after valid acceptance.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `Machine-readable report, Markdown/HTML report, artifact index, token-cost summary, unresolved/manual/deferred list, and G15 package.` where applicable.
  - **UI impact:** Execute the feature through `Markdown report viewer with navigation, proof badges, approval timeline, artifact links, usage/cost table, unresolved items, download, and G15 controls.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Missing artifact, report overclaim, cost rounding/config mismatch, broken links, sensitive logs exposed, stale delivery data, and accepting incomplete report.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given G15 is stale or unsatisfied, when protected progression is attempted, then the backend rejects it and the UI does not show the next phase as active.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F14-I03
  - **Suggested labels:** sprint-4, s4-f14, reporting-capability, testing, g15, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** Medium


---


### S4-F15 — Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Operational capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

The team can execute the final manual and automated runtime proof on Angular 18.0.x and 18.2.x workspaces generated under external temporary test roots, including all gates, one real repair, an environment blocker, cancellation, restart recovery, final assurance, generated-output publication, and unchanged external source.

#### Context

The MVP is complete only when the integrated controlled platform—not isolated services—proves the authoritative workflow.

**Governing specification sections:** 43-44, 71-72, 75

#### Scope

Representative fixtures, all automated seam tests, real subprocess/cancel/restart tests, real 18→21 passing path, controlled repair, security negative cases, and final demonstration.

#### Out of scope

Angular 11-17 production validation, Angular 22, unsupported topologies, browser automation, and enterprise scale.

#### Backend slice

- **Application service/components:** Fixture harness, real subprocess test profiles, deterministic failure fixtures, fake model integration suite plus one configured Azure path, end-to-end orchestration tests, security tests, and runtime evidence collector.
- **Domain aggregate/projection:** TestRun records are operational; the tested MigrationRun uses all production aggregates.
- **Persistence:** Test execution metadata and complete migration-run records/artifacts.
- **State/approval rule:** No new human gate is introduced by this feature; existing prerequisites remain enforced.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status`
- **Durable event:** Existing production events validated for completeness/order; acceptance-suite status events optional.
- **Artifact Store output:** External fixture-generation manifests, repository-isolation evidence, generated-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Operator acceptance checklist linking each scenario to live product pages/artifacts; no hidden API-only completion.
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
→ Fixture harness, real subprocess test profiles, deterministic failure fixtures, fake model integration suite plus one configured Azure path, end-to-end orchestration tests, security tests, and runtime evidence collector.
→ Test execution metadata and complete migration-run records/artifacts.
→ ArtifactService finalizes evidence: External fixture-generation manifests, repository-isolation evidence, generated-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
→ Transition/Event service persists and emits: Existing production events validated for completeness/order; acceptance-suite status events optional.
→ SSE replay or snapshot refresh
→ Operator acceptance checklist linking each scenario to live product pages/artifacts; no hidden API-only completion.
```

#### Sub-issues

- `S4-F15-I01` — Backend/application contract
- `S4-F15-I02` — Persistence, API, durable event, and artifact contract
- `S4-F15-I03` — Frontend projection and interaction
- `S4-F15-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart**, then the backend performs only the authorized service operation, persists the result, emits **Existing**-family durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Test execution metadata and complete migration-run records/artifacts.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **External fixture-generation manifests, repository-isolation evidence, generated-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.

#### Manual end-to-end test scenario

**Preconditions:** S4-F01, S4-F02, S4-F03, S2-F03, S4-F04, S4-F05, S4-F06, S4-F07, S4-F08, S4-F09, S4-F10, S4-F11, S4-F12, S4-F13, S4-F14; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

**Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

**UI steps:**
1. Launch the backend and frontend and open the relevant run or operator page.
2. Navigate to the surface described by **Operator acceptance checklist linking each scenario to live product pages/artifacts; no hidden API-only completion.**.
3. Trigger the primary action for **Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart** using valid fixture data.
4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
5. Open the resulting detail, event, and artifact views.

**Expected UI result:** The team can execute the final manual and automated runtime proof on Angular 18.0.x and 18.2.x workspaces generated under external temporary test roots, including all gates, one real repair, an environment blocker, cancellation, restart recovery, final assurance, generated-output publication, and unchanged external source. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Test execution metadata and complete migration-run records/artifacts.` are retrievable through `Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** External fixture-generation manifests, repository-isolation evidence, generated-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.

**Expected durable event:** Existing production events validated for completeness/order; acceptance-suite status events optional.

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

S4-F01, S4-F02, S4-F03, S2-F03, S4-F04, S4-F05, S4-F06, S4-F07, S4-F08, S4-F09, S4-F10, S4-F11, S4-F12, S4-F13, S4-F14

#### Risks and edge cases

- Fixture not representative
- external registry/model instability
- runtime duration
- corporate proxy variance
- flaky real tests
- and treating simulated proof as runtime proof.

#### Detailed sub-issues

#### S4-F15-I01 — Implement backend application contract for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

  - **Parent feature:** S4-F15
  - **Issue type:** Backend
  - **Technical story:** Implement the bounded backend/application behavior for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart so the feature has one authoritative service path.
  - **Context:** The MVP is complete only when the integrated controlled platform—not isolated services—proves the authoritative workflow.
  - **Scope:** Fixture harness, real subprocess test profiles, deterministic failure fixtures, fake model integration suite plus one configured Azure path, end-to-end orchestration tests, security tests, and runtime evidence collector.
  - **Out of scope:** Angular 11-17 production validation, Angular 22, unsupported topologies, browser automation, and enterprise scale.
  - **Implementation notes:** Keep domain rules outside route handlers and LangGraph nodes. Use repositories and the Transition Service for state changes. Model inputs/outputs with Pydantic v2. No new human gate is introduced by this feature; existing prerequisites remain enforced.
  - **Likely files/modules:** backend/app/domain, backend/app/services, backend/app/repositories, backend/app/models, and bounded orchestration/agent adapter modules only where named.
  - **Input contract:** Validated request identifiers, expected state version, idempotency key, prerequisite artifact IDs, and feature-specific data for `Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status`.
  - **Output contract:** Typed application result containing state version, result status, artifact references, and stable error codes; service behavior: Fixture harness, real subprocess test profiles, deterministic failure fixtures, fake model integration suite plus one configured Azure path, end-to-end orchestration tests, security tests, and runtime evidence collector.
  - **Database impact:** Use or introduce the records summarized by: Test execution metadata and complete migration-run records/artifacts.
  - **API impact:** Define service-facing request/response models supporting: Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status
  - **Event impact:** Request durable events only through the transition/event service: Existing production events validated for completeness/order; acceptance-suite status events optional.
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: External fixture-generation manifests, repository-isolation evidence, generated-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
  - **UI impact:** No UI implementation in this issue; return stable contracts required by the sibling frontend issue.
  - **Security considerations:** Enforce authority boundaries, input validation, state/version checks, path/workspace confinement, secret redaction, and the risk controls relevant to: Fixture not representative, external registry/model instability, runtime duration, corporate proxy variance, flaky real tests, and treating simulated proof as runtime proof.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's backend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the same idempotency key and identical payload are retried, when the request is repeated, then the original result is returned; a different payload with the same key is rejected.
  - **Automated tests:** Unit tests for happy path, invalid input, illegal/stale transition, idempotent retry, dependency failure, and policy bypass attempts using fake external adapters.
  - **Manual verification contribution:** Enables the UI path to call one authoritative application service and observe a legal result.
  - **Dependencies:** S4-F01, S4-F02, S4-F03, S2-F03, S4-F04, S4-F05, S4-F06, S4-F07, S4-F08, S4-F09, S4-F10, S4-F11, S4-F12, S4-F13, S4-F14
  - **Suggested labels:** sprint-4, s4-f15, operational-capability, backend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** High

#### S4-F15-I02 — Persist and expose evidence contracts for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

  - **Parent feature:** S4-F15
  - **Issue type:** API
  - **Technical story:** Add the persistence, API, artifact, and durable-event slice needed to make Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart observable and auditable.
  - **Context:** The MVP is complete only when the integrated controlled platform—not isolated services—proves the authoritative workflow.
  - **Scope:** Persistence: Test execution metadata and complete migration-run records/artifacts.. API: Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status. Events: Existing production events validated for completeness/order; acceptance-suite status events optional.. Artifacts: External fixture-generation manifests, repository-isolation evidence, generated-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
  - **Out of scope:** Angular 11-17 production validation, Angular 22, unsupported topologies, browser automation, and enterprise scale.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Test execution metadata and complete migration-run records/artifacts.
  - **API impact:** Implement and document: Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: Existing production events validated for completeness/order; acceptance-suite status events optional.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: External fixture-generation manifests, repository-isolation evidence, generated-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
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

#### S4-F15-I03 — Build frontend experience for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

  - **Parent feature:** S4-F15
  - **Issue type:** Frontend
  - **Technical story:** Create the React/Next.js projection and user interaction for Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart, using backend snapshots and durable events only.
  - **Context:** The MVP is complete only when the integrated controlled platform—not isolated services—proves the authoritative workflow.
  - **Scope:** Operator acceptance checklist linking each scenario to live product pages/artifacts; no hidden API-only completion.
  - **Out of scope:** Angular 11-17 production validation, Angular 22, unsupported topologies, browser automation, and enterprise scale.
  - **Implementation notes:** Use typed API clients and a run-scoped projection store. Render loading, empty, running, success, blocked, stale, reconnecting, and failure states. Never infer a workflow transition from button clicks or log text; refresh authoritative state after mutations.
  - **Likely files/modules:** frontend/src/app, frontend/src/components, frontend/src/lib/api, frontend/src/lib/sse, frontend/src/stores, CSS Modules, and component tests.
  - **Input contract:** Backend responses from `Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status` plus durable events `Existing production events validated for completeness/order; acceptance-suite status events optional.` and artifact metadata IDs.
  - **Output contract:** Accessible UI surface: Operator acceptance checklist linking each scenario to live product pages/artifacts; no hidden API-only completion.; user actions submit expected state version and idempotency key when mutating.
  - **Database impact:** None directly; frontend must never access SQLite or infer database truth.
  - **API impact:** Consume `Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status` with typed success/error handling and correlation-ID display.
  - **Event impact:** Apply `Existing production events validated for completeness/order; acceptance-suite status events optional.` only when sequence/state version is newer; reconnect or reload snapshot on gaps.
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: External fixture-generation manifests, repository-isolation evidence, generated-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
  - **UI impact:** Implement: Operator acceptance checklist linking each scenario to live product pages/artifacts; no hidden API-only completion.
  - **Security considerations:** Escape untrusted repository/log/model content, do not render secrets, do not accept raw authoritative diffs/paths, and protect destructive actions with explicit confirmation.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's frontend behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the browser refreshes or SSE reconnects, when the snapshot/events are reloaded, then the same authoritative state is displayed without duplicate action.
  - **Automated tests:** React component tests for all visual states, typed API mocks, stale conflict, SSE duplicate/gap/reconnect, accessibility labels, and action-disabled prerequisites.
  - **Manual verification contribution:** Provides the only supported human/operator demonstration path; no API-only acceptance.
  - **Dependencies:** S4-F15-I02
  - **Suggested labels:** sprint-4, s4-f15, operational-capability, frontend, mvp, vertical-slice
  - **Estimate:** M
  - **Risk level:** Medium

#### S4-F15-I04 — Verify and document Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

  - **Parent feature:** S4-F15
  - **Issue type:** Testing
  - **Technical story:** Prove Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart through automated seams, security negatives, and the documented UI manual scenario.
  - **Context:** The MVP is complete only when the integrated controlled platform—not isolated services—proves the authoritative workflow.
  - **Scope:** Backend unit tests, API integration tests, frontend component tests, SSE/event tests where relevant, source-safety/security tests, and feature documentation.
  - **Out of scope:** Angular 11-17 production validation, Angular 22, unsupported topologies, browser automation, and enterprise scale.
  - **Implementation notes:** Use FastAPI + temporary SQLite + temporary Artifact Store + fake external adapters as the primary seam. Generate all full Angular fixture workspaces under an external temporary test root and pass them through the production source-path API. Add real subprocess or fixture tests only when the feature owns execution. Record exact manual evidence and update architecture/API docs.
  - **Likely files/modules:** backend/tests, frontend tests, external fixture generators/manifests, temporary test-root helpers, docs/testing, docs/api, docs/architecture decisions, and sprint demonstration checklist.
  - **Input contract:** Feature acceptance criteria, representative valid and negative fixture data, fake adapter outcomes, and existing production API/UI.
  - **Output contract:** Passing automated suite, reproducible manual test record, captured evidence IDs, and updated traceability.
  - **Database impact:** Assert expected records/versions/idempotency and ensure tests isolate temporary databases.
  - **API impact:** Exercise `Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status` for happy, invalid, stale, missing-prerequisite/approval, and backend-failure cases.
  - **Event impact:** Assert ordering, replay, and payload of `Existing production events validated for completeness/order; acceptance-suite status events optional.` where applicable.
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `External fixture-generation manifests, repository-isolation evidence, generated-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.` where applicable.
  - **UI impact:** Execute the feature through `Operator acceptance checklist linking each scenario to live product pages/artifacts; no hidden API-only completion.` and record visible loading/empty/success/blocked/stale/failure behavior.
  - **Security considerations:** Include at least one security or integrity negative derived from: Fixture not representative, external registry/model instability, runtime duration, corporate proxy variance, flaky real tests, and treating simulated proof as runtime proof.
  - **Acceptance criteria:**
    - Given/When/Then: Given the parent feature prerequisites are satisfied, when this issue's testing behavior is exercised, then the bounded contract described in Scope is observable and no unrelated authority is introduced.
- Given/When/Then: Given invalid or unauthorized input, when the operation is attempted, then it fails with a stable reason and leaves authoritative state/evidence unchanged except for an auditable rejection where required.
- Given/When/Then: Given a downstream dependency fails, when the issue handles the failure, then partial evidence is preserved safely, the state remains legal, and the frontend contract can display the failure.
- Given/When/Then: Given the full manual scenario is executed, when database, artifact, event, and source-safety evidence are inspected, then they match the documented expected results.
  - **Automated tests:** Automated tests named by behavior; no vague 'works' assertions. Include regression for architecture authority and cleanup of product-owned test data.
  - **Manual verification contribution:** Runs the complete feature manual scenario and contributes screenshots/artifact IDs/event IDs to the sprint evidence package.
  - **Dependencies:** S4-F15-I03
  - **Suggested labels:** sprint-4, s4-f15, operational-capability, testing, mvp, vertical-slice
  - **Estimate:** S
  - **Risk level:** High


---


### D.4.5 Sprint integration tests

- Parser and C-Lite route suite for code, dependency, environment, external retry, and unknown cases.

- Fake Proposer/Reviewer contract tests plus configured Azure structured-output integration.

- Patch checksum/fingerprint/path/applicability/idempotency and rollback/reconstruction security tests.

- Startup command/lease/artifact/graph reconciliation and waiting-approval restart tests.

- Final assurance, atomic publication failure, report-proof-label, cost aggregation, and full end-to-end runtime tests.


### D.4.6 Sprint manual demonstration

Trigger a real migration failure; inspect/classify evidence; build context; run Proposer and Reviewer with one revision; approve G10; apply exact diff; preflight and normal validation; approve G11; reject stale proposal; show environment blocker without patch; show no-progress protection; complete 18→21; approve final assurance/delivery/report; publish atomically; verify source unchanged.


#### Demonstration checklist

1. Trigger a real migration failure.

2. Inspect/classify evidence.

3. Build context.

4. Run Proposer and Reviewer with one revision.

5. Approve G10.

6. Apply exact diff.

7. Preflight and normal validation.

8. Approve G11.

9. Reject stale proposal.

10. Show environment blocker without patch.

11. Show no-progress protection.

12. Complete 18→21.

13. Approve final assurance/delivery/report.

14. Publish atomically.

15. Verify source unchanged..


### D.4.7 Sprint exit criteria

- G10, G11, G13, G14, and G15 are implemented and manually proven.

- Only Proposer authors diffs; Reviewer schema cannot contain one.

- Backend applies only the exact persisted human-approved patch.

- Repair returns to the same normal validation pipeline and stops no-progress loops.

- Final assurance runs clean and independently.

- Atomic/fail-closed publication and complete evidence/cost report succeed.

- Angular 18.0.x and 18.2.x fixtures prove the approved 21.x target route with unchanged source.


### D.4.8 Risks carried into the next sprint

Only explicitly deferred post-MVP scope remains: older Angular family fixture validation, additional package managers/topologies, enterprise scaling/RBAC, stronger isolation, approved browser/security/quality tooling, and modernization workflows.


### Sprint 4 integration tests

- Failure parser and C-Lite routing tests covering code/config, dependency, environment/user action, retryable external, and unknown routes.
- Full repair-chain tests with fake model clients: context checksum, Proposer diff, Reviewer no-diff schema, checksum mismatch, revision/context limits, Azure fallback eligibility, model outage fail-closed, stale proposal, path escape, duplicate patch, no progress, rollback, and exact persisted Apply.
- Startup reconciliation and safe-boundary recovery tests for interrupted commands, stale leases, missing/tampered artifacts, and stale graph checkpoints.
- Assistant tests for bounded history, evidence references, `store=false`, read-only deterministic fallback, and approval-intent handoff.
- Final assurance, atomic publication, deterministic-report, optional-narrative fallback, proof-label, estimated-cost, and G13–G15 tests.
- Real subprocess tests and separately gated live Azure tests; normal automated tests use fake clients.

### Sprint 4 manual demonstration

1. Produce a real Angular/TypeScript migration failure.
2. Inspect FailureEvidence and deterministic C-Lite classification.
3. Build the sanitized RepairContextPack.
4. Run Repair Proposer and Reviewer with one bounded revision.
5. Inspect complete checksum lineage and approve G10.
6. Apply the exact persisted diff, run patch preflight, resume normal validation, and approve G11.
7. Demonstrate stale proposal rejection, environment failure without a source patch, and no-progress protection.
8. Demonstrate cancellation and backend restart recovery.
9. Complete all three migration stages.
10. Ask the AI Assistant an evidence-grounded question and demonstrate labelled deterministic fallback.
11. Run final assurance and approve G13.
12. Create and atomically publish the delivery candidate through G14.
13. Generate the deterministic evidence/cost report, optionally add AI narrative, and approve G15.
14. Verify the original source fingerprint is unchanged.

### Sprint 4 exit criteria

- Repair is fully checksum-bound, human-gated, exact, and revalidated through the normal pipeline.
- Approval-sensitive model outages fail closed; Assistant and report narrative use clearly labelled low-authority deterministic fallback only.
- Recovery uses proven boundaries and never invents evidence.
- Final assurance is independent, delivery is atomic/fail-closed, and the report is complete without relying on an LLM.
- The real Angular 18.x→19.x→20.x→21.x fixture proof passes with repair, cancellation, restart, and source-integrity evidence.

# E. Approval-gate traceability matrix

| Gate | Sprint | Feature | Evidence and binding | Manual proof |
|---|---:|---|---|---|
| G01 Source/path acceptance | 1 | S1-F05 | Preflight checksum, state version, path/environment/source-analysis artifacts | Approve valid source; old decision is stale after input change |
| G02 Snapshot acceptance | 1 | S1-F08 | Source manifest, snapshot fingerprint, source-integrity result | Approve snapshot; tamper/change invalidates gate |
| G03 Baseline acceptance | 1 | S1-F14 | Exact ExecutionProfile, install/build/test/lint, known failures, parity anchors | Clean or qualified baseline accepted; failed mandatory build cannot become passed |
| G04 Analysis acceptance | 2 | S2-F04 | Deterministic analysis checksum, phase Proposer/Reviewer outputs and checksums | Review one revision and approve final reviewed artifact |
| G05 Feasibility acceptance | 2 | S2-F05 | Catalogue version, route, support level, exact Stage 1 profile | Approve feasible route; blocked route cannot proceed |
| G06 Plan acceptance | 2 | S2-F07 | Immutable plan/checksum, Planning review chain, policy/runtime versions | Modify plan, create new version, approve current version only |
| G07 Stage start | 3 | Stage-start feature | Input fingerprint, exact StageExecutionPlan, runtime and sandbox target | Approve each major stage before mutation |
| G08 Transformation acceptance | 3 | Transformation-diff feature | Exact command evidence, package/lockfile/source diff, risk scan | Review and approve exact official update result |
| G09 Validation acceptance | 3 | Stage-validation features | Install, exact version, static, build, tests, lint, route/backend comparisons | Failed core gate remains failed |
| G10 Repair Apply/Reject | 4 | S4-F06 | Full failure/context/proposer/diff/reviewer/policy lineage | Apply exact persisted diff or reject; stale proposal blocked |
| G11 Repair validation acceptance | 4 | S4-F08 | Patch ledger, post-apply fingerprint, normal-pipeline evidence | Approve successful revalidation or inspect fresh failure |
| G12 Stage completion | 3 | Stage-sealing feature | Cleanup, cleanliness, output fingerprint, artifact index | Seal stage and permit copy-forward |
| G13 Final assurance | 4 | S4-F12 | Independent clean sandbox install/build/tests/parity/source integrity | Approve independent final evidence |
| G14 Delivery acceptance | 4 | S4-F13 | Candidate manifest/fingerprint, destination safety, publication plan | Approve atomic/fail-closed publication |
| G15 Final report acceptance | 4 | S4-F14 | Deterministic report checksum, artifact index, proof labels, estimated cost | Accept report even if optional AI narrative used deterministic fallback |

# F. Architecture traceability matrix

| Component | Sprint/feature | Completion proof |
|---|---|---|
| LangGraph adapter | Sprint 0 + S1-F01/S1-F06; stage and repair subgraphs in 3/4 | Nodes call services, reconcile with SQLite, and cannot execute commands or write state directly |
| Transition Service | Sprint 0 + S1-F01 | Legal transition, optimistic version, idempotency, event atomicity tests |
| SQLite/WAL | Sprint 0 + S1-F01/S1-F02 | Same-host WAL diagnostics and authoritative state persistence |
| Artifact Store | Sprint 0, used by every feature | Atomic finalization, SHA-256, immutable ID access, reconciliation |
| Approval Service | Sprint 0 foundation; G01–G15 across 1–4 | State/artifact/plan/fingerprint-bound decisions and stale prevention |
| JobSupervisor/leases | Sprint 0; exercised 1/3/4 | One active run, command ownership, cancellation, startup recovery |
| ExternalSource/PathPolicy | S1-F03–F08 | External source and target-parent intake, generated output reservation, platform-repository isolation, read-only source fingerprinting |
| WorkspaceManager | Sprint 0 skeleton; S1-F06/F07/F10, Sprint 3 stages, S4 final sandbox | Run root under reserved output, source snapshot, baseline/stage isolation, typed workspace aliases, copy-forward, quarantine |
| Compatibility Resolver/catalogue | S2-F05 | Family route, support level, exact versions and catalogue checksum |
| ExecutionProfile | S1-F09 and S2-F05 | Exact paired Node/npm/npx profile reused by baseline, stage and repair validation |
| MigrationPlan/StageExecutionPlan | S2-F06/S2-F07 | Immutable versions, command refs, builder/validation/recovery policy |
| Azure OpenAI gateway/role router | S2-F03 | Readiness/smoke, Structured Outputs, append-only invocation ledger, safe fallback policy |
| Analysis phase review chain | S2-F04 | Deterministic facts → Proposer → Reviewer → G04 |
| Planning phase review chain | S2-F07 | Deterministic plan → Proposer → Reviewer → G06 |
| Command Policy Engine/Executor/ProcessController | Sprint 0 shell; Sprint 1 baseline; Sprint 3 production stage engine | Structured argv, `shell=false`, confinement, timeout, logs, tree cancellation |
| Validation Service | S1 baseline; Sprint 3 stage pipeline; S4 repair/final assurance | One normal validation pipeline and independent assurance dimensions |
| FailureEvidence/C-Lite | S4-F01/F02 | Raw logs plus deterministic parser/router and failure-origin comparison |
| RepairContextPack | S4-F03 | Bounded, redacted, provenance-tagged, checksum-bound context |
| Repair Proposer/Reviewer | S4-F04/F05 | Diff authorship separated from critique, explicit checksum lineage |
| PatchSafety/PatchApply | S4-F06/F07 | Exact persisted diff, dry-run, scope/path checks, patch ledger |
| AI Assistant | S4-F11 | Read-only authoritative context, bounded history, labelled fallback |
| FinalAssuranceService | S4-F12 | Independent clean candidate and G13 |
| DeliveryService | S4-F13 | Source-integrity recheck, generated-output destination binding, manifest/fingerprint, atomic/fail-closed G14 publication to registered `migrated-app/` |
| ReportService/optional narrator | S4-F14 | Deterministic truth always available; optional narrative cannot change facts |
| SSE projection | Sprint 0, exercised throughout | Durable sequence/replay/gap recovery; browser never owns progress |

# G. MVP end-to-end acceptance scenario

```text
External Angular 18.x source path + external target-parent path
→ generate and reserve a separate output root outside the platform repository
→ validate real Windows paths, repository isolation, and Angular eligibility
→ G01
→ create authoritative run
→ controlled fetch/copy from the read-only external source into the run-scoped immutable snapshot and source-integrity proof
→ G02
→ exact source ExecutionProfile
→ baseline sandbox, npm ci, build, tests, lint and parity anchors
→ G03
→ deterministic discovery
→ production Azure readiness/smoke
→ Analysis Proposer/Reviewer
→ G04
→ compatibility route 18→19→20→21 and exact Stage 1 profile
→ G05
→ deterministic MigrationPlan/StageExecutionPlan
→ Planning Proposer/Reviewer and one plan revision
→ G06
→ Stage 18→19 G07
→ exact official Angular update
→ G08
→ normal validation
→ G09
→ cleanup/fingerprint
→ G12
→ copy forward
→ Stage 19→20
→ controlled real failure
→ FailureEvidence and C-Lite
→ RepairContextPack
→ Repair Proposer
→ Repair Reviewer with one revision
→ G10 exact Apply
→ PatchSafety/PatchApply
→ normal validation
→ G11
→ Stage 20→21
→ final assurance sandbox
→ G13
→ delivery candidate, final original-source/destination revalidation, and atomic publication to `<resolved-output-root>/migrated-app`
→ G14
→ deterministic evidence and estimated-cost report with optional AI narrative
→ G15
→ completed run with unchanged original-source fingerprint
```

The scenario must also demonstrate stale approval rejection, environment failure without a code patch, duplicate/no-progress repair prevention, explicit cancellation, browser reconnect, backend restart recovery, rejection of source/target paths inside the platform repository, and absence of a partially published `migrated-app`.

# H. MVP Definition of Done

The MVP is complete only when:

1. Sprint 0 foundations are reused and production contracts are reconciled without losing historical mock data.
2. The real legacy application is never stored inside the platform repository; the external original source is never mutated and its fingerprint is verified at snapshot, completion, failure, cancellation, and delivery.
3. Angular 18.0.x, 18.1.x, and 18.2.x normalize to 18.x while exact versions remain recorded.
4. Every stage resolves exact approved Angular/CLI/TypeScript/RxJS/Node/npm versions before execution.
5. The route is exactly 18.x→19.x→20.x→21.x, one major at a time.
6. SQLite through the Transition Service remains authoritative state; LangGraph checkpoints cannot override it.
7. Artifact Store evidence is finalized and checksum-registered before passed/completed state.
8. CommandExecutor is the only process path; raw shell and forbidden flags are rejected.
9. Every snapshot, baseline, stage, repair, final-assurance, and delivery-candidate workspace uses a registered run-scoped product-owned alias outside the platform repository and original source.
10. G01–G15 are persistent, explicit human gates and production auto-approval is unavailable.
11. Core failed install/version/build/test evidence cannot be approved into passed.
12. Deterministic discovery and planning remain the source of technical truth.
13. The production Azure gateway exists before real phase calls and every call is role-routed, bounded, redacted, versioned, and ledgered.
14. Analysis and Planning use checksum-bound phase Proposer/Reviewer chains; approval-sensitive failures fail closed.
15. Repair uses a diff-authoring Proposer, non-authoring Reviewer, complete checksum lineage, G10, exact apply, and normal-pipeline G11 validation.
16. Environment/user-action failures do not produce blind source patches.
17. Duplicate/equivalent patches and no-progress loops stop and escalate.
18. Cancellation terminates the process tree and recovery resumes or reconstructs only from proven boundaries.
19. Technical, parity, security, quality, and delivery statuses remain independent and honest.
20. Browser/visual parity is `manual_validation_required`; excluded external scanners are `deferred_company_tool_required`.
21. Final assurance runs in a clean independent sandbox and is approved through G13.
22. Delivery is bound to the exact target parent, generated output root, managed `migrated-app` alias, source/snapshot/candidate fingerprints, and is atomic/fail-closed through G14.
23. Final report truth is deterministic; optional AI narrative cannot change facts and may fall back without invalidating the report.
24. Provider-recorded input/output/total tokens and historical pricing snapshots produce clearly labelled estimated cost.
25. The external generated-fixture suite proves Angular 18.x→21.x, repository isolation, generated-output layout, repair, cancellation, restart, source integrity, and final publication.
