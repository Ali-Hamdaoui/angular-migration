# Angular Migration Control Tower
## Complete Four-Sprint MVP Development Backlog — Sprint 0 and LLM Governance Integrated

**Project:** AI Frontend Migration Factory — Angular Compatibility Migration  
**Backlog status:** Implementation-ready, authoritative-scope aligned, Sprint 0-integrated, LLM-governance corrected  
**Backlog version:** 2.0 — Final consolidated edition  
**Prepared:** 2026-07-14  
**Approved MVP route:** Angular 18.x → Angular 19.x → Angular 20.x → Angular 21.x  
**Migration mode:** Strict technical compatibility with functional-parity controls  
**Backlog structure:** Exactly four logical delivery sprints → 50 vertical features → 200 bounded implementation issues  
**Completed prerequisite:** Sprint 0 platform skeleton and mock proof  
**Authority model:** LangGraph coordination; Transition Service legal movement; SQLite state; CommandExecutor execution; Artifact Store evidence; explicit human G01–G15 decisions

> Angular 21.x is the **approved MVP target**, not the latest Angular release. Sprint 0 is treated as completed work and is not rebuilt. This document replaces the previous four-sprint backlog, the standalone revised Sprint 1, and the separate LLM-amendment document.

# A. Backlog interpretation

## A.1 Consolidation decisions

This backlog is generated from the authoritative product specification, the completed Sprint 0 backlog, the revised Sprint 1, and the verified Azure OpenAI usage audit.

- Sprint 1 reuses the FastAPI/Next.js shells, SQLite/Alembic, Transition Service foundation, durable SSE, Artifact Store, command-worker shell, mock LangGraph workflow, viewers, cancellation/resume, LLM mock contracts, observability, and Angular fixture completed in Sprint 0.
- Sprint 1 advances through a real immutable source, exact source runtime, real baseline commands, known-failure/parity anchors, and G03.
- Sprint 2 starts from G03, implements the real Azure OpenAI boundary before its consumers, and changes Analysis and Planning into checksum-bound Proposer/Reviewer phase-review chains.
- Sprint 3 remains the deterministic stage-execution increment.
- Sprint 4 reuses the Sprint 2 gateway, removes the duplicate gateway feature, strengthens repair lineage, and separates deterministic report truth from optional AI narrative.

Every feature remains a complete vertical slice:

```text
observable outcome
→ bounded backend service
→ authoritative state/evidence
→ typed API and durable event
→ frontend projection
→ automated tests
→ UI manual confirmation
```

## A.2 Non-negotiable authority boundaries

```text
LangGraph             → coordinates workflow use cases only
Transition Service    → validates and persists every legal transition
SQLite                → authoritative structured state
CommandExecutor       → only external-process execution path
Artifact Store        → authoritative immutable evidence
Frontend              → projection of backend state only
Human                 → G01–G15 decisions
Phase Proposer        → bounded analysis/planning explanation only
Repair Proposer       → only LLM allowed to author a repair diff
Phase/Repair Reviewer → critique/review only; never replacement mutation
PatchApplyService     → exact persisted, checksum-bound, approved diff only
```

## A.3 Web-verified implementation constraints

- Angular publishes Angular-family-specific Node.js, TypeScript, and RxJS compatibility tables.
- Multi-major Angular updates are executed one major at a time.
- `npm ci` requires an existing lockfile and fails instead of silently rewriting a mismatch.
- Optional Angular build-system and modernization migrations remain separate decisions.
- LangGraph persistence and interrupts support coordination and human pauses, while SQLite remains this product's business source of truth.
- SQLite WAL is limited to the same-host local MVP and not a network-share database design.
- Azure OpenAI structured outputs reduce syntax ambiguity but remain followed by Pydantic, semantic, security, checksum, and policy validation.

## A.4 Capacity risk

The four sprints are logical integration increments, not calendar promises. The scope includes a migration engine, Windows execution runtime, fifteen gates, real Azure integration, phase and repair review chains, recovery, final assurance, atomic publication, and runtime proof. Team capacity and corporate environment constraints must be assessed before assigning dates; scope must not be hidden inside XL issues.

# B. Dependency overview

```text
Completed Sprint 0 mock platform
→ production contract and LLM vocabulary reconciliation
→ Windows/environment readiness
→ path and Angular eligibility
→ G01 → real run → immutable snapshot → G02
→ exact source runtime → baseline sandbox and commands → G03
→ deterministic discovery
→ production Azure gateway and append-only ledger
→ Analysis Proposer/Reviewer → G04
→ compatibility route and exact Stage 1 profile → G05
→ deterministic plan → Planning Proposer/Reviewer → G06
→ command policy/execution and stage sandbox → G07
→ exact Angular update → G08
→ validation/parity → G09
→ cleanup/fingerprint/copy-forward → G12
→ FailureEvidence and C-Lite
→ RepairContextPack → Repair Proposer → Repair Reviewer → G10
→ exact patch apply → normal validation → G11
→ recovery and Assistant
→ final assurance → G13
→ delivery → G14
→ deterministic report + optional narrative → G15
→ full Angular 18.x→21.x runtime proof
```

# C. Sprint summary

| Sprint | Goal | Features | Issues | Gates |
|---:|---|---:|---:|---|
| 1 | Real intake, immutable snapshot, exact source runtime, baseline qualification | 14 | 56 | G01, G02, G03 |
| 2 | Deterministic discovery, production Azure AI phase review, feasibility and planning | 7 | 28 | G04, G05, G06 |
| 3 | Controlled stage execution, transformation review, validation and copy-forward | 14 | 56 | G07, G08, G09, G12 |
| 4 | Failure/repair, recovery, final assurance, delivery, reporting and runtime proof | 15 | 60 | G10, G11, G13, G14, G15 |
| **Total** |  | **50** | **200** | **G01–G15** |

# D. Detailed sprint backlog

## Sprint 1 — Real Intake, Immutable Snapshot, Source Runtime, Baseline Qualification, and G03

### 1. Alignment decision

Sprint 0 already built the platform skeleton and mock proof: FastAPI and Next.js shells, configuration, SQLAlchemy/Alembic/SQLite, state and event contracts, Transition Service foundations, ordered SSE replay, Artifact Store, structured-command shell, mock LangGraph workflow, viewers, worker leases, cancellation/resume, LLM usage mock, observability, and the Angular fixture.

Sprint 1 must therefore **productionize and exercise** those foundations with a real source application. It must not rebuild them as new standalone features.

The revised Sprint 1 also corrects two Sprint 0 assumptions before real execution:

1. The production workflow uses the authoritative multidimensional phases and statuses rather than the Sprint 0 six-phase compression as business truth.
2. Production auto-approval is removed. G01–G15 are explicit human decisions. Any auto-approval behavior retained for tests is isolated from the production workflow.

Because Sprint 0 explicitly deferred real source intake, arbitrary-project snapshots, source-compatible runtime work, and real baseline commands to Sprint 1, this revised sprint advances through **baseline qualification and G03**. The original four-sprint backlog's Sprint 2 must subsequently remove duplicated baseline work and begin from deterministic discovery, analysis, feasibility, and planning.

---

### 2. Original Sprint 1 change matrix

| Original Sprint 1 feature | Decision | Revised treatment |
|---|---|---|
| S1-F01 — Launch platform and health | **Delete as standalone** | Completed by Sprint 0. Only production environment-readiness extensions remain in revised S1-F02. |
| S1-F02 — SQLite/WAL readiness | **Delete as standalone** | Completed by Sprint 0. Sprint 1 only verifies the existing local-WAL boundary during diagnostics. |
| S1-F03 — Test immutable artifact | **Delete as standalone** | Completed by Sprint 0 Artifact Store and viewers. Real artifacts are produced inside every revised feature. |
| S1-F04 — State and legal transitions | **Replace, do not rebuild** | Revised S1-F01 migrates Sprint 0 contracts to the authoritative vocabulary and removes production auto-approval. |
| S1-F05 — SSE projection | **Delete as standalone** | Completed by Sprint 0. Every real feature must prove snapshot/replay/reconnect using the existing mechanism. |
| S1-F06 — Path validation | **Keep and expand** | Revised S1-F03 handles arbitrary Windows paths, junctions, target reservation, and source staleness. |
| S1-F07 — Angular eligibility/topology | **Keep and expand** | Revised S1-F04 performs real deterministic parsing and support classification. |
| S1-F08 — G01 | **Keep and modify** | Revised S1-F05 reuses approval infrastructure, binds real evidence, and forbids auto-approval. |
| S1-F09 — Run creation/LangGraph shell | **Modify** | Revised S1-F06 promotes the mock path to a real run and real source-intake graph while preserving SQLite authority. |
| S1-F10 — Snapshot and G02 | **Split and expand** | Revised S1-F07 creates the real snapshot; revised S1-F08 handles G02 and source integrity. |
| Missing from original Sprint 1 | **Add** | Source runtime resolution, baseline sandbox/package prequalification, real `npm ci`, build/test/lint, parity anchors, known-failure fingerprints, and G03. |

---

### 3. Sprint goal

Convert the completed Sprint 0 skeleton into the first real, safe, reproducible product increment.

The sprint accepts a real Angular 18.x source, validates it, obtains G01, creates a real run, creates and approves an immutable source snapshot through G02, resolves an exact source-compatible ExecutionProfile, creates a separate baseline sandbox, audits package and lifecycle behavior, runs a frozen clean installation plus configured build/test/lint commands, captures baseline parity anchors and known failure fingerprints, and obtains G03.

At sprint completion, the run is ready for Sprint 2 discovery and analysis. It is **not migrated**.

---

### 4. Authoritative boundaries preserved

```text
LangGraph          → coordinates real use cases only
Transition Service → validates every legal transition
SQLite             → authoritative structured state
CommandExecutor    → only external-process path
Artifact Store     → immutable evidence authority
Frontend           → backend projection only
Human              → G01, G02, and G03 decisions
Original source    → read-only and fingerprint-verified
```

The sprint does not introduce a new state authority, command path, approval path, artifact path, or direct LLM mutation path.

---

### 5. Web-verified implementation constraints

The revised backlog uses these current official constraints:

