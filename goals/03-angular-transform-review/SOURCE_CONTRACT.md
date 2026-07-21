# Authoritative Backlog Contracts — G03 Exact Angular Transformation and G08

The following sections are extracted verbatim from the supplied authoritative backlog. Shared operating rules add execution discipline but cannot weaken them.

<!-- S3-F07 sha256:654993bf3c36c7032698cb239dca24cec2b418404037fb41e96a4d59eb72adb3 -->
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

---

<!-- S3-F08 sha256:a4d2ec3d1eaa6c1394f70b1d6df2fa4842bbc47d64ac02b57cf67a743801c243 -->
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

---

<!-- S3-F09 sha256:0bb4c3363afd402fa457e7b966ad11716e7818eb6ecb43954ad6a174abf259ae -->
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

---
