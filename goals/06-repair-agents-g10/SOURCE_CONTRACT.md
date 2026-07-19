# Authoritative Backlog Contracts — G06 Repair Proposer, Reviewer, and G10

The following sections are extracted verbatim from the supplied authoritative backlog. Shared operating rules add execution discipline but cannot weaken them.

<!-- S4-F04 sha256:48fb3897b0101df6f7f0f4847a4a19d30414a6f63dee703654d77b05c59b25ab -->
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Generate and review a Proposer repair candidate**, then the backend performs only the authorized service operation, persists the result, emits the documented **PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED** durable events, and the UI displays the authoritative success state.
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

---

<!-- S4-F05 sha256:fd6da24220da9d5cc740f6c30d94f8e738f2be4c5e1b13e9e13b35bd072b46b2 -->
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Review a Proposer candidate with non-authoring Reviewer and bounded revision**, then the backend performs only the authorized service operation, persists the result, emits the documented **REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT** durable events, and the UI displays the authoritative success state.
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

---

<!-- S4-F06 sha256:db7e1fc8e004a0accdc98904871b5fb666ab877536ea4d9a6bec25ae1a89c592 -->
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Persist an accepted proposal and decide G10 Apply or Reject**, then the backend performs only the authorized service operation, persists the result, emits the documented **REPAIR_PROPOSAL_READY** durable events, and the UI displays the authoritative success state.
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

---