- Angular publishes version-specific Node.js, TypeScript, and RxJS compatibility, so the source runtime is resolved through a versioned policy rather than the host default runtime.
- Angular multi-major upgrades are performed one major at a time; Sprint 1 performs no upgrade and only prepares a proven baseline.
- `angular.json` is the authoritative Angular CLI workspace configuration and its `projects` section supports deterministic topology and target discovery.
- A committed `package-lock.json` represents the exact dependency tree, and `npm ci` fails rather than rewriting a mismatched lockfile.
- LangGraph persistence and interrupts support orchestration resume, but the project continues to treat SQLite domain state as authoritative.
- SQLite WAL is retained for the local, same-host MVP and must not be moved to an unsupported network-share operating model.
- Windows paths require explicit normalization, long-path awareness, and reparse/junction handling before containment decisions.

---

### 6. Sprint boundaries

#### In scope

- Reconcile Sprint 0 contracts with the authoritative specification.
- Remove production auto-approval.
- Real Windows/corporate environment readiness.
- Real source/target validation and target reservation.
- Real Angular eligibility and topology analysis.
- Checksum-bound real preflight and G01.
- Real run creation and LangGraph handoff.
- Real arbitrary-project immutable snapshot and G02.
- Exact source-compatible ExecutionProfile selection.
- Baseline sandbox and package/lifecycle prequalification.
- Real `npm ci`, build, tests, and lint through CommandExecutor.
- Baseline parity anchors and known-failure fingerprints.
- Baseline qualification and G03.
- UI, SSE, artifact, recovery, security, and test work for every feature.

#### Out of scope

- AI Analysis Agent and Planning Agent real calls.
- Deep dependency, route, UI, state-management, or business analysis.
- Historical target-stage compatibility catalogue and exact target patches.
- G04–G15.
- `ng update` or any Angular transformation.
- Proposer/Reviewer repair flow.
- Final assurance, delivery publication, or final evidence report.
- Browser/visual automation and excluded external scanners.

---

### 7. Feature summary

| Order | Feature | Outcome | Gate |
|---:|---|---|---|
| 1 | S1-F01 — Reconcile Sprint 0 contracts with the authoritative workflow | An operator can open the Control Tower and see the authoritative run, phase, stage, step, approval, repair, and assurance dimensions without the old six-phase compression or production auto-approval behavior. | — |
| 2 | S1-F02 — Productionize Windows and corporate-environment readiness | An operator can see the real local execution readiness needed for source intake and baseline work: paired Node/npm/npx installations, Git, local data roots, disk, registry, proxy, and certificate status. | — |
| 3 | S1-F03 — Validate real source and target paths and reserve the output safely | A user can enter arbitrary local source and target paths and receive precise pass, warning, or blocker results before any run or copy is created. | — |
| 4 | S1-F04 — Detect Angular eligibility, exact versions, lockfile, and workspace topology | A user can analyze the validated source and see deterministic Angular facts, exact and family versions, package manager, lockfile, projects, builders, and MVP support classification. | — |
| 5 | S1-F05 — Create a checksum-bound production preflight and decide G01 | A reviewer can inspect a complete real source/path/environment eligibility package and approve, request modification, or reject G01; stale decisions cannot advance the workflow. | G01 |
| 6 | S1-F06 — Create the real authoritative run and hand off to LangGraph safely | After G01 approval, a user can create one real migration run, see it become the single active mutating run, and observe LangGraph coordinate real source-intake services without owning state or execution. | — |
| 7 | S1-F07 — Create and inspect an immutable arbitrary-project source snapshot | A user can create a real product-owned source snapshot, inspect its complete manifest and fingerprint, and see that no command has run in the original source. | — |
| 8 | S1-F08 — Review G02 and establish the immutable source-integrity boundary | A reviewer can inspect the exact snapshot evidence, approve or reject G02, and prove the original source fingerprint still matches the approved pre-snapshot state. | G02 |
| 9 | S1-F09 — Resolve and approve the source-compatible ExecutionProfile | A reviewer can see which exact Node/npm/npx runtime will reproduce the Angular 18 source baseline and why incompatible or unavailable profiles are blocked. | — |
| 10 | S1-F10 — Create the baseline sandbox and prequalify package, lockfile, registry, and lifecycle scripts | A reviewer can create a mutable baseline sandbox from the approved snapshot and see whether npm metadata and install behavior are safe and reproducible before installation. | — |
| 11 | S1-F11 — Execute and inspect the frozen baseline clean installation | A user can run the approved `npm ci` baseline command through the sole CommandExecutor, watch live logs, cancel it, and inspect immutable completion evidence without source mutation. | — |
| 12 | S1-F12 — Execute the baseline build, test, and lint matrix | A reviewer can see every discovered baseline build, test, and lint target and its real executed, not-configured, blocked, passed, or failed status. | — |
| 13 | S1-F13 — Capture baseline parity anchors and fingerprint pre-existing failures | A reviewer can inspect stable baseline fingerprints for failures, routes, and backend-integration anchors so later migration stages can distinguish existing problems from new regressions. | — |
| 14 | S1-F14 — Qualify the baseline and decide G03 | A reviewer can see a complete baseline qualification package, choose strict-clean or qualified-known-failure policy where allowed, and approve, request modification, or reject G03. | G03 |

---

### 8. Detailed feature backlog

---

### S1-F01 — Reconcile Sprint 0 contracts with the authoritative workflow

**Feature type:** Workflow capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

An operator can open the Control Tower and see the authoritative run, phase, stage, step, approval, repair, and assurance dimensions without the old six-phase compression or production auto-approval behavior.

#### Context

Sprint 0 established the contracts, database schema, transition service, mock graph, generated frontend client, and Control Tower. Those foundations must be migrated—not recreated—because the completed Sprint 0 vocabulary grouped phases and included auto-approval, while the authoritative specification requires separate phases and explicit human approval at G01–G15.

#### Scope

- Migrate the Sprint 0 state vocabulary to the authoritative multidimensional statuses and phases.
- Add missing stage outcomes: preparing, passed_with_known_baseline_failures, and passed_with_manual_items.
- Add authoritative approval and repair status vocabularies.
- Remove or disable auto-approval from the production API, state model, LangGraph route, and UI; retain it only in isolated mock/test fixtures when useful.
- Normalize production endpoints under `/api/v1` while preserving a controlled compatibility migration for existing tests.
- Update Alembic data migration, Pydantic schemas, OpenAPI, generated TypeScript client, selectors, fixture snapshots, and graph routing.
- Prove that LangGraph reads authoritative state and requests transitions instead of treating its checkpoint as business truth.

#### Out of scope

- Real source scanning
- Real command execution beyond Sprint 0 probes
- G01–G03 evidence packages
- Angular transformation

#### Backend and authority slice

ContractMigrationService, TransitionPolicyRegistry updates, ApprovalPolicy cleanup, graph-state adapter changes, and database data migration. Existing Transition Service remains the only legal state-write path.

#### Persistence

Alter existing run/stage/step fields and migrate Sprint 0 mock values to the new vocabulary; add approval_status and repair_status where not already explicit. Preserve event history and aggregate versions.

#### API contract

`GET /api/v1/runs/{runId}/state`, versioned error envelope, and removal/deprecation of production auto-approval mutation endpoints.

#### Durable events

STATE_CONTRACT_MIGRATED, APPROVAL_POLICY_DISABLED_FOR_PRODUCTION, and normal transition events with the new state dimensions.

#### Artifact evidence

`global/00_setup/contract_migration_report.json` and a schema-diff artifact for operator review.

#### Frontend slice

Update the Control Tower timeline, status badges, approval controls, generated client, and state inspector. Auto-approval controls are absent from real runs.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Production LLM contract reconciliation

Sprint 1 performs no real model invocation, but the production contracts and database migration must support the Sprint 2 and Sprint 4 LLM pipeline.

**Roles**

```text
assistant
phase_proposer
phase_reviewer
repair_proposer
repair_reviewer
report_narrator
fallback
```

**Responsibilities**

```text
analysis_review
planning_review
repair_proposal
repair_review
assistant_answer
report_narrative
smoke_check
```

**Invocation statuses**

```text
queued
started
completed
failed
fallback_completed
schema_invalid
semantic_invalid
content_filtered
budget_blocked
configuration_missing
cancelled
```

**Retry and revision counters**

```text
transport_retry
provider_protocol_retry
structured_output_regeneration
phase_review_revision
repair_review_revision
repair_attempt
```

These values remain separate so provider retries are never confused with semantic repair attempts or human-governed review revisions. The existing Sprint 0 mock usage schema is migrated without losing historical mock records.

#### Sub-issues


#### S1-F01-I01 — Backend / Domain: Reconcile Sprint 0 contracts with the authoritative workflow

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F01 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** Completed Sprint 0 contracts, database, Transition Service, SSE, LangGraph mock workflow, and Control Tower
- **Estimate:** M
- **Risk:** High


#### S1-F01-I02 — Database / API / Event / Artifact: Reconcile Sprint 0 contracts with the authoritative workflow

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F01 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** Completed Sprint 0 contracts, database, Transition Service, SSE, LangGraph mock workflow, and Control Tower
- **Estimate:** M
- **Risk:** High


#### S1-F01-I03 — Frontend: Reconcile Sprint 0 contracts with the authoritative workflow

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F01 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** Completed Sprint 0 contracts, database, Transition Service, SSE, LangGraph mock workflow, and Control Tower
- **Estimate:** M
- **Risk:** Low


#### S1-F01-I04 — Testing / Security / Documentation: Reconcile Sprint 0 contracts with the authoritative workflow

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F01 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** Completed Sprint 0 contracts, database, Transition Service, SSE, LangGraph mock workflow, and Control Tower
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given a Sprint 0 database, when the migration runs, then existing mock runs remain readable and no event history is lost.
- Given a real run, when its state is loaded, then the API returns the authoritative separate dimensions and never the old combined phase as business truth.
- Given a user attempts production auto-approval, when the request is submitted, then the backend returns `AUTO_APPROVAL_NOT_ALLOWED` and no gate advances.
- Given LangGraph resumes from an old checkpoint, when SQLite has newer state, then SQLite wins and the graph reconstructs from the authoritative version.
- Given the frontend refreshes, when it reloads the snapshot, then the same authoritative state is displayed without local translation into an unsupported status.

#### Manual end-to-end test

Open a migrated Sprint 0 mock run, verify its historical events remain visible, start a new real-intake draft, confirm the new phase/status vocabulary, and confirm no auto-approval control is available for the real run.

