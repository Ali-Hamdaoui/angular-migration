# Authoritative Backlog Contracts — G02 Stage Workspace, G07, and Bootstrap

The following sections are extracted verbatim from the supplied authoritative backlog. Shared operating rules add execution discipline but cannot weaken them.

<!-- S3-F05 sha256:a934fd752ee95d183072daa72d6c6fa70090d1f34727a9e59fe1a58929403d8f -->
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

---

<!-- S3-F06 sha256:ee69eb1c6ebe9e9b4875e7f2b64508c6f3db21b3fa19ed1ebcc202c145aec1a3 -->
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

---
