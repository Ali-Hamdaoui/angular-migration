# Authoritative Backlog Contracts — G07 Exact Patch Apply, G11, and Loop Protection

The following sections are extracted verbatim from the supplied authoritative backlog. Shared operating rules add execution discipline but cannot weaken them.

<!-- S4-F07 sha256:fcb8413a8dbd0d15173eee7db887ebb212c997c16cfc0526784976d00bd0960a -->
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Validate and apply only the exact persisted repair diff**, then the backend performs only the authorized service operation, persists the result, emits the documented **REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED** durable events, and the UI displays the authoritative success state.
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

---

<!-- S4-F08 sha256:bac89f45ac8b277b4a3a46788cda319601c91f2ba2cee0cc349d92d96d095dd0 -->
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Run patch preflight, resume normal validation, and decide G11**, then the backend performs only the authorized service operation, persists the result, emits the documented **PATCH_PREFLIGHT_COMPLETED** durable events, and the UI displays the authoritative success state.
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

---

<!-- S4-F09 sha256:32c1cd302529950e4cdbcf4764224f678bacf899d5ab4eb0fe5e8ea8e89e563d -->
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Stop no-progress repair loops and reconstruct or roll back safely**, then the backend performs only the authorized service operation, persists the result, emits the documented **DUPLICATE_PATCH_REJECTED** durable events, and the UI displays the authoritative success state.
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

---