#### Dependencies

- Completed Sprint 0 contracts, database, Transition Service, SSE, LangGraph mock workflow, and Control Tower

#### Risks and edge cases

- Breaking stored mock data
- Frontend enum drift
- Hidden auto-approval code path
- Graph checkpoint overriding SQLite
- Migration rollback complexity

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F02 — Productionize Windows and corporate-environment readiness

**Feature type:** Operational capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

An operator can see the real local execution readiness needed for source intake and baseline work: paired Node/npm/npx installations, Git, local data roots, disk, registry, proxy, and certificate status.

#### Context

Sprint 0 created health, configuration, safe version-command, runtime-profile, and diagnostics foundations. Sprint 1 must replace placeholder readiness with real, sanitized evidence without yet resolving target-stage toolchains.

#### Scope

- Discover approved `node.exe`, associated `npm.cmd` and `npx.cmd`, exact versions, architecture, and installation root.
- Reject mixed executable pairs unless explicitly validated.
- Detect Git and Python worker readiness through the existing structured command authority.
- Validate SQLite and Artifact Store are local, writable, and above disk thresholds.
- Capture npm registry, proxy, HTTPS proxy, strict-SSL, and custom-CA presence without exposing credentials or certificate content.
- Expose actionable available, degraded, and blocked diagnostics through the existing health screen.
- Persist a versioned EnvironmentCapabilitySnapshot that can be checksum-bound into preflight.

#### Out of scope

- Automatic runtime download
- Exact Angular source runtime selection
- Private registry credential repair
- Container or microVM isolation

#### Backend and authority slice

EnvironmentCapabilityService and RuntimeInventoryService use only the Sprint 0 structured command worker for version probes.

#### Persistence

Persist environment capability snapshots, discovered runtime candidates, timestamps, policy version, and checksum; do not store secret values.

#### API contract

`GET /api/v1/environment/diagnostics` and `POST /api/v1/environment/refresh` with idempotency for refresh requests.

#### Durable events

ENVIRONMENT_DIAGNOSTICS_STARTED, ENVIRONMENT_DIAGNOSTICS_COMPLETED, ENVIRONMENT_DIAGNOSTICS_BLOCKED.

#### Artifact evidence

`global/00_setup/environment_capability_summary.json` and `runtime_inventory.json`, both redacted.

#### Frontend slice

Extend the existing health screen with runtime-pair cards, local-storage status, registry/proxy/certificate indicators, refresh, and remediation guidance.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Redacted LLM readiness extension

The environment diagnostics surface must show only safe configuration status:

- Azure endpoint configured: yes/no;
- authentication mode: API key / Entra ID adapter;
- assistant role configured: yes/no;
- phase proposer configured: yes/no;
- phase reviewer configured: yes/no;
- repair proposer configured: yes/no;
- repair reviewer configured: yes/no;
- report narrator configured: yes/no;
- fallback enabled: yes/no;
- pricing snapshot loaded: yes/no;
- context and output-budget policies loaded: yes/no;
- live smoke status: not executed until Sprint 2 / passed / failed.

The UI and APIs must never expose the API key, endpoint value, raw deployment names, provider headers, raw prompts, or raw completions.

#### Sub-issues


#### S1-F02-I01 — Backend / Domain: Productionize Windows and corporate-environment readiness

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F02 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F01, Sprint 0 configuration, health, command worker, Artifact Store, and observability foundations
- **Estimate:** M
- **Risk:** High


#### S1-F02-I02 — Database / API / Event / Artifact: Productionize Windows and corporate-environment readiness

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F02 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F01, Sprint 0 configuration, health, command worker, Artifact Store, and observability foundations
- **Estimate:** M
- **Risk:** High


#### S1-F02-I03 — Frontend: Productionize Windows and corporate-environment readiness

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F02 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F01, Sprint 0 configuration, health, command worker, Artifact Store, and observability foundations
- **Estimate:** M
- **Risk:** Low


#### S1-F02-I04 — Testing / Security / Documentation: Productionize Windows and corporate-environment readiness

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F02 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F01, Sprint 0 configuration, health, command worker, Artifact Store, and observability foundations
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given a valid paired Node/npm/npx installation, when diagnostics run, then all exact versions and the common installation root are displayed.
- Given `node.exe` and `npm.cmd` come from different installations, when diagnostics run, then the candidate is blocked as `RUNTIME_PAIR_MISMATCH`.
- Given proxy credentials exist, when evidence is persisted or displayed, then no secret value appears.
- Given SQLite or the data root is on a disallowed network share, when diagnostics run, then readiness is blocked.
- Given diagnostics are refreshed, when an identical idempotency key is retried, then the original result is returned without duplicate probes.

#### Manual end-to-end test

Open Environment Diagnostics, refresh capabilities, inspect paired runtime candidates and redacted corporate settings, then simulate a missing npm executable and verify a clear blocker without any application-code patch suggestion.

#### Dependencies

- S1-F01
- Sprint 0 configuration, health, command worker, Artifact Store, and observability foundations

#### Risks and edge cases

- Corporate proxy differences
- Multiple Node installations
- Secrets in command output
- Network-share false positives
- Antivirus locking executables

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F03 — Validate real source and target paths and reserve the output safely

**Feature type:** Product capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

A user can enter arbitrary local source and target paths and receive precise pass, warning, or blocker results before any run or copy is created.

#### Context

Sprint 0 validated controlled fixture paths only. Sprint 1 must productionize the PathPolicy for real Windows projects and establish a reservation boundary so two active runs cannot claim the same output.

#### Scope

- Canonicalize absolute paths, separators, drive-letter case, `.` and `..` components.
- Detect source/target equality, unsafe nesting, overlap with internal roots, protected paths, and unsupported network locations.
- Inspect symlinks, junctions, and other reparse-point risks; fail closed on uncertain escapes.
- Validate source readability, target creatability/writability, path-length risk, free disk, and transient file-lock behavior.
- Create a short-lived target reservation record bound to the validation result.
- Generate a source metadata fingerprint from safe lightweight metadata so path validation becomes stale when the selected source materially changes.
- Display sanitized paths and detailed rule results in the existing setup page.

#### Out of scope

- Angular eligibility
- Source snapshot
- Dependency installation
- Permanent run ownership

#### Backend and authority slice

Real PathPolicy, TargetReservationService, WindowsPathInspector, and DiskCapacityEstimator.

#### Persistence

Persist path-validation requests/results, target reservations, expiry, policy version, source metadata fingerprint, and idempotency keys.

#### API contract

`POST /api/v1/sources/validate-paths`, `GET /api/v1/sources/path-validations/{id}`.

#### Durable events

PATH_VALIDATION_STARTED, PATH_VALIDATION_COMPLETED, PATH_VALIDATION_BLOCKED, TARGET_RESERVED, TARGET_RESERVATION_EXPIRED.

#### Artifact evidence

`path_safety_report.json` and `target_reservation.json` after the run is created; pre-run evidence is retained as checksum-bound metadata.

#### Frontend slice

Production setup form with path results, warnings, blocked reasons, expiry, retry, and a source-immutability notice.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Sub-issues


#### S1-F03-I01 — Backend / Domain: Validate real source and target paths and reserve the output safely

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F03 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F02
- **Estimate:** M
- **Risk:** High


#### S1-F03-I02 — Database / API / Event / Artifact: Validate real source and target paths and reserve the output safely

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F03 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F02
- **Estimate:** M
- **Risk:** High


#### S1-F03-I03 — Frontend: Validate real source and target paths and reserve the output safely

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F03 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F02
- **Estimate:** M
- **Risk:** Low


#### S1-F03-I04 — Testing / Security / Documentation: Validate real source and target paths and reserve the output safely

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F03 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F02
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given safe separate local paths, when validation completes, then the target is temporarily reserved and the UI displays passed rules.
- Given the target is nested inside the source, when validation runs, then it is blocked and no directory is created.
- Given a junction escapes the approved root, when validation runs, then the result is blocked.
- Given another active reservation claims the target, when validation runs, then the result is `TARGET_ALREADY_RESERVED`.
- Given the source changes after validation, when the result is reused, then it is stale and cannot support G01 or run creation.

#### Manual end-to-end test

Validate a real Angular fixture and safe target, then repeat with target-inside-source, a junction escape, a long-path warning, and a target already reserved by another test run.

#### Dependencies

- S1-F02

#### Risks and edge cases

- Windows reparse-point behavior
- UNC paths
- Long paths
- Source changing during validation
- Race between reservations
- Sensitive path disclosure

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F04 — Detect Angular eligibility, exact versions, lockfile, and workspace topology

**Feature type:** Product capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

A user can analyze the validated source and see deterministic Angular facts, exact and family versions, package manager, lockfile, projects, builders, and MVP support classification.

#### Context

Sprint 0 supplied contracts and an Angular 18 fixture. Real eligibility is deterministic factual parsing and must not be delegated to an LLM.

#### Scope

- Parse `package.json`, `package-lock.json`, `angular.json`, and relevant TypeScript configuration without executing project code.
- Detect declared and lockfile-resolved `@angular/core`, `@angular/cli`, Material/CDK when present, TypeScript, RxJS, and Zone.js versions.
- Normalize exact versions to source families and expose confidence/conflict evidence.
- Detect AngularJS indicators and block AngularJS; block Angular 2–10; classify Angular 11–17 as product-scope but not runtime-proven for this MVP; accept Angular 18.x reference intake.
- Classify single application, multi-application, local libraries, publishable library, Nx, microfrontend, custom builder, SSR/hybrid, and unknown topology.
- Identify npm and a committed valid lockfile as the Sprint 1 supported package-manager boundary.
- Persist deterministic facts separately from policy decisions.

#### Out of scope

- Deep route or API analysis
- Compatibility ladder
- Target exact versions
- LLM interpretation
- Any file mutation

#### Backend and authority slice

SourceAnalyzer factual scanners, VersionDetector, LockfileInspector, WorkspaceTopologyClassifier, and EligibilityPolicyService.

#### Persistence

Persist source-analysis record, exact/family versions, detected projects/builders, package-manager facts, support classification, policy version, and checksum.

#### API contract

`POST /api/v1/sources/analyze`, `GET /api/v1/sources/analyses/{analysisId}`.

#### Durable events

