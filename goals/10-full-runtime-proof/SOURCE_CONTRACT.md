# Exact Authoritative Backlog Contract

<!-- S4-F15 sha256:1c7dfaf2b0548fd4b630bddea11088b1f7b7d67df6032cba0a192182c38f4194 -->

### S4-F15 — Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Operational capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** None added in this feature

#### User-observable outcome

The team can execute the final manual and automated runtime proof on Angular 18.0.x and 18.2.x workspaces generated under external temporary test roots, including all gates, one real repair, an environment blocker, cancellation, restart recovery, final assurance, external-output publication, and unchanged external source.

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
- **Artifact Store output:** External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
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
→ ArtifactService finalizes evidence: External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Prove the full Angular 18.x to approved 21.x MVP with fixtures, repair, cancel, and restart**, then the backend performs only the authorized service operation, persists the result, emits the documented **Existing** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **Test execution metadata and complete migration-run records/artifacts.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
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

**Expected UI result:** The team can execute the final manual and automated runtime proof on Angular 18.0.x and 18.2.x workspaces generated under external temporary test roots, including all gates, one real repair, an environment blocker, cancellation, restart recovery, final assurance, external-output publication, and unchanged external source. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

**Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

**Expected database/API result:** Records described by `Test execution metadata and complete migration-run records/artifacts.` are retrievable through `Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status` and include idempotency and correlation metadata where the operation is mutating.

**Expected artifact:** External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.

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
  - **Artifact impact:** Produce or reference evidence only through ArtifactService: External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
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
  - **Scope:** Persistence: Test execution metadata and complete migration-run records/artifacts. API: Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status. Events: Existing production events validated for completeness/order; acceptance-suite status events optional. Artifacts: External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
  - **Out of scope:** Angular 11-17 production validation, Angular 22, unsupported topologies, browser automation, and enterprise scale.
  - **Implementation notes:** Use Alembic for schema changes, short transactions, optimistic versions, and unique idempotency keys. Finalize and checksum artifacts before committing a passed/completed transition. APIs accept IDs, never arbitrary artifact paths.
  - **Likely files/modules:** backend/app/db/models, backend/alembic/versions, backend/app/api/v1, backend/app/events, backend/app/artifacts, and API schema documentation.
  - **Input contract:** Typed application-service result, aggregate IDs/version, artifact temporary files or serialized content, actor/correlation/idempotency metadata.
  - **Output contract:** Committed database records, finalized artifact IDs/checksums, durable event sequence, and versioned API response/error envelope.
  - **Database impact:** Create/update schema and indexes required for: Test execution metadata and complete migration-run records/artifacts.
  - **API impact:** Implement and document: Existing production APIs; optional GET /api/v1/operator/acceptance-suite/status; include 400/403/404/409/422/500-class stable error codes as applicable.
  - **Event impact:** Persist then emit: Existing production events validated for completeness/order; acceptance-suite status events optional.; event payload includes run/stage IDs, state version, actor, timestamp, and artifact refs.
  - **Artifact impact:** Atomic temp-write → SHA-256 → atomic rename → DB registration for: External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
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
  - **Artifact impact:** Render artifact links/previews by registered artifact ID for: External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.
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
  - **Artifact impact:** Assert existence, checksum, immutability, and safe retrieval of `External fixture-generation manifests, repository-isolation evidence, external-output-layout evidence, automated integration results, real runtime proof report, cancellation/restart evidence, repair lineage, final output fingerprint, and external-source integrity proof.` where applicable.
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
