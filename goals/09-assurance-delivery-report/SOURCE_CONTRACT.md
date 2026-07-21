# Authoritative Backlog Contracts — G09 Final Assurance, Delivery, Reporting, and G13–G15

The following sections are extracted verbatim from the supplied authoritative backlog. Shared operating rules add execution discipline but cannot weaken them.

<!-- S4-F12 sha256:9d7e78f9b8c6622be43c567604c0eabf33cc478d4dd9731d327eb84688f6346f -->
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Run independent final assurance and decide G13**, then the backend performs only the authorized service operation, persists the result, emits the documented **FINAL_ASSURANCE_STARTED/STEP_COMPLETED/COMPLETED/FAILED** durable events, and the UI displays the authoritative success state.
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

---

<!-- S4-F13 sha256:f524016c2d3ce63055c3f12442616a7a0a69d0fbf56676e52945eaa365dc129a -->
### S4-F13 — Create a delivery candidate and publish atomically through G14

#### Feature identity

- **Sprint:** Sprint 4
- **Feature type:** Approval capability
- **Priority:** Must
- **Suggested feature estimate:** M
- **Authoritative gate:** G14

#### User-observable outcome

A reviewer can inspect the exact user-selected external output root, clean delivery manifest/fingerprint, original-source integrity proof, and destination safety, decide G14, and publish `<resolved-output-root>/migrated-app` atomically or fail closed without exposing a partial final directory.

#### Context

Final output appears only at `<resolved-output-root>/migrated-app`, beneath the exact user-selected external output root, and only from the approved final fingerprint after independent verification, unchanged-original-source proof, destination revalidation, and human delivery authority.

**Governing specification sections:** 33-35, 53.9, 56.15, 68.10, 70.10

#### Scope

Candidate copied from the approved final stage sandbox into the registered delivery-candidate alias under the same output root, manifest/fingerprint, source-integrity recheck, output-root ownership and destination safety, G14, atomic/fail-closed publication to `migrated-app/`, and UI.

#### Out of scope

Cloud deployment, Git push/PR, backend migration, and publishing before final assurance.

#### Backend slice

- **Application service/components:** DeliveryService for candidate copy from the approved final stage sandbox, exclusions, manifest/fingerprint, original-source fingerprint revalidation, output-root containment, parent writability, and ownership revalidation, managed-output and overwrite policy, G14 package, idempotent publication to the exact registered `migrated-app` alias, same-volume atomic rename or two-phase fail-closed fallback, and source/snapshot/final binding.
- **Domain aggregate/projection:** DeliveryRecord, ApprovalGate G14.
- **Persistence:** delivery_records, output-root/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.
- **State/approval rule:** G14 is created as a persistent gate. Its decision is bound to the current state version, gate version, artifact-set checksum, plan version where applicable, and workspace fingerprint where applicable.
- **Validation and idempotency:** Mutating requests carry the expected aggregate state version and an idempotency key. Services validate prerequisites and return stable conflict/error codes before side effects.
- **API contract:** `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish`
- **Durable event:** DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.
- **Artifact Store output:** Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, output-root destination safety report, managed-output ownership report, G14 package, and publication record.
- **Security controls:** Enforce actor/run authorization hooks, path/workspace confinement where relevant, artifact ID access, secret redaction, prompt-injection boundaries for untrusted content, and fail-closed behavior.

#### Frontend slice