SOURCE_ANALYSIS_STARTED, SOURCE_ANALYSIS_COMPLETED, SOURCE_ELIGIBILITY_BLOCKED.

#### Artifact evidence

`angular_detection.json`, `version_detection.json`, `workspace_topology.json`, `lockfile_summary.json`, and `eligibility_result.json`.

#### Frontend slice

Eligibility panel showing facts, conflicts, support level, project topology, and why a source is accepted, review-required, or blocked.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Sub-issues


#### S1-F04-I01 — Backend / Domain: Detect Angular eligibility, exact versions, lockfile, and workspace topology

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F04 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F03, Sprint 0 Angular fixture and deterministic component contracts
- **Estimate:** M
- **Risk:** High


#### S1-F04-I02 — Database / API / Event / Artifact: Detect Angular eligibility, exact versions, lockfile, and workspace topology

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F04 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F03, Sprint 0 Angular fixture and deterministic component contracts
- **Estimate:** M
- **Risk:** High


#### S1-F04-I03 — Frontend: Detect Angular eligibility, exact versions, lockfile, and workspace topology

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F04 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F03, Sprint 0 Angular fixture and deterministic component contracts
- **Estimate:** M
- **Risk:** Low


#### S1-F04-I04 — Testing / Security / Documentation: Detect Angular eligibility, exact versions, lockfile, and workspace topology

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F04 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F03, Sprint 0 Angular fixture and deterministic component contracts
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given Angular 18.0.x, 18.1.x, or 18.2.x, when analyzed, then the exact version is shown and the family is normalized to `18.x`.
- Given declared and lockfile-resolved Angular versions disagree, when analyzed, then the result is blocked or review-required with evidence rather than silently choosing one.
- Given AngularJS or Angular 10, when analyzed, then the source is blocked with deterministic indicators.
- Given a multi-application or custom-builder workspace, when analyzed, then it is explicitly classified and not silently accepted as the supported single-app topology.
- Given malicious text in a README or source comment, when analysis runs, then it is treated as data and cannot alter policy.

#### Manual end-to-end test

Analyze clean Angular 18.0.x and 18.2.x fixtures, then AngularJS, Angular 10, multi-app, custom-builder, malformed JSON, and version-conflict fixtures; inspect all evidence in the UI.

#### Dependencies

- S1-F03
- Sprint 0 Angular fixture and deterministic component contracts

#### Risks and edge cases

- Nested workspaces
- Package aliases
- Malformed lockfiles
- Hybrid AngularJS/Angular apps
- Nonstandard builders
- False support claims

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F05 — Create a checksum-bound production preflight and decide G01

**Feature type:** Approval capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

A reviewer can inspect a complete real source/path/environment eligibility package and approve, request modification, or reject G01; stale decisions cannot advance the workflow.

#### Context

Sprint 0 implemented mock preflight and approval infrastructure. Sprint 1 must create the real G01 package from immutable deterministic inputs and remove all production auto-approval behavior.

#### Scope

- Combine path validation, target reservation, environment capability, source eligibility, selected target family, migration mode, and policy versions into one immutable preflight artifact set.
- Calculate an artifact-set checksum and expiry.
- Create G01 with allowed decisions: approved, approved_with_comment, modification_requested, and rejected.
- Bind the decision to gate version, state version, input checksum, artifact-set checksum, actor, and target reservation.
- Mark G01 stale when any bound input or artifact changes.
- Implement append-only decision history and explicit rejection/modification consequences.
- Allow approval only when no mandatory preflight blocker exists.

#### Out of scope

- G02–G15
- Enterprise RBAC
- Auto approval
- Baseline execution

#### Backend and authority slice

PreflightService, ApprovalService using the existing Transition Service, GateBindingValidator, and PreflightExpiryService.

#### Persistence

Persist preflights, approval_gates, user_decisions, gate versions, artifact-set checksums, state versions, and expiry.

#### API contract

`POST /api/v1/preflights`, `GET /api/v1/preflights/{id}`, `POST /api/v1/runs/drafts/{draftId}/approvals/{gateId}/decisions`.

#### Durable events

PREFLIGHT_CREATED, APPROVAL_GATE_CREATED, G01_APPROVED, G01_REJECTED, G01_MODIFICATION_REQUESTED, APPROVAL_MARKED_STALE.

#### Artifact evidence

`preflight_request.json`, `preflight_result.json`, `environment_capability_summary.json`, `path_safety_report.json`, `eligibility_result.json`, and `g01_evidence_index.json`.

#### Frontend slice

G01 review page with evidence index, checksums, warnings, blockers, comment, decisions, stale-state handling, and no auto-approval control.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Sub-issues


#### S1-F05-I01 — Backend / Domain: Create a checksum-bound production preflight and decide G01

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F05 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F01, S1-F02, S1-F03, S1-F04
- **Estimate:** M
- **Risk:** High


#### S1-F05-I02 — Database / API / Event / Artifact: Create a checksum-bound production preflight and decide G01

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F05 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F01, S1-F02, S1-F03, S1-F04
- **Estimate:** M
- **Risk:** High


#### S1-F05-I03 — Frontend: Create a checksum-bound production preflight and decide G01

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F05 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F01, S1-F02, S1-F03, S1-F04
- **Estimate:** M
- **Risk:** Low


#### S1-F05-I04 — Testing / Security / Documentation: Create a checksum-bound production preflight and decide G01

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F05 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F01, S1-F02, S1-F03, S1-F04
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given valid evidence with no blocker, when a reviewer approves G01, then the decision is persisted and the legal transition is requested.
- Given a blocker, when approval is attempted, then the backend rejects it and the blocker remains failed.
- Given source metadata, policy, target, reservation, or an artifact changes, when an old decision is submitted, then it is rejected as stale.
- Given duplicate identical approval submission, when retried with the same idempotency key, then the original result is returned.
- Given browser refresh or backend restart, when G01 is waiting, then the exact pending gate and evidence package are restored.

#### Manual end-to-end test

Review and approve a clean G01 package; then change the target family or source file and retry the old decision to prove staleness. Reject a blocked AngularJS source and confirm no run can be created.

#### Dependencies

- S1-F01
- S1-F02
- S1-F03
- S1-F04

#### Risks and edge cases

- Approval replay
- Evidence-set drift
- Target reservation expiry
- Confusing warnings with blockers
- Duplicate decisions

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F06 — Create the real authoritative run and hand off to LangGraph safely

**Feature type:** Workflow capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

After G01 approval, a user can create one real migration run, see it become the single active mutating run, and observe LangGraph coordinate real source-intake services without owning state or execution.

#### Context

Sprint 0 created a mock run and six-phase mock graph. Sprint 1 replaces the production start path with a real run aggregate and real preflight/snapshot nodes while retaining mock mode for tests only.

#### Scope

- Create a real run only from a current approved G01 decision.
- Persist strict-parity constraints, target Angular 21.x as the approved MVP target, policy versions, pricing snapshot, source/target references, and actor identity.
- Enforce one active mutating run and target ownership using the existing lease foundation.
- Create the run artifact namespace transactionally or compensate safely.
- Update JobSupervisor to start the production LangGraph thread.
- Replace mock preflight and run-creation nodes with thin adapters that call real application services.
- Reconstruct graph routing from SQLite after restart; keep LangGraph checkpoints as resume hints only.
- Keep the mock workflow accessible only through explicit test/demo configuration.

#### Out of scope

- Snapshot implementation
- Baseline commands
- Stage graph
- Repair graph
- Distributed workers

#### Backend and authority slice

MigrationRunService, JobSupervisor production start path, one-active-run policy, LangGraph source-intake adapter, and startup reconstruction hook.

#### Persistence

Persist migration_runs, active-run claim/lease, policy snapshots, graph thread reference, state version, and initial transition/event.

#### API contract

`POST /api/v1/runs`, `POST /api/v1/runs/{runId}/start`, `GET /api/v1/runs/{runId}/state`.

#### Durable events

RUN_CREATED, RUN_START_ACCEPTED, RUN_STARTED, RUN_START_REJECTED, RUN_RECONSTRUCTED.

#### Artifact evidence

`create_run_request.json`, `client_constraints.json`, `target_policy.json`, `run_policy_snapshot.json`, and `run_initial_state.json`.

#### Frontend slice

Start action consumes the approved preflight and shows accepted/running/waiting states from backend events; it does not locally mark snapshot or baseline complete.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Sub-issues


#### S1-F06-I01 — Backend / Domain: Create the real authoritative run and hand off to LangGraph safely

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F06 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F05, Sprint 0 JobSupervisor, leases, LangGraph mock graph, Transition Service, SSE
- **Estimate:** M
- **Risk:** High


#### S1-F06-I02 — Database / API / Event / Artifact: Create the real authoritative run and hand off to LangGraph safely

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F06 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F05, Sprint 0 JobSupervisor, leases, LangGraph mock graph, Transition Service, SSE
- **Estimate:** M
- **Risk:** High


#### S1-F06-I03 — Frontend: Create the real authoritative run and hand off to LangGraph safely

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F06 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F05, Sprint 0 JobSupervisor, leases, LangGraph mock graph, Transition Service, SSE
- **Estimate:** M
- **Risk:** Low


#### S1-F06-I04 — Testing / Security / Documentation: Create the real authoritative run and hand off to LangGraph safely

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F06 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F05, Sprint 0 JobSupervisor, leases, LangGraph mock graph, Transition Service, SSE
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given current G01 approval, when run creation is submitted, then exactly one run and initial event are created.
- Given stale or rejected G01, when run creation is submitted, then it is rejected and no partial run directory remains.
- Given an active mutating run exists, when another start is attempted, then it is blocked by the one-active-run policy.
- Given a graph checkpoint is stale, when the backend restarts, then the graph reconstructs from SQLite and does not repeat completed side effects.
- Given the browser disconnects after start acceptance, when it reconnects, then the authoritative state is recovered from snapshot and SSE replay.

#### Manual end-to-end test

Approve G01, start a real run, refresh the browser, restart the backend at a safe waiting boundary, and confirm the run resumes at the authoritative state. Attempt a second run and confirm it is blocked.

#### Dependencies

- S1-F05
- Sprint 0 JobSupervisor, leases, LangGraph mock graph, Transition Service, SSE

#### Risks and edge cases

