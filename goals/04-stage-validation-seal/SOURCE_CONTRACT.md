# Authoritative Backlog Contracts — G04 Stage Validation, G09, G12, and Copy-Forward

The following sections are extracted verbatim from the supplied authoritative backlog. Shared operating rules add execution discipline but cannot weaken them.

<!-- S3-F10 sha256:dce98a5bd496e4efb82af6d36f885ff552b2ea6a0b8e3801948ba076c8a9ab29 -->
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

---

<!-- S3-F11 sha256:8dfe70942558b51fe8e84a8553000a6ccf2595f2f264e9b38b30ac416880ecc0 -->
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

---

<!-- S3-F12 sha256:c3753e939012e382315fff5857c2805fad2b69c4e96dcdf71f572e18542f61c7 -->
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

---

<!-- S3-F13 sha256:d07f4331498a9bd76c3f365aaf84162e7d283848c3b097c5745c2d9c17243170 -->
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

---

<!-- S3-F14 sha256:b14fd771e7e347027a24731c7afd48d276d6d72f1c7f6ade99e35647d56a096e -->
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

---
