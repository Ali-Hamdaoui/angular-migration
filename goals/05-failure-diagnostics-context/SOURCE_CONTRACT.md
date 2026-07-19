# Authoritative Backlog Contracts — G05 Failure Evidence, C-Lite, and Repair Context

The following sections are extracted verbatim from the supplied authoritative backlog. Shared operating rules add execution discipline but cannot weaken them.

<!-- S4-F01 sha256:ecfa53a69423427b040e712dc8e49e73919ec65a336dfc535e59627d596fc1bb -->
### S4-F01 — Capture FailureEvidence and parse deterministic diagnostics

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Repair capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

A reviewer can open a failed command inspect immutable raw logs, normalized npm/Angular CLI/TypeScript/template/test/generic diagnostics, locations, fingerprints, and baseline origin.

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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Capture FailureEvidence and parse deterministic diagnostics**, then the backend performs only the authorized service operation, persists the result, emits the documented **FAILURE_CAPTURED** durable events, and the UI displays the authoritative success state.
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

**Expected UI result:** A reviewer can open a failed command inspect immutable raw logs, normalized npm/Angular CLI/TypeScript/template/test/generic diagnostics, locations, fingerprints, and baseline origin. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

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

---

<!-- S4-F02 sha256:853a5d31489d331f1749600b689ca58af2d8bef1d244d76f924da90443144a1c -->
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Route failures with C-Lite and show environment or retry actions**, then the backend performs only the authorized service operation, persists the result, emits the documented **FAILURE_CLASSIFIED** durable events, and the UI displays the authoritative success state.
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

---

<!-- S4-F03 sha256:5d8ad28e95c925914fa592ab372deaf62ae0bd0df0627aaad62dfb5ec0722906 -->
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Build and inspect a bounded sanitized RepairContextPack**, then the backend performs only the authorized service operation, persists the result, emits the documented **REPAIR_CONTEXT_CREATED** durable events, and the UI displays the authoritative success state.
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

---