- Partial run creation
- Duplicate graph start
- Stale G01
- Lease orphaning
- Mock path leaking into production

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F07 — Create and inspect an immutable arbitrary-project source snapshot

**Feature type:** Product capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

A user can create a real product-owned source snapshot, inspect its complete manifest and fingerprint, and see that no command has run in the original source.

#### Context

Sprint 0 provided snapshot/workspace interfaces and fixture-bound copy tests. Sprint 1 must implement safe arbitrary-project snapshotting for the approved real run.

#### Scope

- Freeze the source metadata fingerprint at snapshot start and detect source changes during copy.
- Apply a versioned inclusion/exclusion policy; exclude generated directories such as `node_modules`, `.angular/cache`, `dist`, and `coverage` only when explicitly recorded.
- Handle symlinks, junctions, file locks, long paths, case behavior, and transient copy retries.
- Create snapshot files only under the product-owned snapshot root.
- Generate deterministic file manifest, sizes, content hashes, exclusions, Git metadata where available, and snapshot fingerprint.
- Finalize all snapshot artifacts before requesting a passed transition.
- Quarantine or delete incomplete product-owned copies safely after interruption.

#### Out of scope

- Mutable baseline workspace
- G02 decision
- Dependency installation
- Stage sandboxes
- Final delivery

#### Backend and authority slice

SnapshotService, SourceManifestBuilder, FingerprintService, LinkPolicyInspector, and incomplete-copy cleanup/quarantine service.

#### Persistence

Persist source_snapshots, manifest/fingerprint metadata, copy status, policy version, artifact IDs, and idempotency.

#### API contract

`POST /api/v1/runs/{runId}/snapshots`, `GET /api/v1/runs/{runId}/snapshots/{snapshotId}`.

#### Durable events

SNAPSHOT_STARTED, SNAPSHOT_PROGRESS_UPDATED, SNAPSHOT_CREATED, SNAPSHOT_FAILED, SNAPSHOT_QUARANTINED.

#### Artifact evidence

`source_manifest.json`, `source_git_metadata.json`, `snapshot_manifest.json`, `exclusion_policy_snapshot.json`, `snapshot_copy_report.json`, and `snapshot_fingerprint.json`.

#### Frontend slice

Snapshot progress and detail view with counts, size, exclusions, fingerprint, warnings, interrupted/failed state, and artifact links.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Sub-issues


#### S1-F07-I01 — Backend / Domain: Create and inspect an immutable arbitrary-project source snapshot

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F07 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F06, Sprint 0 SnapshotService/WorkspaceService/Artifact Store foundations
- **Estimate:** M
- **Risk:** High


#### S1-F07-I02 — Database / API / Event / Artifact: Create and inspect an immutable arbitrary-project source snapshot

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F07 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F06, Sprint 0 SnapshotService/WorkspaceService/Artifact Store foundations
- **Estimate:** M
- **Risk:** High


#### S1-F07-I03 — Frontend: Create and inspect an immutable arbitrary-project source snapshot

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F07 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F06, Sprint 0 SnapshotService/WorkspaceService/Artifact Store foundations
- **Estimate:** M
- **Risk:** Low


#### S1-F07-I04 — Testing / Security / Documentation: Create and inspect an immutable arbitrary-project source snapshot

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F07 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F06, Sprint 0 SnapshotService/WorkspaceService/Artifact Store foundations
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given an approved run and stable source, when snapshotting completes, then every included file is represented in the manifest and the snapshot fingerprint is stored.
- Given the source changes during copy, when verification runs, then snapshot completion is rejected and the partial copy is quarantined or safely removed.
- Given a link escapes the source root, when encountered, then snapshotting fails closed.
- Given snapshotting is cancelled, when cleanup completes, then no incomplete snapshot is marked valid.
- Given the same idempotency key is retried after success, when submitted, then the existing snapshot result is returned without recopying.

#### Manual end-to-end test

Create a snapshot of the real Angular fixture, inspect manifest/exclusions/fingerprint, then modify a source file during a controlled slow copy and confirm the snapshot is not accepted.

#### Dependencies

- S1-F06
- Sprint 0 SnapshotService/WorkspaceService/Artifact Store foundations

#### Risks and edge cases

- Large repositories
- Source mutation during copy
- Windows locked files
- Junction escapes
- Hashing cost
- Disk exhaustion

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F08 — Review G02 and establish the immutable source-integrity boundary

**Feature type:** Approval capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

A reviewer can inspect the exact snapshot evidence, approve or reject G02, and prove the original source fingerprint still matches the approved pre-snapshot state.

#### Context

Snapshot creation and snapshot acceptance are separate responsibilities. G02 must bind the immutable snapshot, source integrity proof, and current state before any baseline workspace or command is permitted.

#### Scope

- Generate source integrity before/after evidence using the versioned fingerprint policy.
- Create a G02 evidence index containing snapshot manifest, exclusions, copy report, Git metadata, and fingerprints.
- Bind G02 to run, gate version, state version, source fingerprint, snapshot fingerprint, artifact-set checksum, actor, and policy version.
- Implement approved, approved_with_comment, modification_requested, and rejected decisions.
- Mark G02 stale if source, snapshot, policy, or evidence changes.
- Block baseline workspace creation while G02 is pending, rejected, stale, or missing.
- Persist the snapshot as the only allowed input boundary for baseline.

#### Out of scope

- Baseline workspace creation
- Runtime selection
- Final source-integrity check
- G03

#### Backend and authority slice

SourceIntegrityVerifier, G02 ApprovalPackageBuilder, ApprovalService bindings, and TransitionPolicy updates.

#### Persistence

Persist integrity checks, G02 gate/decisions, snapshot input boundary, artifact-set checksum, and staleness reason.

#### API contract

`GET /api/v1/runs/{runId}/approvals/{gateId}`, `POST /api/v1/runs/{runId}/approvals/{gateId}/decisions`.

#### Durable events

SOURCE_INTEGRITY_VERIFIED, SOURCE_INTEGRITY_FAILED, G02_CREATED, G02_APPROVED, G02_REJECTED, G02_STALE.

#### Artifact evidence

`source_integrity_before.json`, `source_integrity_after_snapshot.json`, `source_read_only_verification.json`, and `g02_evidence_index.json`.

#### Frontend slice

G02 review view with source/snapshot fingerprint comparison, exclusions, warnings, decision controls, stale handling, and blocked next-step indicator.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Sub-issues


#### S1-F08-I01 — Backend / Domain: Review G02 and establish the immutable source-integrity boundary

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F08 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F07
- **Estimate:** M
- **Risk:** High


#### S1-F08-I02 — Database / API / Event / Artifact: Review G02 and establish the immutable source-integrity boundary

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F08 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F07
- **Estimate:** M
- **Risk:** High


#### S1-F08-I03 — Frontend: Review G02 and establish the immutable source-integrity boundary

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F08 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F07
- **Estimate:** M
- **Risk:** Low


#### S1-F08-I04 — Testing / Security / Documentation: Review G02 and establish the immutable source-integrity boundary

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F08 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F07
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given matching source and snapshot evidence, when G02 is approved, then the snapshot becomes the baseline input boundary.
- Given the original source changed, when approval is attempted, then the integrity gate fails and cannot be overridden into passed.
- Given G02 is pending or stale, when baseline workspace creation is attempted, then the backend rejects it.
- Given an artifact is replaced or its checksum changes, when an old decision is replayed, then it is rejected as stale.
- Given backend restart while waiting, when the run is reopened, then the exact G02 package and state are restored.

#### Manual end-to-end test

Approve a valid G02 package, then repeat with a changed source and with a tampered manifest checksum. Confirm both are blocked and no baseline workspace is created.

#### Dependencies

- S1-F07

#### Risks and edge cases

- Source hash instability
- Approval replay
- Tampered evidence
- Incorrect exclusion policy
- Baseline starting before approval

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F09 — Resolve and approve the source-compatible ExecutionProfile

**Feature type:** Execution capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

A reviewer can see which exact Node/npm/npx runtime will reproduce the Angular 18 source baseline and why incompatible or unavailable profiles are blocked.

#### Context

Angular versions have specific Node, TypeScript, and RxJS compatibility ranges. Sprint 0 created runtime-profile contracts; Sprint 1 must select a real exact source profile without depending on the host default runtime or an LLM guess.

#### Scope

- Load a versioned source-runtime compatibility policy derived from official Angular compatibility data.
- Match the detected exact Angular source version to approved runtime candidate constraints.
- Select an exact paired Node/npm/npx installation from S1-F02 inventory.
- Validate local Angular CLI/package metadata, OS, architecture, registry, proxy, certificate, environment allowlist, cache policy, and network profile.
- Persist the exact immutable ExecutionProfile checksum.
- Provide manual preparation guidance when no compatible profile exists; do not automatically download unapproved runtimes.
- Require an explicit runtime-selection confirmation before baseline commands when multiple approved candidates exist.

#### Out of scope

- Angular 19/20/21 stage profiles
- Historical compatibility catalogue promotion
- Automatic runtime installation
- Target exact version resolution

#### Backend and authority slice

SourceRuntimeResolver, ExecutionProfileRegistry real adapter, RuntimePolicyLoader, and profile confirmation service.

#### Persistence

Persist compatibility-policy version, candidate profiles, selected exact profile, validation timestamp, checksum, and decision.

#### API contract

`POST /api/v1/runs/{runId}/execution-profiles/resolve`, `GET /api/v1/runs/{runId}/execution-profiles`, `POST /api/v1/runs/{runId}/execution-profiles/{id}/select`.

#### Durable events

EXECUTION_PROFILE_RESOLUTION_STARTED, EXECUTION_PROFILE_RESOLVED, EXECUTION_PROFILE_BLOCKED, EXECUTION_PROFILE_SELECTED.

#### Artifact evidence

`source_runtime_resolution.json`, `execution_profile.json`, `runtime_validation_report.json`, and `runtime_environment_redacted.json`.

#### Frontend slice

Runtime candidates table, compatibility rationale, exact executable paths sanitized for display, selection action, blocked guidance, and selected checksum.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Sub-issues


#### S1-F09-I01 — Backend / Domain: Resolve and approve the source-compatible ExecutionProfile

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F09 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F02, S1-F04, S1-F08
- **Estimate:** M
- **Risk:** High


