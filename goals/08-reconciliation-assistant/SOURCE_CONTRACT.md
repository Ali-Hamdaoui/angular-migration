# Authoritative Backlog Contracts — G08 Startup Reconciliation and Migration Assistant

The following sections are extracted verbatim from the supplied authoritative backlog. Shared operating rules add execution discipline but cannot weaken them.

<!-- S4-F10 sha256:d5be2f77bea72f1d00d1982c1393e853d34274891a1246c2ee3f29d8ffc61230 -->
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Reconcile interrupted commands, leases, artifacts, and graph state on startup**, then the backend performs only the authorized service operation, persists the result, emits the documented **RECONCILIATION_STARTED/COMPLETED** durable events, and the UI displays the authoritative success state.
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

---

<!-- S4-F11 sha256:aa27885c2a5f87d42041e9f00b2f5f63877fb1457ad5425902a2eb4a4c258ff7 -->
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Explain authoritative migration state through the AI Assistant**, then the backend performs only the authorized service operation, persists the result, emits the documented **ASSISTANT_RESPONSE_STARTED/COMPLETED/FAILED** durable events, and the UI displays the authoritative success state.
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

---