- **Surface:** Delivery review page with selected external output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.
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
→ DeliveryService for candidate copy from the approved final stage sandbox, exclusions, manifest/fingerprint, original-source fingerprint revalidation, output-root containment, parent writability, and ownership revalidation, managed-output and overwrite policy, G14 package, idempotent publication to the exact registered `migrated-app` alias, same-volume atomic rename or two-phase fail-closed fallback, and source/snapshot/final binding.
→ delivery_records, output-root/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.
→ ArtifactService finalizes evidence: Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, output-root destination safety report, managed-output ownership report, G14 package, and publication record.
→ Transition/Event service persists and emits: DELIVERY_CANDIDATE_READY, PUBLICATION_STARTED/COMPLETED/FAILED and G14 events.
→ SSE replay or snapshot refresh
→ Delivery review page with selected external output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.
```

#### Sub-issues

- `S4-F13-I01` — Backend/application contract
- `S4-F13-I02` — Persistence, API, durable event, and artifact contract
- `S4-F13-I03` — Frontend projection and interaction
- `S4-F13-I04` — Automated, security, manual, and documentation verification

#### Feature acceptance criteria

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Create a delivery candidate and publish atomically through G14**, then the backend performs only the authorized service operation, persists the result, emits the documented **DELIVERY_CANDIDATE_READY** durable events, and the UI displays the authoritative success state.
- **Invalid input:** Given malformed, unsupported, unsafe, or incomplete input, when the request is submitted, then FastAPI returns a stable machine-readable error, no illegal transition occurs, no unregistered artifact is trusted, and the UI displays a corrective blocked or failure state.
- **Stale state:** Given the aggregate state version changes after the page is loaded, when a mutating request uses the old version, then the backend returns `STALE_STATE_VERSION`, the UI reloads the snapshot, and the operation is not duplicated.
- **Persistence:** Given the operation succeeds, when the database is inspected through its repository/API, then the expected records for **delivery_records, output-root/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.** exist with state version, timestamps, and idempotency lineage.
- **Evidence:** Given the feature produces evidence, when the step is shown as passed or completed, then **Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, output-root destination safety report, managed-output ownership report, G14 package, and publication record.** is already finalized, SHA-256 registered, retrievable by artifact ID, and immutable.
- **Frontend behavior:** Given loading, empty, running, success, blocked, stale, backend-failure, and reconnect states, when each is simulated, then the UI renders a distinct user-readable state and never advances the workflow locally.
- **Backend failure:** Given the application service, database, filesystem, external process, or external provider fails, when the failure is returned, then partial evidence is preserved where safe, state remains legal, and the UI exposes a correlation ID and recovery guidance.
- **Missing approval:** Given G14 is pending, rejected, modification-requested, expired, or stale, when the next protected transition is requested, then the Transition Service rejects progression.
- **Approval binding:** Given any bound artifact, plan version, state version, or workspace fingerprint changes, when an older G14 decision is replayed, then it is recorded as invalid/stale and cannot satisfy the active gate.
- **Technical truth:** Given a mandatory technical check is failed, when a human submits approval, then the failed check remains failed and progression follows the configured non-bypass policy.
- **Repository/source isolation:** Given publication starts, when all paths are revalidated, then the external source and platform repository are read-only/out-of-scope and only registered product-owned candidate and destination aliases may be touched.
- **Destination contract:** Given publication succeeds, when the selected external output root is inspected, then `migrated-app/` exactly matches the approved candidate fingerprint and no temporary or partial final directory is presented as successful.
- **Source integrity:** Given the original source fingerprint differs from the G02-approved boundary, when G14 or publication is attempted, then delivery is blocked and the changed source is reported without mutation.

#### Manual end-to-end test scenario

**Preconditions:** S4-F12; use an authenticated local reviewer/operator identity and the sprint fixture appropriate to this feature.

    **Fixture/test data:** a synthetic Angular 18.x single-application npm workspace generated in an external temporary source directory for positive paths; a deliberately invalid, stale, blocked, or unsafe external variant for the negative path. The platform repository contains only fixture generators/manifests, never the generated full workspace.

    **UI steps:**
    1. Launch the backend and frontend and open the relevant run or operator page.
    2. Navigate to the surface described by **Delivery review page with selected external output root, final `migrated-app` path, source-integrity status, file counts, fingerprint, exclusions, overwrite/fallback explanation, G14 controls, publish progress, and partial-failure evidence.**.
    3. Trigger the primary action for **Create a delivery candidate and publish atomically through G14** using valid fixture data.
    4. Observe progress through the UI and, when applicable, disconnect/refresh and reconnect.
    5. Open the resulting detail, event, and artifact views.
6. Open the **G14** review package, enter a review comment, and choose an allowed decision.
7. Repeat with a stale state version or changed bound artifact to verify rejection.

    **Expected UI result:** A reviewer can inspect the exact user-selected external output root, clean delivery manifest/fingerprint, original-source integrity proof, and destination safety, decide G14, and publish `<resolved-output-root>/migrated-app` atomically or fail closed without exposing a partial final directory. Loading, success, blocked, stale, and failure presentations are distinguishable; the UI derives final state from the backend snapshot/events.

    **Expected backend state:** The legal aggregate transition is persisted with an incremented state version, or the read-only result is recorded without altering workflow state.

    **Expected database/API result:** Records described by `delivery_records, output-root/migrated-app aliases, source/snapshot/candidate/final fingerprints, publication attempts, gate decisions/events.` are retrievable through `POST /api/v1/runs/{id}/delivery/candidate; GET /api/v1/runs/{id}/delivery; POST /api/v1/runs/{id}/approvals/G14/decisions; POST /api/v1/runs/{id}/delivery/publish` and include idempotency and correlation metadata where the operation is mutating.

    **Expected artifact:** Delivery manifest, exclusion list, candidate fingerprint, original-source final integrity report, output-root destination safety report, managed-output ownership report, G14 package, and publication record.

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
- Selected external output root changed after G14 evidence creation
- Existing unmanaged `migrated-app/` or ownership ambiguity
- Original external source changed after G02
- Partial copy, disk exhaustion, or file locks during two-phase fallback
- Reparse-point or containment escape into the source or platform repository
- Duplicate publication or conflicting idempotency payload

---

<!-- S4-F14 sha256:c2dfb93fcc73d94531db20735e847d0588b8e2c1fe021f580951c54c0fa52e2c -->
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

- **Happy path:** Given all dependencies are complete and valid inputs are supplied, when the user completes the UI action for **Generate, view, download, and accept the final evidence and cost report through G15**, then the backend performs only the authorized service operation, persists the result, emits the documented **REPORT_GENERATION_STARTED/READY/FAILED** durable events, and the UI displays the authoritative success state.
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

---