#### S1-F09-I02 — Database / API / Event / Artifact: Resolve and approve the source-compatible ExecutionProfile

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F09 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F02, S1-F04, S1-F08
- **Estimate:** M
- **Risk:** High


#### S1-F09-I03 — Frontend: Resolve and approve the source-compatible ExecutionProfile

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F09 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F02, S1-F04, S1-F08
- **Estimate:** M
- **Risk:** Low


#### S1-F09-I04 — Testing / Security / Documentation: Resolve and approve the source-compatible ExecutionProfile

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F09 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F02, S1-F04, S1-F08
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given a compatible Angular 18 source and approved runtime candidate, when resolution runs, then an exact immutable profile is produced.
- Given only the host default runtime is incompatible, when resolution runs, then baseline is blocked rather than using it silently.
- Given multiple compatible profiles, when one is selected, then the selection and checksum are persisted and other profiles remain evidence only.
- Given the executable or policy changes after selection, when baseline start is attempted, then the profile is stale and must be resolved again.
- Given no profile exists, when resolution fails, then the UI presents environment preparation guidance and no code repair is proposed.

#### Manual end-to-end test

Resolve a compatible profile for Angular 18, select it, inspect exact versions, then remove or invalidate the selected npm path and confirm baseline becomes blocked.

#### Dependencies

- S1-F02
- S1-F04
- S1-F08

#### Risks and edge cases

- Multiple Node installations
- Corporate runtime restrictions
- Compatibility policy drift
- Executable replacement
- Native dependency differences

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F10 — Create the baseline sandbox and prequalify package, lockfile, registry, and lifecycle scripts

**Feature type:** Execution capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

A reviewer can create a mutable baseline sandbox from the approved snapshot and see whether npm metadata and install behavior are safe and reproducible before installation.

#### Context

The original source and immutable snapshot must never be command working directories. Before `npm ci`, package sources, lockfile consistency, registry readiness, and lifecycle scripts must be evaluated deterministically.

#### Scope

- Create a physical baseline sandbox from the G02-approved snapshot.
- Exclude `node_modules` and generated caches from copy; verify the baseline input fingerprint matches the approved snapshot policy.
- Validate `package.json` and `package-lock.json` parseability and consistency without rewriting either file.
- Inventory public/private registry, Git, tarball, local-file, workspace, and unknown dependency sources.
- Audit root lifecycle scripts and available package metadata; classify allowed, restricted, requires_review, blocked, or unknown.
- Validate registry/proxy/certificate/private-package capability in the selected ExecutionProfile.
- Create a baseline-install authorization result and an explicit human decision when sensitive scripts require review.
- Block unsupported package managers for the Sprint 1 MVP.

#### Out of scope

- Dependency vulnerability scanning
- Automatic lockfile regeneration
- Peer-dependency repair
- Actual installation
- Angular update

#### Backend and authority slice

BaselineWorkspaceService, PackageMetadataInspector, LockfilePrequalificationService, PackageSourceInventory, LifecycleScriptAuditor, and install-authorization service.

#### Persistence

Persist baseline workspace record, input fingerprint, lockfile result, source inventory, script audit, authorization decision, and artifact references.

#### API contract

`POST /api/v1/runs/{runId}/baseline/workspace`, `POST /api/v1/runs/{runId}/baseline/prequalify`, `POST /api/v1/runs/{runId}/baseline/install-authorizations`.

#### Durable events

BASELINE_WORKSPACE_STARTED, BASELINE_WORKSPACE_READY, LOCKFILE_PREQUALIFICATION_COMPLETED, LIFECYCLE_SCRIPT_REVIEW_REQUIRED, BASELINE_INSTALL_AUTHORIZED, BASELINE_INSTALL_BLOCKED.

#### Artifact evidence

`baseline_workspace_manifest.json`, `lockfile_prequalification.json`, `package_source_inventory.json`, `package_install_script_audit.json`, `registry_readiness.json`, and `baseline_install_authorization.json`.

#### Frontend slice

Baseline preparation page with workspace fingerprint, lockfile state, dependency-source categories, lifecycle scripts, registry readiness, decision controls, and blockers.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Sub-issues


#### S1-F10-I01 — Backend / Domain: Create the baseline sandbox and prequalify package, lockfile, registry, and lifecycle scripts

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F10 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F08, S1-F09
- **Estimate:** M
- **Risk:** High


#### S1-F10-I02 — Database / API / Event / Artifact: Create the baseline sandbox and prequalify package, lockfile, registry, and lifecycle scripts

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F10 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F08, S1-F09
- **Estimate:** M
- **Risk:** High


#### S1-F10-I03 — Frontend: Create the baseline sandbox and prequalify package, lockfile, registry, and lifecycle scripts

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F10 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F08, S1-F09
- **Estimate:** M
- **Risk:** Low


#### S1-F10-I04 — Testing / Security / Documentation: Create the baseline sandbox and prequalify package, lockfile, registry, and lifecycle scripts

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F10 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F08, S1-F09
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given approved G02 and selected ExecutionProfile, when baseline workspace creation completes, then it is a separate product-owned writable directory with the expected fingerprint.
- Given `package.json` and lockfile disagree, when prequalification runs, then the result is blocked and neither file is modified.
- Given an unapproved Git/tarball/local dependency source, when audited, then installation is blocked or explicitly review-required according to policy.
- Given a sensitive lifecycle script, when no authorization exists, then `npm ci` cannot start.
- Given cancellation during copy, when recovery runs, then the incomplete baseline workspace is reconstructed from the approved snapshot.

#### Manual end-to-end test

Create the baseline sandbox, inspect package and script evidence, approve a controlled review-required script, then test invalid lockfile and unapproved dependency-source fixtures and confirm no install begins.

#### Dependencies

- S1-F08
- S1-F09

#### Risks and edge cases

- Lockfile format differences
- Hidden npm configuration
- Private registry availability
- Malicious lifecycle scripts
- Baseline copy drift

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F11 — Execute and inspect the frozen baseline clean installation

**Feature type:** Execution capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

A user can run the approved `npm ci` baseline command through the sole CommandExecutor, watch live logs, cancel it, and inspect immutable completion evidence without source mutation.

#### Context

Sprint 0 created the structured command and supervisor shell. Sprint 1 productionizes one real mutating command inside the approved baseline sandbox. `npm ci` is used because the MVP requires npm plus a valid committed lockfile and must not silently rewrite it.

#### Scope

- Register an exact `npm ci` command template with `shell=false`, explicit executable, arguments, working-directory alias, ExecutionProfile, timeout, network profile, environment allowlist, recovery category, and idempotency.
- Execute only after G02, profile selection, baseline workspace readiness, and install authorization.
- Persist complete stdout/stderr and bounded SSE log chunks.
- Capture npm debug logs, exit code, start/end fingerprints, duration, process identity, cancellation, timeout, and environment blocker classification.
- Verify `package.json` and `package-lock.json` remain unchanged after installation.
- Run dependency-tree verification after success.
- Reconstruct the baseline workspace after interruption when trust cannot be proven.

#### Out of scope

- `npm install` fallback
- `--force`
- `--legacy-peer-deps`
- Automatic dependency changes
- Build/test/lint

#### Backend and authority slice

Command Policy Engine production rule, CommandExecutor real npm path, ProcessController, JobSupervisor ownership, npm result parser, and recovery classifier.

#### Persistence

Persist command_executions, worker lease, runtime checksum, status, exit code, log artifacts, fingerprints, cancellation/timeout, and idempotency.

#### API contract

`POST /api/v1/runs/{runId}/baseline/install`, `GET /api/v1/runs/{runId}/commands/{executionId}`, log artifact endpoints, and existing cancellation endpoint.

#### Durable events

COMMAND_QUEUED, COMMAND_STARTED, COMMAND_OUTPUT_AVAILABLE, BASELINE_INSTALL_SUCCEEDED, BASELINE_INSTALL_FAILED, COMMAND_CANCELLED, COMMAND_INTERRUPTED.

#### Artifact evidence

`npm-ci-command.json`, full stdout/stderr logs, npm debug logs, `dependency_tree_verification.json`, `lockfile_post_install_verification.json`, and `baseline_install_summary.json`.

#### Frontend slice

Install command card, live log viewer, elapsed time, cancel action, reconnect behavior, result summary, artifacts, and environment-vs-project failure presentation.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Sub-issues


#### S1-F11-I01 — Backend / Domain: Execute and inspect the frozen baseline clean installation

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F11 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F10, Sprint 0 CommandExecutor/ProcessController/SSE/log viewer foundations
- **Estimate:** M
- **Risk:** High


#### S1-F11-I02 — Database / API / Event / Artifact: Execute and inspect the frozen baseline clean installation

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F11 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F10, Sprint 0 CommandExecutor/ProcessController/SSE/log viewer foundations
- **Estimate:** M
- **Risk:** High


#### S1-F11-I03 — Frontend: Execute and inspect the frozen baseline clean installation

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F11 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F10, Sprint 0 CommandExecutor/ProcessController/SSE/log viewer foundations
- **Estimate:** M
- **Risk:** Low


#### S1-F11-I04 — Testing / Security / Documentation: Execute and inspect the frozen baseline clean installation

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F11 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F10, Sprint 0 CommandExecutor/ProcessController/SSE/log viewer foundations
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given all prerequisites, when baseline install starts, then the exact registered command runs once inside the baseline sandbox.
- Given raw shell text or forbidden flags, when requested, then Command Policy rejects the request before process creation.
- Given a lockfile mismatch, when install is requested, then no command starts.
- Given cancellation, when the process tree is terminated, then partial logs are finalized and the workspace is classified for reconstruction.
- Given success, when post-install verification runs, then package and lockfile hashes are unchanged and dependency-tree evidence exists.
- Given browser refresh, when the command is still running, then live state resumes from backend snapshot/events without cancelling the process.

#### Manual end-to-end test

Run `npm ci` on the clean fixture, refresh during execution, inspect logs and dependency tree, then cancel a controlled slow install fixture and confirm process-tree termination and safe reconstruction.

#### Dependencies

- S1-F10
- Sprint 0 CommandExecutor/ProcessController/SSE/log viewer foundations

#### Risks and edge cases

- Lifecycle script child processes
- Huge logs
- Proxy/certificate failure
- Native package compilation
- Cancellation leaving partial state

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F12 — Execute the baseline build, test, and lint matrix

**Feature type:** Validation capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

A reviewer can see every discovered baseline build, test, and lint target and its real executed, not-configured, blocked, passed, or failed status.

#### Context

Baseline qualification must record the source application’s real pre-migration behavior. Existing project targets are reused; the platform does not invent tests or change the test framework.

#### Scope

- Discover required application build targets and configurations from `angular.json` and approved package scripts.
- Discover configured tests and lint without treating missing configuration as passed.
- Create registered structured commands for each approved target using the selected ExecutionProfile and baseline sandbox.
- Execute production build, complete configured tests, and conditional lint with timeouts, cancellation, immutable logs, and command evidence.
- Record statuses using the authoritative vocabulary: passed, failed, skipped_not_configured, skipped_not_applicable, blocked, interrupted, or cancelled.
- Capture command durations, warning summaries, exit codes, test counts where parsable, and output locations without treating generated output as source evidence.
- Preserve the package/lockfile fingerprints established by the clean install.

#### Out of scope

- Changing test assertions
- Adding missing tests
- Browser/visual automation
- External quality/security scanners
- Angular migration validation

#### Backend and authority slice

BaselineTargetDiscoveryService, registered build/test/lint commands, CommandExecutor reuse, parsers, and ValidationService baseline mode.

#### Persistence

Persist baseline steps, target inventory, command executions, result status, parser summaries, artifact refs, and state versions.

#### API contract

`GET /api/v1/runs/{runId}/baseline/targets`, `POST /api/v1/runs/{runId}/baseline/builds`, `/tests`, `/lint`, and result endpoints.

#### Durable events

BASELINE_TARGETS_DISCOVERED, BASELINE_BUILD_STARTED/COMPLETED, BASELINE_TESTS_STARTED/COMPLETED, BASELINE_LINT_STARTED/COMPLETED.

#### Artifact evidence

`baseline_target_inventory.json`, per-command logs, `baseline_build_report.json`, `baseline_test_report.json`, `baseline_lint_report.json`, and generated-output inventory.

#### Frontend slice

Validation matrix with target/configuration, command, status, duration, counts, warnings, artifacts, cancel/retry controls, and honest not-configured/manual/deferred labels.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Sub-issues


#### S1-F12-I01 — Backend / Domain: Execute the baseline build, test, and lint matrix

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F12 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F11
- **Estimate:** M
- **Risk:** High


#### S1-F12-I02 — Database / API / Event / Artifact: Execute the baseline build, test, and lint matrix

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F12 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F11
- **Estimate:** M
- **Risk:** High


#### S1-F12-I03 — Frontend: Execute the baseline build, test, and lint matrix

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F12 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F11
- **Estimate:** M
- **Risk:** Low


#### S1-F12-I04 — Testing / Security / Documentation: Execute the baseline build, test, and lint matrix

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F12 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F11
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given a configured production build, when executed, then its exact command and result are persisted and visible.
- Given no lint target exists, when baseline validation completes, then lint is `skipped_not_configured`, not passed.
- Given a test fails, when parsing completes, then the failed tests and raw logs are preserved without modifying tests.
- Given cancellation, when a target stops, then later targets are not started unless policy explicitly permits and state remains legal.
- Given an unsupported custom target, when discovered, then it is blocked or review-required rather than silently skipped.

#### Manual end-to-end test

Run build, tests, and lint on the clean fixture, then use fixtures with failing tests, missing lint, and custom builder; verify every status and artifact is honest and source files remain unchanged.

#### Dependencies

- S1-F11

#### Risks and edge cases

- Watch mode hanging
- Multiple projects
- Custom builders
- Test flakiness
- Large generated output
- False pass for missing tools

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F13 — Capture baseline parity anchors and fingerprint pre-existing failures

**Feature type:** Validation capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** Medium

#### User-observable outcome

A reviewer can inspect stable baseline fingerprints for failures, routes, and backend-integration anchors so later migration stages can distinguish existing problems from new regressions.

#### Context

G03 requires more than command exit codes. The platform needs minimum deterministic baseline anchors while deeper application analysis remains in Sprint 2.

#### Scope

- Normalize baseline install/build/test/lint failures into stable fingerprints using deterministic parsers.
- Classify origin at baseline as pre-existing and store severity/count/group metadata.
- Build a lightweight structural route inventory from Angular configuration and obvious route declarations without AI interpretation.
- Build a lightweight backend-integration snapshot of environment API roots, proxy configuration, interceptor/service endpoint indicators, and authentication-related file references.
- Record test/lint/build target inventory and package/runtime identities as baseline anchors.
- Label every claim as machine_proven, user_attested_only, not_configured, blocked_by_environment, or unknown.
- Generate comparison-ready schema versions for later stages.

#### Out of scope

- Deep semantic route analysis
- Full API contract extraction
- Functional parity conclusion
- AI Analysis Agent
- Migration-caused failure classification

#### Backend and authority slice

BaselineFailureFingerprintService, baseline parsers, RouteInventoryBuilder minimal mode, BackendContractSnapshotBuilder minimal mode, and evidence-confidence service.

#### Persistence

Persist failure fingerprints, diagnostics, anchor summaries, confidence labels, source artifact refs, and schema versions.

#### API contract

`GET /api/v1/runs/{runId}/baseline/failures`, `/routes`, `/backend-integration`, and `/anchors`.

#### Durable events

BASELINE_FAILURES_FINGERPRINTED, BASELINE_ROUTE_ANCHOR_CREATED, BASELINE_BACKEND_ANCHOR_CREATED.

#### Artifact evidence

`known_baseline_failures.json`, `baseline_route_inventory.json`, `baseline_backend_integration_snapshot.json`, `baseline_anchor_manifest.json`, and parser diagnostics.

#### Frontend slice

Baseline evidence tabs for known failures, routes, backend integration, confidence labels, and artifact provenance.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Sub-issues


#### S1-F13-I01 — Backend / Domain: Capture baseline parity anchors and fingerprint pre-existing failures

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F13 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F12
- **Estimate:** M
- **Risk:** Medium


#### S1-F13-I02 — Database / API / Event / Artifact: Capture baseline parity anchors and fingerprint pre-existing failures

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F13 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F12
- **Estimate:** M
- **Risk:** Medium


#### S1-F13-I03 — Frontend: Capture baseline parity anchors and fingerprint pre-existing failures

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F13 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F12
- **Estimate:** M
- **Risk:** Low


#### S1-F13-I04 — Testing / Security / Documentation: Capture baseline parity anchors and fingerprint pre-existing failures

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F13 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F12
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given the same normalized failure occurs twice, when fingerprinted, then it produces the same stable fingerprint under the same parser version.
- Given a baseline failure exists, when displayed, then it is labeled pre-existing and is not called migration-caused.
- Given automated route/backend evidence is incomplete, when reported, then the claim is `NOT_PROVEN` or the equivalent confidence status rather than inferred as verified.
- Given sensitive auth/API files are detected, when displayed, then their risk is visible but file contents and secrets are not exposed unnecessarily.
- Given parser version changes, when evidence is regenerated, then a new schema/policy version is recorded.

#### Manual end-to-end test

Run a known-failure fixture, inspect stable fingerprints and evidence confidence, then rerun and confirm stable identity. Inspect route/backend anchors and verify they are presented as structural evidence, not full parity proof.

#### Dependencies

- S1-F12

#### Risks and edge cases

- Unstable error text
- Overclaiming parity
- Secret leakage in endpoint snapshots
- Route patterns missed
- Parser-version drift

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.

---

### S1-F14 — Qualify the baseline and decide G03

**Feature type:** Approval capability  
**Priority:** Must  
**Estimate:** M  
**Risk:** High

#### User-observable outcome

A reviewer can see a complete baseline qualification package, choose strict-clean or qualified-known-failure policy where allowed, and approve, request modification, or reject G03.

#### Context

Sprint 1 ends at an approved source baseline, not merely completed commands. G03 creates the proven boundary from which Sprint 2 discovery and analysis may proceed.

#### Scope

- Aggregate runtime, install, build, tests, lint, route/backend anchors, known failures, environment blockers, manual/deferred items, source integrity, and evidence confidence.
- Produce one of: qualified, qualified_with_known_failures, reproducibility_degraded, blocked_by_environment, or blocked_by_project.
- Support strict-clean baseline and qualified-known-failure policy only when company policy permits and all known failures are fingerprinted.
- Create G03 with evidence-set checksum, state version, baseline workspace fingerprint, ExecutionProfile checksum, actor, policy version, and expiry/staleness rules.
- Ensure approval cannot turn a failed mandatory install/build gate into passed.
- After approval, transition to a Sprint 2-ready discovery boundary; no Angular update or plan execution begins.
- Generate a Sprint 1 evidence index and operator summary.

#### Out of scope

- G04 analysis approval
- Compatibility feasibility
- Migration plan
- Angular update
- Repair
- Final report

#### Backend and authority slice

BaselineQualificationService, BaselinePolicyService, G03 ApprovalPackageBuilder, ApprovalService, TransitionPolicy, and Sprint1CompletionService.

#### Persistence

Persist baseline qualification, assurance fields, known-failure policy, G03 gate/decisions, workspace/profile fingerprints, evidence checksum, and next-boundary state.

#### API contract

`GET /api/v1/runs/{runId}/baseline/summary`, `POST /api/v1/runs/{runId}/baseline/qualify`, and G03 decision endpoints.

#### Durable events

BASELINE_QUALIFIED, BASELINE_QUALIFIED_WITH_KNOWN_FAILURES, BASELINE_BLOCKED, G03_CREATED, G03_APPROVED, G03_REJECTED, SPRINT1_BOUNDARY_REACHED.

#### Artifact evidence

`baseline_summary.json`, `baseline_qualification.json`, `baseline_assurance_status.json`, `g03_evidence_index.json`, and `sprint1_evidence_manifest.json`.

#### Frontend slice

Baseline review page with all dimensions, policy selector where allowed, blockers, known failures, proof/confidence labels, G03 decisions, and Sprint 2 readiness.

#### End-to-end flow

```text
User action
→ typed Next.js request
→ FastAPI endpoint
→ bounded application service
→ Artifact Store finalization when evidence is produced
→ Transition Service validates and persists legal state
→ durable event commit
→ SSE replay or snapshot refresh
→ authoritative Control Tower result
```

#### Sub-issues


#### S1-F14-I01 — Backend / Domain: Qualify the baseline and decide G03

- **Issue type:** Backend / Domain
- **Technical story:** Implement the bounded application service and deterministic domain rules. Keep routers and LangGraph nodes thin; use the Transition Service for state movement.
- **Scope:** Implement only the S1-F14 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F13
- **Estimate:** M
- **Risk:** High


#### S1-F14-I02 — Database / API / Event / Artifact: Qualify the baseline and decide G03

- **Issue type:** Database / API / Event / Artifact
- **Technical story:** Add or extend Alembic models, repositories, typed API contracts, durable events, idempotency, and checksum-bound artifacts. Preserve short transactions.
- **Scope:** Implement only the S1-F14 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F13
- **Estimate:** M
- **Risk:** High


#### S1-F14-I03 — Frontend: Qualify the baseline and decide G03

- **Issue type:** Frontend
- **Technical story:** Implement the Control Tower projection and user actions using generated API types, authoritative snapshots, and ordered SSE events. Cover loading, empty, running, success, blocked, stale, reconnecting, and failure states.
- **Scope:** Implement only the S1-F14 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F13
- **Estimate:** M
- **Risk:** Low


#### S1-F14-I04 — Testing / Security / Documentation: Qualify the baseline and decide G03

- **Issue type:** Testing / Security / Documentation
- **Technical story:** Add unit, API integration, frontend component, SSE/restart, source-safety, and security tests plus the exact UI manual scenario and documentation updates.
- **Scope:** Implement only the S1-F14 contract described above; do not absorb later features.
- **Likely components:** Backend service/domain/repository/API/event/artifact modules or the matching frontend/test modules for this issue type.
- **Input contract:** Validated IDs, expected state version for mutations, idempotency key, actor/correlation metadata, prerequisite artifact IDs/checksums, and the feature-specific request.
- **Output contract:** Typed status/result, new authoritative state version when applicable, durable event sequence, artifact references, and stable error codes.
- **Security:** Enforce authorization hooks, secret redaction, path/workspace confinement, artifact-by-ID access, no raw shell, no direct graph/LLM mutation, and fail-closed integrity checks.
- **Automated tests:** Happy path, invalid input, stale state, duplicate idempotency, missing prerequisite/approval, backend failure, and one authority-bypass/security negative appropriate to the feature.
- **Manual contribution:** Supports the parent feature's UI-driven manual scenario and exposes inspectable state, event, database/API, and artifact evidence.
- **Dependencies:** S1-F13
- **Estimate:** S
- **Risk:** Medium

#### Feature acceptance criteria

- Given clean mandatory gates, when qualification runs, then status is qualified and G03 can be approved.
- Given approved known baseline failures, when all fingerprints are stable and policy allows, then status is qualified_with_known_failures and the UI never labels it clean.
- Given install or required build failed, when a reviewer attempts approval, then the core failure remains failed and progression is blocked.
- Given an evidence artifact, workspace fingerprint, ExecutionProfile, or policy changes, when an old G03 decision is submitted, then it is stale.
- Given G03 approval, when Sprint 1 completes, then the run is ready for Sprint 2 discovery and no migration command is scheduled.

#### Manual end-to-end test

Qualify and approve the clean fixture, qualify a controlled known-test-failure fixture under the explicit policy, then attempt to approve a failed install/build fixture and confirm it remains blocked.

#### Dependencies

- S1-F13

#### Risks and edge cases

- Known failure treated as clean
- Approval bypassing core gates
- Stale evidence
- Baseline workspace mutation
- Confusing Sprint 2 readiness with migration success

#### Feature Definition of Done

- Backend/domain behavior works through the authoritative application-service path.
- Database migration and repository changes are complete where required.
- API and stable error contracts are documented and included in generated frontend types.
- Required artifacts are finalized, SHA-256 registered, immutable, and retrievable by artifact ID before a passed transition.
- Durable events commit with/after authoritative state and replay correctly.
- Frontend works in the same sprint and never advances workflow state locally.
- Loading, empty, running, success, blocked, stale, reconnecting, and failure states are visible as relevant.
- Automated and manual tests pass, including the listed negative case.
- Source immutability, security, Windows behavior, and recovery boundaries are verified where relevant.
- Documentation and traceability are updated without bypassing any authority boundary.


---

### 9. Sprint integration tests

1. **Sprint 0 upgrade test:** Apply the authoritative contract migration to a Sprint 0 database and prove state/event history remains readable.
2. **No-auto-approval test:** Attempt all production auto-approval routes and prove no gate advances.
3. **Real source-intake API test:** FastAPI + temporary SQLite/WAL + temporary Artifact Store from path validation through G03.
4. **Source safety matrix:** Windows drive/case, nesting, long path, symlink, junction, source-change-during-copy, locked file, and target-reservation conflicts.
5. **Eligibility matrix:** Angular 18.0.x, 18.1.x, 18.2.x, AngularJS, Angular 10, Angular 11–17 policy classification, multi-app, custom builder, Nx, malformed JSON, and version conflicts.
6. **Approval integrity:** G01, G02, and G03 stale state, stale checksum, duplicate decision, rejection, modification request, restart, and non-bypassable core failures.
7. **Runtime profile:** Compatible candidate, mixed executable pair, missing candidate, changed executable, policy version change, and secret redaction.
8. **Baseline package safety:** Valid lockfile, mismatch, missing lockfile, unapproved package source, sensitive lifecycle script, registry unavailable, and private-auth missing.
9. **Real subprocess suite:** `npm ci`, build, tests, lint, timeout, cancellation, process-tree termination, large logs, and browser refresh.
10. **Known failure stability:** The same controlled baseline failure yields the same fingerprint under the same parser version.
11. **Recovery:** Backend restart at G01/G02/G03 waits, interrupted snapshot reconstruction, interrupted install reconstruction, and graph checkpoint reconciliation with SQLite.
12. **Authority regression:** LangGraph, UI, LLM mock, and agents cannot write authoritative state, execute raw commands, apply approvals, or mutate source.

---

### 10. Sprint manual demonstration

```text
1. Start the already-built Sprint 0 backend and frontend after applying the Sprint 1 contract migration.
2. Open the health/environment view and inspect real paired Node/npm/npx, Git, SQLite/WAL, Artifact Store, proxy, and certificate readiness.
3. Select a real Angular 18.x source and a safe target.
4. Validate safe paths; demonstrate a target-inside-source blocker and a Windows junction blocker.
5. Analyze the source and display exact Angular/CLI versions, Angular family, npm lockfile, projects, and topology.
6. Review the real preflight package and approve G01.
7. Create the real run; prove a second active mutating run is blocked.
8. Create the immutable snapshot, inspect manifest/exclusions/fingerprint, and approve G02.
9. Resolve and select the exact source ExecutionProfile.
10. Create the baseline sandbox and inspect lockfile, package-source, registry, and lifecycle-script evidence.
11. Run real npm ci through CommandExecutor and watch logs through SSE.
12. Refresh the browser during the command and recover the same state.
13. Run build, tests, and lint according to discovered configuration.
14. Inspect known baseline failure fingerprints plus route/backend structural anchors.
15. Qualify the baseline and approve G03.
16. Demonstrate a controlled known-failure baseline and a failed mandatory build that cannot be approved into passed.
17. Cancel a controlled long-running baseline command and verify process-tree termination and reconstruction.
18. Confirm the original source fingerprint remains unchanged and migrated-app does not exist.
```

---

### 11. Sprint exit criteria

Sprint 1 is complete only when:

- Sprint 0 infrastructure has been reused rather than reimplemented.
- Authoritative phase/status contracts are active and old combined macro phases are presentation-only or historical.
- Production auto-approval is removed or unreachable.
- Real arbitrary Windows path safety and target reservation work.
- Angular 18.x exact version/family and topology detection work deterministically.
- G01, G02, and G03 block progression, are checksum/state/fingerprint bound, and survive restart.
- One real authoritative run is created from the approved preflight.
- One immutable arbitrary-project source snapshot is created and approved.
- The source-compatible ExecutionProfile is exact, persisted, and used by every baseline command.
- Baseline commands run only in the product-owned baseline sandbox through CommandExecutor.
- `npm ci` does not silently rewrite package metadata or lockfiles.
- Configured build/tests/lint execute and missing checks are not falsely marked passed.
- Known baseline failures and minimum parity anchors are persisted with confidence/proof labels.
- A clean or policy-qualified baseline reaches G03; a failed mandatory install/build cannot be approved into passed.
- Cancellation, restart, SSE replay, idempotency, and source integrity are proven.
- No `ng update`, Angular source transformation, LLM repair, or final publication occurs.

---

### 12. Downstream backlog adjustment

After adopting this revised Sprint 1, the next sprint must remove duplicated baseline foundation work. Sprint 2 should begin from the G03-approved snapshot/baseline boundary and focus on:

```text
deterministic discovery expansion
→ AI Analysis Agent explanation
→ G04 analysis acceptance
→ compatibility catalogue and feasibility
→ G05 feasibility acceptance
→ MigrationPlan and StageExecutionPlan
→ Planning Agent explanation
→ plan revision
→ G06 plan acceptance
```

This preserves the overall architecture while taking advantage of the foundation already delivered in Sprint 0.

---

### 13. Non-negotiable Sprint 1 rules

1. Do not rebuild completed Sprint 0 foundations as new features.
2. Do not let the old mock state vocabulary remain production business truth.
3. Do not allow production auto-approval.
4. Do not mutate the original source or use it as a command working directory.
5. Do not use the immutable snapshot as a mutable baseline workspace.
6. Do not run commands outside CommandExecutor.
7. Do not accept arbitrary shell strings or forbidden npm flags.
8. Do not use an LLM for path safety, version parsing, topology, runtime selection, lockfile validation, or baseline truth.
9. Do not mark an artifact-backed step passed before the artifact is finalized and checksum-registered.
10. Do not treat a missing test/lint/security/browser tool as passed.
11. Do not let a human approval rewrite failed mandatory technical evidence into passed evidence.
12. Do not run `ng update` or any Angular transformation in Sprint 1.
13. Do not publish `migrated-app`.
14. Do not call Angular 21 the latest release; it is the approved MVP target.
15. End at the G03-approved baseline boundary, ready for Sprint 2 discovery and planning.