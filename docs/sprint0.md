# AI Frontend Migration Factory — Complete Sprint 0 Backlog

**Sprint:** Sprint 0 — Platform Skeleton, Contracts, Mock Workflow, Execution Boundaries, and Developer Foundation  
**Project:** AI Frontend Migration Factory — Angular 11+  
**Reference POC:** Angular 18.x → Angular 21.x  
**Migration mode:** Strict compatibility with strict functional-parity constraints  
**Backend application:** Unchanged  
**Mutation policy:** Internal sandbox workspace only  
**Execution authority:** Backend-controlled  
**Orchestration model:** LangGraph-backed deterministic workflow  
**Primary stack:** FastAPI, Next.js, SQLite, LangGraph, Azure OpenAI Gateway abstraction, local artifact store, SSE

---

## 1. Sprint Goal

Create the complete technical foundation of the AI Frontend Migration Factory without executing a real Angular migration.

Sprint 0 must prove that the solution is being built as a reusable migration platform rather than a one-off script. It establishes the repository structure, backend and frontend shells, state and event contracts, persistence model, mock workflow, deterministic component boundaries, AI-agent contracts, artifact model, structured command authority, internal workspace model, cancellation and resume foundations, observability, and developer workflow.

The sprint must make later migration work safer by freezing the core contracts before real Angular analysis, `ng update`, repair, or delivery logic is introduced.

---

## 2. Sprint Objectives

Sprint 0 must establish the following architectural truths:

1. **The backend owns workflow state.** The frontend renders snapshots and ordered events; it does not invent progress.
2. **Deterministic services and AI-assisted agents are different concepts.** Eligibility checks, snapshots, compatibility resolution, command validation, static checks, checkpoints, and delivery are deterministic services.
3. **Agents and LLMs do not execute commands.** They may propose registered actions or patches; the backend validates and executes them.
4. **The original source is immutable.** Future mutations occur only inside an internal run workspace.
5. **Incomplete work is not published.** `migrated-app/` is created only after a successful delivery gate.
6. **State transitions are idempotent and recoverable.** Optimistic state versions, ordered events, worker leases, cancellation, and resume are designed before long-running work begins.
7. **Artifacts are immutable evidence.** They are checksum-bound, stage-scoped, repair-attempt-scoped, and opened by artifact ID rather than arbitrary paths.
8. **Commands are structured.** Raw shell strings are not accepted by the trusted execution layer.
9. **SSE is a delivery mechanism, not the source of truth.** Reconnection and replay are supported, while the state snapshot remains authoritative.
10. **LLM usage is governed.** Secrets are redacted, repository content is untrusted data, usage is measured, and cost is calculated from a pricing snapshot.

---

## 3. Sprint Outcome and Demo

At the end of Sprint 0, the team must be able to:

- start the FastAPI backend locally with Uvicorn;
- start the Next.js Control Tower frontend locally;
- open the migration setup page;
- validate a mock migration configuration before enabling Start;
- create a mock migration run from a valid preflight checksum;
- persist the run snapshot in SQLite;
- execute a six-phase mock workflow through LangGraph;
- receive ordered workflow updates through Server-Sent Events;
- reconnect using `Last-Event-ID` and replay missed events;
- refresh the browser and reconstruct the UI from the backend state snapshot;
- see macro phases, Angular stages, deterministic steps, AI-assisted agents, validation gates, approvals, risks, and assurance statuses;
- switch auto-approval policy and immediately reevaluate the current mock gate;
- cancel a mock run and observe a controlled cancellation sequence;
- resume from a safe mock checkpoint;
- inspect mock command logs, diffs, validation reports, repair attempts, Markdown reports, artifact metadata, and checksums;
- see mock LLM input/output tokens and calculated cost;
- verify that failed or cancelled runs never publish `migrated-app/`;
- confirm that no real `ng update`, arbitrary package installation, real repair, or user-source mutation occurs.

---

## 4. Optimized Sprint 0 Demo Scenario

```text
1. Start FastAPI and Next.js.
2. Open /migrations/new.
3. Select the controlled Angular 18 fixture and a safe target directory.
4. Click Validate Configuration.
5. Backend validates paths, runtime capabilities, and mock topology.
6. Backend returns a checksum-bound preflight result.
7. Start Migration becomes enabled only for that valid, non-expired checksum.
8. Create a mock migration run.
9. Backend creates the state record, event stream, internal workspace metadata,
   snapshot metadata, and artifact directories.
10. LangGraph executes six macro phases:
    - Preflight and Snapshot
    - Discovery and Baseline
    - Feasibility and Planning
    - Staged Migration
    - Final Assurance
    - Delivery and Reporting
11. Independent discovery steps run as a parallel fan-out/fan-in group.
12. Workflow pauses at Analysis / Feasibility Approval.
13. User approves through the backend approval API.
14. Workflow pauses at Plan Approval.
15. User enables Auto Approval.
16. Backend persists the policy and reevaluates the current waiting gate immediately.
17. Mock stages run: Angular 18→19, Angular 19→20, Angular 20→21.
18. Each stage displays deterministic steps separately from AI-assisted agents.
19. Ordered SSE events update the UI.
20. A simulated disconnect reconnects from the last event ID.
21. Duplicate events are ignored; a replay gap triggers snapshot recovery.
22. The user opens a mock command log, stage diff, validation report,
    repair attempt, and final report.
23. The UI displays LLM usage and cost using the configured pricing snapshot.
24. A mock delivery gate publishes the fixture output atomically.
25. The final report shows technical status, parity status, security status,
    quality status, delivery readiness, manual items, and accepted risks.
```

---

## 5. Scope

### 5.1 In Scope

- Repository and module boundaries.
- FastAPI backend shell and thin API routers.
- Next.js Control Tower shell.
- Pydantic v2 contracts and OpenAPI generation.
- SQLAlchemy, Alembic, and SQLite bootstrap.
- Canonical run, phase, stage, and step state model.
- Single state transition service with optimistic concurrency.
- Ordered SSE stream, heartbeat, replay, deduplication, and snapshot recovery.
- LangGraph mock workflow organized into six macro phases.
- Parallel mock discovery fan-out/fan-in.
- Deterministic component contracts and AI-assisted agent contracts.
- Structured command policy and safe local version commands.
- Internal snapshot, workspace, checkpoint, and atomic-delivery abstractions.
- Immutable, checksum-bound local artifact store.
- Runtime and preflight capability checking.
- Auto-approval, approval, cancellation, and resume foundations.
- Azure OpenAI LLM Gateway mock, redaction, usage, budgets, and cost.
- Custom log, diff, Markdown, artifact, approval, and assistant panels.
- Angular 18 fixture and expected baseline/parity manifests.
- Observability and run metrics foundation.
- Developer scripts, tests, documentation, and ADRs.

### 5.2 Out of Scope

| Not in Sprint 0 | Planned later |
|---|---|
| Real arbitrary-project source snapshot and sandbox copy | Sprint 1 |
| Full real source/target validation and Angular eligibility scan | Sprint 1 |
| Real source-compatible runtime provisioning | Sprint 1/2 |
| Real baseline `npm ci`, build, test, and lint | Sprint 1 |
| Real Angular AST/template/workspace analysis | Sprint 2 |
| Real historical compatibility catalog and exact stage resolver | Sprint 2 |
| Real `ng update` execution | Sprint 3 |
| Real static symbol and template verification | Sprint 3 |
| Real low-risk repair patches | Sprint 4 |
| Real final evidence report from migration evidence | Sprint 4 |
| Browser and visual automation | Deferred/company-approved phase |
| External security and quality scanners | Deferred/company-approved phase |
| Production delivery publication or pull-request integration | Later MVP sprint |
| Real Azure OpenAI call | Later sprint after security/configuration approval |

Sprint 0 may execute only safe, allowlisted local version commands and fixture-bound tests. It must not mutate an arbitrary user source project.

---

## 6. Technology Stack

### 6.1 Backend

- Python 3.12+
- FastAPI
- Uvicorn
- Pydantic v2
- `pydantic-settings`
- SQLAlchemy
- Alembic
- SQLite with documented single-host MVP constraints
- LangGraph
- Azure OpenAI LLM Gateway abstraction
- Local filesystem artifact store
- Controlled Python execution worker
- Server-Sent Events

### 6.2 Migration Worker Runtime Foundation

- Python
- Node.js runtime-profile abstraction
- npm
- `npx`
- Git
- Future exact runtime selection per Angular stage

### 6.3 Frontend

- Node.js
- Next.js
- React
- TypeScript
- CSS Modules
- OpenAPI-generated typed client
- SSE client
- Custom log viewer
- Custom unified diff viewer
- Safe Markdown report viewer
- Artifact preview and metadata panel

---

## 7. Repository-Level Architecture

```text
backend/
  app/
    api/
    core/
    domain/
    repositories/
    state/
    events/
    orchestration/
    components/          # deterministic workflow components
    agents/              # AI-assisted agents only
    preflight/
    snapshots/
    runtime_profiles/
    command_execution/
    artifact_store/
    workspaces/
    checkpoints/
    delivery/
    llm_gateway/
    observability/
    policies/
frontend/
shared/
demo-apps/
scripts/
docs/
  adr/
tests/
```

---

## 8. Issue Summary

| ID | Issue | Priority | Main dependency |
|---|---|---:|---|
| AMF-S0-01 | Repository and Platform Boundary Skeleton | Must | None |
| AMF-S0-02 | FastAPI Backend and API Surface Skeleton | Must | S0-01 |
| AMF-S0-03 | Configuration, Policy, and Environment Foundation | Must | S0-02 |
| AMF-S0-04 | SQLAlchemy, Alembic, and SQLite State Schema | Must | S0-02, S0-03, S0-05 |
| AMF-S0-05 | Canonical Contracts and State Vocabulary | Must | S0-02 |
| AMF-S0-06 | Next.js Control Tower Skeleton | Must | S0-05 |
| AMF-S0-07 | Generated Typed Frontend API Client | Must | S0-05, S0-06 |
| AMF-S0-08 | Ordered SSE, Replay, and State Recovery | Must | S0-04, S0-05, S0-06 |
| AMF-S0-09 | Optimized LangGraph Mock Orchestrator | Must | S0-08, S0-19, S0-20 |
| AMF-S0-10 | Deterministic Component and AI-Agent Contracts | Must | S0-05, S0-09 |
| AMF-S0-11 | Immutable Stage-Scoped Artifact Store | Must | S0-03, S0-05 |
| AMF-S0-12 | Structured Command Worker and Supervisor Shell | Must | S0-03, S0-05, S0-19 |
| AMF-S0-13 | Preflight and Runtime Capability Foundation | Must | S0-12, S0-19 |
| AMF-S0-14 | LLM Gateway Mock, Redaction, Usage, and Cost | Should | S0-03, S0-05, S0-10 |
| AMF-S0-15 | Log, Diff, Markdown, and Artifact Viewers | Should | S0-06, S0-11 |
| AMF-S0-16 | Angular 18 Fixture and Evaluation Foundation | Must | None |
| AMF-S0-17 | Developer Scripts and Quality Gates | Must | S0-02, S0-06, S0-07 |
| AMF-S0-18 | Architecture Boundaries, Threats, and ADRs | Must | S0-01 |
| AMF-S0-19 | Internal Workspace, Snapshot, and Atomic Delivery | Must | S0-01, S0-03 |
| AMF-S0-20 | State Transition, Idempotency, Lease, Cancel, and Resume | Must | S0-04, S0-05 |
| AMF-S0-21 | Observability and Run Metrics Foundation | Should | S0-04, S0-08, S0-12, S0-14 |

---

# 9. Detailed Issues

## AMF-S0-01 — Repository and Platform Boundary Skeleton

**Type:** Architecture / DevOps  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `repository`, `architecture`, `foundation`, `devex`  
**Dependencies:** None

### User Story / Technical Story

As a development team, we need a clear repository and module structure so state management, orchestration, deterministic services, AI agents, command execution, artifacts, workspaces, delivery, and UI responsibilities remain separated from the beginning.

### Context / Why This Issue Exists

The factory is a platform composed of multiple trusted and untrusted layers. Without explicit boundaries, workflow logic may leak into routers, command execution may leak into agents, and the frontend may become a second workflow engine. Correcting those problems after real migration logic is introduced would be expensive and risky.

### Scope

- Create the complete top-level repository structure defined in Section 7.
- Create README files for `backend/`, `frontend/`, `shared/`, `demo-apps/`, `scripts/`, `docs/`, and `tests/`.
- Separate deterministic workflow components under `backend/app/components/` from AI-assisted workers under `backend/app/agents/`.
- Create explicit modules for state, events, command execution, artifacts, snapshots, workspaces, checkpoints, delivery, policies, and observability.
- Add package/module placeholders and dependency direction notes.

### Out of Scope

- Real migration logic.
- Real Angular analysis.
- Real LLM calls.
- Real package installation or `ng update`.
- Production deployment configuration.

### Implementation Notes

- API routers must depend on application services, not repositories or workers directly.
- LangGraph nodes must call state, event, artifact, and execution services rather than implement those concerns internally.
- Agents must not import execution-worker implementations or secret-bearing configuration.
- The root README should include a concise architecture diagram and module ownership table.

### Acceptance Criteria

- The repository contains all agreed top-level and backend module folders.
- Deterministic components and AI-assisted agents are clearly separated.
- State/event services are not placed inside API routers or UI code.
- Workspace, artifact, checkpoint, and delivery modules are distinct.
- Every principal folder contains a README describing ownership and forbidden responsibilities.
- Backend and frontend can be started independently.

### Definition of Done

- Structure committed and importable.
- Root README and folder READMEs completed.
- Architecture ownership table reviewed by the team.
- No circular dependency between API, domain, repositories, orchestration, and worker modules.

### Risks and Edge Cases

- Reorganizing repeatedly after implementation begins.
- Developers treating every workflow step as an AI agent.
- Frontend or LangGraph nodes bypassing platform services.
- Shared folder becoming an uncontrolled dumping ground.

---

## AMF-S0-02 — FastAPI Backend and API Surface Skeleton

**Type:** Backend  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `backend`, `fastapi`, `api`, `foundation`  
**Dependencies:** AMF-S0-01

### User Story / Technical Story

As a backend developer, I need a FastAPI application shell and stable API surface so later workflow services can be added without placing business logic in HTTP handlers.

### Context / Why This Issue Exists

The backend is the trusted execution authority and source of truth. Sprint 0 must establish thin routers, dependency injection, exception handling, and versioned contracts before real migration operations are implemented.

### Scope

- Create FastAPI application startup, router registration, exception handling, and lifecycle hooks.
- Add `GET /health` and `GET /version`.
- Add mock shells for `POST /migrations/preflight`, `POST /migrations/mock`, `GET /migrations/{runId}/state`, and `GET /migrations/{runId}/events`.
- Add approval, approval-policy, cancel, resume, artifact, and assistant route shells.
- Add request correlation/run identifiers to structured logs.

### Out of Scope

- Real migration creation.
- Real source snapshot.
- Real Angular commands.
- Authentication and authorization.
- Production API gateway integration.

### Implementation Notes

- Routers should contain input validation and service delegation only.
- Use dependency injection for state, artifact, transition, preflight, and orchestration services.
- Return a canonical error envelope with an error code, message, correlation ID, and optional details.
- `POST /migrations/mock` must require a valid, non-expired preflight checksum.

### Acceptance Criteria

- Backend starts with Uvicorn.
- Health and version endpoints return valid responses.
- All listed route shells appear in OpenAPI.
- Routers delegate to services and contain no workflow state machine.
- Create-mock-run rejects a missing, stale, or mismatched preflight checksum.
- Cancel and resume endpoints behave idempotently in mock tests.

### Definition of Done

- Backend README documents startup and API routes.
- Basic endpoint and error-envelope tests pass.
- OpenAPI schema is generated in CI/local quality command.
- No secret-bearing configuration is serialized by API models.

### Risks and Edge Cases

- Business logic being placed in routers.
- Inconsistent errors across endpoints.
- Premature coupling of HTTP handlers to LangGraph internals.
- Mock endpoints diverging from future real endpoint contracts.

---

## AMF-S0-03 — Configuration, Policy, and Environment Foundation

**Type:** Backend / Platform  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `configuration`, `policy`, `security`, `environment`  
**Dependencies:** AMF-S0-02

### User Story / Technical Story

As the platform, we need centralized validated configuration and policy settings so filesystem roots, database behavior, command limits, SSE behavior, runtime profiles, and LLM budgets are never hardcoded.

### Context / Why This Issue Exists

The factory interacts with local paths, processes, artifacts, databases, and Azure OpenAI. Incorrect or hardcoded settings can expose secrets, permit unsafe paths, create inconsistent behavior across machines, and make cost reporting inaccurate.

### Scope

- Implement settings for application environment, database URL, artifact root, workspace root, snapshot root, delivery root, and allowed source/target roots.
- Add command timeout, maximum output size, worker lease, SSE heartbeat, replay retention, and log chunk settings.
- Add SQLite WAL and busy-timeout settings.
- Add Azure OpenAI endpoint/deployment/API-version/key placeholders and LLM enablement flag.
- Add input/output price-per-million, token budget, and cost budget settings.
- Create policy interfaces/files for topology support, command allowlists, install scripts, changed-file sensitivity, auto approval, and migration support levels.
- Create `.env.example` with safe placeholders.

### Out of Scope

- Production secret-store integration.
- Real Azure identity configuration.
- Enterprise policy administration UI.
- Remote dynamic configuration service.

### Implementation Notes

- Use Pydantic Settings with strict validation.
- Never return or log API keys, tokens, private registry credentials, or raw secret values.
- Pricing must be snapshotted into a run so historical reports do not change when configuration changes.
- Paths must be normalized through a dedicated path policy rather than string comparison.

### Acceptance Criteria

- Application loads valid local configuration from environment variables or `.env`.
- Missing required settings fail startup with a readable validation message.
- Invalid roots, timeouts, prices, or budget values are rejected.
- Secrets are redacted from startup logs and API responses.
- `.env.example` contains no real credentials.
- Policy settings can be injected into mock services in tests.

### Definition of Done

- Configuration tests cover valid, missing, and invalid values.
- Local setup documentation completed.
- Secret-redaction test passes.
- Windows and POSIX path examples are documented.

### Risks and Edge Cases

- Hardcoded Windows-only paths.
- Accidental secret logging.
- Changing LLM prices modifying old reports.
- Unsafe broad filesystem roots.
- Unbounded command output or SSE retention.

---

## AMF-S0-04 — SQLAlchemy, Alembic, and SQLite State Schema

**Type:** Backend / Persistence  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `sqlalchemy`, `alembic`, `sqlite`, `persistence`, `state-store`  
**Dependencies:** AMF-S0-02, AMF-S0-03, AMF-S0-05

### User Story / Technical Story

As the platform, we need a persistent relational schema so run state, stages, steps, events, approvals, commands, artifacts, leases, repairs, assurance statuses, and LLM usage survive refreshes and backend restarts.

### Context / Why This Issue Exists

Backend-owned state cannot remain in memory. The optimized workflow also requires optimistic concurrency, ordered events, idempotency, and worker ownership. These fields must exist before orchestration and SSE are implemented.

### Scope

- Configure SQLAlchemy sessions and Alembic.
- Create tables: `migration_runs`, `migration_stages`, `stage_steps`, `agent_executions`, `workflow_events`, `approval_events`, `approval_policy_events`, `artifact_metadata`, `command_executions`, `worker_leases`, `repair_attempts`, `llm_usage_records`, and `run_assurance_statuses`.
- Add state version, event sequence, event ID, idempotency key, stage/attempt IDs, lease owner/expiry, artifact checksum/schema version, and LLM pricing/cost fields.
- Configure SQLite WAL and busy timeout for the single-host MVP.
- Add repositories and transaction helpers.

### Out of Scope

- Production PostgreSQL support.
- Distributed locks.
- Large artifact blobs in the database.
- Full real workflow persistence semantics beyond the mock.

### Implementation Notes

- Keep transactions short; do not hold a database transaction while executing commands or calling an LLM.
- Store artifact metadata in SQLite and content in the filesystem.
- Use optimistic concurrency through `expected_state_version`.
- Add indexes for run ID, stage ID, event sequence, status, and idempotency key.

### Acceptance Criteria

- Alembic creates the complete initial schema.
- A test inserts and reads a complete mock run snapshot.
- A stale expected state version is rejected.
- Event sequence numbers are unique and monotonic per run.
- Duplicate idempotency keys are constrained appropriately.
- SQLite WAL and busy timeout are configurable.
- Artifact contents are not stored as database blobs.

### Definition of Done

- Initial migration committed.
- Repository tests pass.
- Schema diagram or table reference is documented.
- Local database reset and migration commands are available.

### Risks and Edge Cases

- Overlapping state fields causing inconsistent snapshots.
- SQLite write contention from long transactions.
- Event/state persistence becoming non-transactional.
- Schema changes later breaking mock clients.

---

## AMF-S0-05 — Canonical Contracts and State Vocabulary

**Type:** Backend / Shared Contracts  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `pydantic`, `contracts`, `openapi`, `state-model`  
**Dependencies:** AMF-S0-02

### User Story / Technical Story

As the team, we need one canonical contract vocabulary so the backend, frontend, orchestrator, deterministic services, agents, and tests describe workflow state consistently.

### Context / Why This Issue Exists

The previous state model mixed run-level activity, stage activity, validation activity, and terminal outcomes. That creates invalid combinations and forces the UI to infer meaning. Sprint 0 must freeze a normalized state model before more UI and orchestration code is added.

### Scope

- Define Pydantic schemas for preflight, create-run, run snapshots, stages, steps, events, transitions, approvals, artifacts, topology, support level, runtime profile, commands, leases, repairs, assurance, delivery, and LLM usage/cost.
- Define separate enums for `RunStatus`, `RunPhase`, `StageStatus`, and `StepStatus`.
- Define validation, approval, auto-approval, risk, topology, support-level, assurance, command, cancellation, and artifact enums.
- Add cross-field model validation for incompatible state combinations.
- Expose contracts through OpenAPI.

### Out of Scope

- Real business rules for every future migration state.
- Frontend-specific presentation labels inside domain DTOs.
- Raw filesystem paths for artifact access.
- Raw shell command strings.

### Implementation Notes

- Use these canonical run statuses: `CREATED`, `RUNNING`, `WAITING`, `CANCELLING`, `CANCELLED`, `COMPLETED`, `FAILED`, `DIAGNOSTIC_HOLD`.
- Use phases: `PREFLIGHT_SNAPSHOT`, `DISCOVERY_BASELINE`, `FEASIBILITY_PLANNING`, `STAGED_MIGRATION`, `FINAL_ASSURANCE`, `DELIVERY_REPORTING`.
- Use stage statuses: `PENDING`, `RUNNING`, `WAITING_APPROVAL`, `REPAIRING`, `PASSED`, `FAILED`, `ROLLED_BACK`, `CANCELLED`, `DIAGNOSTIC_HOLD`.
- Use step statuses: `PENDING`, `QUEUED`, `RUNNING`, `PASSED`, `FAILED`, `BLOCKED`, `WAITING_APPROVAL`, `SKIPPED`, `MANUAL`, `DEFERRED`, `ACCEPTED_RISK`, `CANCELLED`.
- Store source/target version family and exact detected/resolved versions separately.

### Acceptance Criteria

- OpenAPI contains all canonical schemas and enums.
- No global `BUILD_RUNNING`, `VALIDATION_RUNNING`, or similar overlapping states remain.
- Invalid enum values and invalid combinations are rejected.
- Every event and artifact reference includes required IDs and timestamps.
- `StructuredCommandRequest` contains executable and arguments, not a shell command string.
- Frontend types can be generated without manually redefining domain enums.

### Definition of Done

- Contract tests and schema snapshots pass.
- Status vocabulary documented with examples.
- Breaking-contract review completed before dependent UI/orchestrator work continues.
- OpenAPI JSON is reproducibly generated.

### Risks and Edge Cases

- Changing vocabulary after the UI and database depend on it.
- Too many presentation-specific states leaking into the domain.
- Invalid combinations such as a completed run with a running stage.
- Raw paths or commands leaking through shared DTOs.

---

## AMF-S0-06 — Next.js Control Tower Skeleton Aligned to Macro Phases

**Type:** Frontend  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `nextjs`, `react`, `typescript`, `control-tower`  
**Dependencies:** AMF-S0-05

### User Story / Technical Story

As a user, I need a Control Tower shell that validates setup inputs, displays authoritative backend state, distinguishes deterministic steps from AI agents, and communicates assurance and delivery status clearly.

### Context / Why This Issue Exists

The UI is the primary product experience, but it must not become a second workflow engine. The optimized workflow also requires a preflight-first setup and separate technical, parity, security, quality, and delivery indicators.

### Scope

- Create `/migrations/new` and `/migrations/[runId]`.
- Create setup, preflight result, run header, macro phase timeline, stage cards, step panel, agent panel, validation panel, assurance panel, approval panel, artifact panel, assistant panel, delivery panel, and report panel.
- Disable Start until the latest input checksum has a valid non-expired preflight result.
- Display the six macro phases and the current run phase/status.
- Display deterministic-component and AI-agent labels separately.
- Add auto-approval, cancel, and resume controls.
- Show `migrated-app` as unpublished until delivery succeeds.

### Out of Scope

- Real migration job creation.
- Real approval authorization.
- Real artifact editing.
- A frontend workflow state machine.
- Production visual design system.

### Implementation Notes

- Derive presentation from canonical DTOs and selectors only.
- Use local component state only for UI concerns such as panel expansion or form input, not workflow truth.
- Display `manual`, `deferred`, and `accepted risk` distinctly.
- On refresh, fetch the state snapshot before connecting or reconciling SSE.

### Acceptance Criteria

- Frontend starts locally and renders both pages.
- Configuration validation is visible and Start remains disabled when blocked or expired.
- Mock run page renders six phases, stages, steps, agents, gates, and assurance dimensions from backend data.
- Auto-approval mode is displayed from backend state.
- Cancel and resume actions call the API client.
- Unpublished delivery state is clearly shown.
- Refresh reconstructs the UI from the backend snapshot without fake progress.

### Definition of Done

- Frontend README completed.
- Component render tests pass.
- Accessibility basics are covered for status labels and controls.
- No duplicate domain enum definitions exist in components.

### Risks and Edge Cases

- UI inferring progress from timers.
- Confusing deterministic components with AI agents.
- Treating technical build success as proven parity.
- Showing an incomplete workspace as final output.

---

## AMF-S0-07 — Generated Typed Frontend API Client

**Type:** Frontend / Contracts  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `openapi`, `api-client`, `typescript`, `contracts`  
**Dependencies:** AMF-S0-05, AMF-S0-06

### User Story / Technical Story

As a frontend developer, I need a generated typed API client so the Control Tower remains aligned with backend OpenAPI contracts and does not scatter raw HTTP calls across components.

### Context / Why This Issue Exists

The workflow contains many state and event types. Manual duplicate interfaces will quickly drift, particularly after optimizing the state model. Contract generation should be part of the normal developer workflow from Sprint 0.

### Scope

- Generate TypeScript types and client functions from backend OpenAPI.
- Centralize base URL, error handling, correlation IDs, and request helpers.
- Provide functions for preflight, create mock run, state, events/recovery, approvals, approval policy, cancellation, resume, artifacts, assistant, version, and health.
- Add mocks or test adapters for component tests.

### Out of Scope

- Authentication interceptors.
- Production retry/circuit-breaker policy.
- Offline client.
- Manual duplication of generated domain types.

### Implementation Notes

- Keep generated code in a dedicated directory and wrap it with small domain-specific functions where useful.
- Prohibit scattered direct `fetch()` through lint rule, code review rule, or module conventions.
- Do not edit generated files manually.

### Acceptance Criteria

- Contract generation runs reproducibly.
- Frontend can call health, version, preflight, create-run, state, approval-policy, cancel, resume, artifact, and assistant endpoints through the client.
- Components import generated or wrapped types rather than redefining them.
- API errors are normalized into a frontend-safe error model.

### Definition of Done

- Generation command documented and included in quality checks.
- Client tests or mocked integration tests pass.
- Generated files are committed or regenerated consistently according to team policy.
- No direct domain `fetch()` calls remain in components.

### Risks and Edge Cases

- Generated client churn.
- OpenAPI changes silently breaking the UI.
- Business logic being placed inside generated-code wrappers.
- Multiple competing API clients.

---

## AMF-S0-08 — Ordered SSE, Replay, and State Recovery Skeleton

**Type:** Backend / Frontend  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `sse`, `events`, `realtime`, `recovery`  
**Dependencies:** AMF-S0-04, AMF-S0-05, AMF-S0-06

### User Story / Technical Story

As a user, I need reliable real-time workflow updates that can reconnect and recover without the UI diverging from backend state.

### Context / Why This Issue Exists

Simple SSE streaming is insufficient for long-running migrations. Network interruption, duplicate delivery, browser refresh, backend restart, and retention gaps must be handled before many UI features depend on the event stream.

### Scope

- Implement `GET /migrations/{runId}/events`.
- Persist events with a monotonic sequence number per run before emission.
- Emit SSE `id`, `event`, and canonical `WorkflowEvent` data.
- Support `Last-Event-ID` replay within configured retention.
- Emit heartbeats.
- Implement frontend duplicate suppression and sequence-gap detection.
- Refetch the state snapshot when replay is unavailable or a gap is detected.
- Keep live UI logs bounded while persisting complete logs as artifacts.

### Out of Scope

- WebSockets.
- Distributed event broker.
- Production horizontal scaling.
- Using SSE as the authoritative state store.

### Implementation Notes

- Events should reference artifact IDs rather than contain large logs or diffs.
- Use one sequence space per run.
- Persist state and event consistently through the transition service.
- The frontend should reconcile event changes against the latest known state version.

### Acceptance Criteria

- Mock stage and step changes reach the UI through SSE.
- Reconnect with `Last-Event-ID` replays missed events.
- Duplicate events do not duplicate UI effects.
- A missing replay range triggers a snapshot refetch.
- Heartbeat keeps idle approval periods observable.
- Events are persisted before emission.
- Page refresh reconstructs state correctly.

### Definition of Done

- Backend SSE tests pass.
- Frontend hook tests cover reconnect, duplicate, and gap scenarios.
- Event format is documented.
- A local replay demo is included.

### Risks and Edge Cases

- Event ordering bugs.
- Unbounded memory usage from logs.
- UI applying stale events after a snapshot.
- SSE connection appearing healthy while state persistence failed.

---

## AMF-S0-09 — Optimized LangGraph Mock Orchestrator

**Type:** Orchestration  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `langgraph`, `orchestration`, `state-machine`, `mock-workflow`  
**Dependencies:** AMF-S0-08, AMF-S0-19, AMF-S0-20

### User Story / Technical Story

As the platform, I need a mock LangGraph workflow that reflects the optimized production flow so real components can replace mock nodes incrementally without redesigning orchestration.

### Context / Why This Issue Exists

A simple linear list of agents does not reflect the real platform. The workflow contains deterministic phases, parallel discovery, durable approvals, stage loops, repair decisions, final assurance, delivery, cancellation, and resume.

### Scope

- Create nodes for run creation, snapshot/topology, source-runtime resolution, parallel discovery fan-out, discovery join, baseline qualification, analysis/feasibility, analysis approval, planning, plan approval, stage loop, final assurance, delivery gate, and reporting.
- Within every mock stage, model checkpoint, transform, cheap validation, expensive validation, repair decision, risk/approval decision, and stage commit.
- Use the transition service for all state changes.
- Use artifact and event services for evidence and notifications.
- Read auto-approval policy at every waiting gate.
- Support mock cancellation and resume.

### Out of Scope

- Real Angular analysis.
- Real compatibility resolution.
- Real commands.
- Real repair.
- Direct database writes from graph nodes.

### Implementation Notes

- Keep graph state compact and store large evidence in artifacts.
- Parallel discovery should be represented as fan-out/fan-in rather than sequential artificial agent cards.
- Waiting gates must be durable across backend restarts in the persistence model.
- Graph nodes must be idempotent or call idempotent services.

### Acceptance Criteria

- Mock graph runs end to end through all six phases.
- Parallel discovery fan-out/fan-in works.
- Analysis and plan approvals pause and resume durably.
- Enabling auto approval reevaluates the current eligible waiting gate immediately.
- Auto approval remains active across later stages.
- Mock cancellation prevents future nodes from starting.
- Resume continues from the last safe mock checkpoint.
- Graph nodes do not write directly to the frontend, filesystem, or database repositories.

### Definition of Done

- Graph topology documented.
- End-to-end orchestration test passes.
- Approval, cancellation, replay, and resume tests pass.
- Mock node outputs use canonical component/agent contracts.

### Risks and Edge Cases

- LangGraph duplicating the transition service.
- Non-idempotent nodes redoing side effects after resume.
- Approvals being read only at run start.
- Sequentializing work that should be parallel.

---

## AMF-S0-10 — Deterministic Component and AI-Agent Contracts

**Type:** Architecture / Agent Platform  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `agents`, `components`, `contracts`, `deterministic-first`  
**Dependencies:** AMF-S0-05, AMF-S0-09

### User Story / Technical Story

As the platform, we need separate contracts for deterministic components and AI-assisted agents so the LLM is used only where judgment or explanation is valuable.

### Context / Why This Issue Exists

Eligibility, version parsing, snapshots, compatibility data, command policy, state transitions, builds, checkpoints, and delivery do not require an LLM. Calling every function an agent adds nondeterminism, cost, and security risk.

### Scope

- Define interfaces for `SourceIntakeValidator`, `SnapshotService`, `WorkspaceTopologyClassifier`, `CompatibilityResolver`, `ToolchainRuntimeManager`, `CommandPolicyEngine`, `BaselineQualificationService`, `StaticSymbolGate`, `ParityEvidenceEngine`, `CheckpointService`, `ArtifactService`, `WorkerSupervisor`, and `DeliveryService`.
- Define common agent input/output envelopes for `AnalysisAgent`, `PlanningAgent`, `TransformationAgent`, `BuildValidationAgent`, `RepairAgent`, `ReportAgent`, and `AssistantAgent`.
- Define registered action proposal and patch proposal schemas.
- Record deterministic executions and agent executions separately.

### Out of Scope

- Real agent prompts.
- Real LLM calls.
- Direct command or mutation permission for an agent.
- Treating compatibility resolution or checkpointing as LLM decisions.

### Implementation Notes

- Agent outputs may recommend a next state but cannot transition state directly.
- Agent action proposals must reference a registered action/command ID.
- Patch proposals must identify files, rationale, risk, expected behavior impact, and validation requests.
- Repository content, comments, and logs must be labeled as untrusted data in future LLM contexts.

### Acceptance Criteria

- Every deterministic service and AI agent has a documented bounded interface.
- Mock agents return schema-validated outputs.
- Agents cannot import command-worker implementations or credentials.
- AI output cannot authorize execution or approval.
- UI labels deterministic steps and AI-assisted agents distinctly.
- Execution history distinguishes component type.

### Definition of Done

- Contracts documented and tested.
- Mock implementations integrated with the orchestrator.
- Forbidden dependency rules reviewed.
- Example action and patch proposals included.

### Risks and Edge Cases

- Agent contract becoming too permissive.
- LLM recommendations being treated as state transitions.
- Deterministic logic being duplicated in prompts.
- User assuming every displayed step consumes LLM tokens.

---

## AMF-S0-11 — Immutable Stage-Scoped Artifact Store

**Type:** Backend / Evidence  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `artifact-store`, `filesystem`, `audit`, `integrity`  
**Dependencies:** AMF-S0-03, AMF-S0-05

### User Story / Technical Story

As the platform, I need an immutable local artifact store so every mock decision, command, approval, diff, validation, repair attempt, and report is reviewable without overwriting earlier evidence.

### Context / Why This Issue Exists

A flat artifact structure would overwrite reports across Angular stages and repair attempts. Artifact access by arbitrary paths would also create a security risk. The store must be stage-scoped, append-only, checksum-bound, and opened by ID.

### Scope

- Create the global, stage, repair-attempt, final-assurance, delivery, and final-report directory structure.
- Support JSON, YAML, Markdown, text logs, and patch/diff content.
- Define `ArtifactEnvelope` metadata including schema version, artifact ID, run/stage/attempt, producer, type, content type, input hashes, policy version, content hash, and relative path.
- Implement atomic writes and path containment checks.
- Implement list/read-by-ID APIs and metadata persistence.

### Out of Scope

- Cloud object storage.
- Artifact editing.
- User-provided arbitrary artifact paths.
- Advanced full-text indexing.

### Implementation Notes

- Use temporary file plus atomic rename for writes where supported.
- Never silently overwrite an existing artifact; create a new version/artifact ID.
- Keep artifact content outside SQLite.
- Normalize and verify every relative path against the run artifact root.

### Acceptance Criteria

- Mock workflow creates the complete folder structure.
- Global and stage artifacts can be listed and opened by ID.
- Each repair attempt has an independent directory.
- Existing artifact content is never silently replaced.
- Path traversal and symlink escape attempts are rejected.
- Checksums are generated and displayed in metadata.
- Large artifact content is not placed in workflow events.

### Definition of Done

- Artifact writer/reader tests pass.
- Integrity and traversal tests pass.
- Folder contract documented.
- UI can open mock artifacts by ID.

### Risks and Edge Cases

- Artifact overwrite across stages.
- Path traversal or symlink escape.
- Database/filesystem metadata inconsistency.
- Mixing the delivered app with internal evidence.

---

## AMF-S0-12 — Structured Command Worker and Supervisor Shell

**Type:** Backend / Security  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `command-authority`, `sandbox`, `worker`, `security`  
**Dependencies:** AMF-S0-03, AMF-S0-05, AMF-S0-19

### User Story / Technical Story

As the trusted execution authority, I need a structured command worker and supervisor so future commands cannot bypass allowlists, runtime profiles, working-directory policy, timeout, cancellation, and idempotency.

### Context / Why This Issue Exists

Accepting raw shell strings creates command-injection and quoting risks. Long-running migrations also require process-tree termination, bounded output, and durable execution records.

### Scope

- Implement `StructuredCommandRequest`, command registry, command policy engine, execution worker, worker supervisor, and command-log writer.
- Allow only safe Sprint 0 commands: Python, Node, npm, npx, and Git version checks.
- Require command ID, executable, argument array, `shell=false`, working-directory alias, runtime-profile ID, timeout, network profile, cancellation policy, and idempotency key.
- Record stdout, stderr, exit code, status, timestamps, duration, requester, and artifact IDs.
- Implement timeout and process-tree termination.

### Out of Scope

- `ng update`.
- `npm install`.
- Arbitrary shell commands.
- Container runtime implementation.
- Production network sandboxing.

### Implementation Notes

- Do not concatenate executable and arguments into a shell string.
- Validate executable and each argument against the registered command definition.
- Use a working-directory alias resolved by the workspace service.
- Bound captured in-memory output and stream/persist complete logs to artifacts.
- Return the recorded result for duplicate idempotency keys.

### Acceptance Criteria

- Allowlisted version commands execute successfully.
- Unknown executable, command ID, argument, working directory, or runtime profile is rejected.
- Shell metacharacters cannot escape the argument policy.
- Timeout and process-tree termination are tested.
- Duplicate idempotency keys do not execute twice.
- Command results and logs are persisted and visible as artifacts.
- Cancellation status is reflected in the command result.

### Definition of Done

- Worker and policy tests pass.
- Unsafe-command tests pass.
- Command result contract documented.
- No agent can call subprocess APIs directly.

### Risks and Edge Cases

- Command injection.
- Orphan child processes.
- Unbounded logs.
- OS-specific quoting behavior.
- Running a command in the wrong workspace.

---

## AMF-S0-13 — Preflight and Runtime Capability Foundation

**Type:** Platform / DevOps  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `preflight`, `runtime`, `path-safety`, `capability`  
**Dependencies:** AMF-S0-12, AMF-S0-19

### User Story / Technical Story

As a user and operator, I need configuration and runtime preflight validation before a run is created so unsafe paths and missing capabilities fail early.

### Context / Why This Issue Exists

The optimized workflow begins with fast-fail checks. Runtime discovery must happen before baseline execution, and the Start button must be bound to exactly the inputs that were validated.

### Scope

- Validate canonical source/target path relationships using controlled fixture/test paths.
- Detect source equals target and target nested inside source.
- Check readable/writable capability and disk-space estimate contract.
- Check Python, Node, npm, npx, and Git availability through the structured worker.
- Define runtime-profile availability, registry/proxy/certificate, topology, and Angular eligibility placeholders.
- Return `passed`, `passed_with_warnings`, `blocked`, or `expired`.
- Bind the result to a normalized input checksum and expiry.

### Out of Scope

- Full arbitrary-project scan.
- Automatic installation of missing tools.
- Real Angular compatibility resolution.
- Unsafe proxy/certificate bypass.

### Implementation Notes

- Changing any relevant setup input invalidates the previous checksum.
- Classify failures as blockers or warnings with actionable codes.
- Do not run `npx` commands that download packages in Sprint 0.
- Use the workspace/path policy for canonicalization.

### Acceptance Criteria

- Valid fixture setup returns a checksum-bound result.
- Changing source, target, target version, mode, or policy invalidates the result.
- Missing tools return structured blockers or warnings rather than crashing.
- Unsafe source/target relationships are blocked.
- Start remains disabled when result is blocked or expired.
- Preflight artifact is created and visible in the UI.
- No source file is modified.

### Definition of Done

- Preflight tests cover safe and unsafe path combinations.
- Capability tests mock missing tools.
- Setup-page integration test passes.
- Runtime requirements documented.

### Risks and Edge Cases

- False confidence from a shallow preflight.
- Windows path casing and symlink behavior.
- `npx` unexpectedly reaching the network.
- Corporate proxy/certificate problems being misclassified.

---

## AMF-S0-14 — LLM Gateway Mock, Redaction, Usage, and Cost

**Type:** Backend / AI Platform  
**Priority:** Should  
**Suggested labels:** `sprint-0`, `azure-openai`, `llm-gateway`, `redaction`, `cost`  
**Dependencies:** AMF-S0-03, AMF-S0-05, AMF-S0-10

### User Story / Technical Story

As an agent engineer and operator, I need a backend-controlled LLM Gateway mock so future agents can request bounded assistance without receiving credentials, changing policy, or hiding token cost.

### Context / Why This Issue Exists

The gateway is the only approved model-access path. Sprint 0 should establish request/response contracts, secret redaction, untrusted-content boundaries, usage aggregation, budgets, and fixed-price cost calculation before real calls are introduced.

### Scope

- Implement mock `LlmRequest`, `LlmResponse`, `LlmUsageRecord`, `LlmCostSummary`, `LlmBudgetDecision`, and `PromptRedactionResult`.
- Add system-policy and untrusted-repository-content separation.
- Add secret/token/header/.env/private-registry redaction tests.
- Validate structured mock outputs.
- Aggregate usage by run, stage, agent, and task type.
- Snapshot configured pricing: input `$0.25/1M`, output `$2.00/1M`.
- Add mock budget actions: warn, block new LLM calls, deterministic fallback, diagnostic hold.
- Persist redacted interaction metadata as artifacts.

### Out of Scope

- Real Azure OpenAI API call.
- Real agent prompts.
- Production managed identity.
- Raw prompt storage.
- LLM-driven execution.

### Implementation Notes

- Treat repository code, comments, READMEs, logs, and errors as untrusted data, not policy instructions.
- Do not store hidden reasoning; store concise decision summaries and structured outputs.
- Include failed calls and retries in usage accounting.
- Keep deployment name configurable and separate from public model labels.

### Acceptance Criteria

- Mock agents can call the gateway through its interface.
- Secrets are removed from test prompts and logs.
- Repository text cannot modify system policy or tool permissions.
- Input, output, total tokens, and cost are calculated correctly.
- Pricing is snapshotted with the run.
- Budget decisions produce structured results.
- Frontend never receives credentials or raw sensitive prompts.

### Definition of Done

- Gateway and redaction tests pass.
- Cost calculation tests pass.
- Untrusted-content test fixture passes.
- Usage summary artifact and UI sample are available.

### Risks and Edge Cases

- Secret leakage.
- Prompt injection from repository content.
- Counting retries incorrectly.
- Old reports changing when prices change.
- Model response being treated as trusted action.

---

## AMF-S0-15 — Log, Diff, Markdown, and Artifact Viewer Skeletons

**Type:** Frontend  
**Priority:** Should  
**Suggested labels:** `sprint-0`, `log-viewer`, `diff-viewer`, `markdown`, `artifacts`  
**Dependencies:** AMF-S0-06, AMF-S0-11

### User Story / Technical Story

As a user, I need safe and usable viewers for logs, diffs, reports, and artifact metadata so the migration remains transparent and auditable.

### Context / Why This Issue Exists

Migration evidence can be large and untrusted. The UI must avoid injecting Markdown/HTML, freezing on large logs, or losing stage and repair-attempt context.

### Scope

- Create `LogViewer`, `UnifiedDiffViewer`, `MarkdownReportViewer`, and `ArtifactPreviewPanel`.
- Support bounded live-log display with on-demand stored artifact loading.
- Display artifact ID, type, stage, repair attempt, producer, timestamp, and checksum.
- Support unified diff file headers, additions, removals, and context lines.
- Render Markdown safely without arbitrary HTML/script execution.
- Add pagination/chunk/search contract for stored logs.

### Out of Scope

- Side-by-side diff.
- Advanced syntax highlighting.
- PDF/DOCX preview.
- Editing artifacts.
- Loading full artifacts through SSE.

### Implementation Notes

- Virtualize or chunk large content where needed.
- Fetch full artifacts on demand by artifact ID.
- Keep viewer state local without altering workflow state.
- Sanitize or disable raw HTML in Markdown.

### Acceptance Criteria

- Mock command log opens and scrolls safely.
- Mock stage and repair-attempt diff opens with correct context.
- Mock Markdown report renders safely.
- Large mock content does not freeze the page.
- Artifact metadata and checksum are visible.
- HTML/script injection fixture is blocked.

### Definition of Done

- Viewer components and tests completed.
- Accessibility basics implemented.
- Connected to artifact API client.
- Large-content behavior documented.

### Risks and Edge Cases

- Cross-site scripting through Markdown.
- Browser memory pressure.
- Poor diff readability.
- Users confusing a proposal artifact with an applied change.

---

## AMF-S0-16 — Angular 18 Fixture and Evaluation Foundation

**Type:** Test Infrastructure  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `angular18`, `fixture`, `evaluation`, `regression`  
**Dependencies:** None

### User Story / Technical Story

As the team, we need a controlled Angular 18 reference application and expectation manifests so future discovery, baseline, migration, parity, repair, and AI changes can be tested repeatedly.

### Context / Why This Issue Exists

A trivial fixture cannot validate the platform. The reference app should remain small but include representative routing, API, validation, styling, environment, and test signals. It must also include controlled regression and untrusted-content cases.

### Scope

- Create or document `demo-apps/angular-18-basic/`.
- Include routes, a lazy-route signal where practical, HTTP service, API base URL, representative interceptor/backend integration signal, form validation, component styling/theme signal, environments, and proxy example.
- Include test/lint metadata where practical.
- Create expected discovery, baseline, route, backend-contract, changed-file-risk, and parity manifests.
- Add controlled known-failure fingerprint and prompt-injection text fixture.
- Document the exact source runtime and build command.

### Out of Scope

- Enterprise-scale app.
- Complex authentication backend.
- Multiple Angular major fixtures.
- Real migration in Sprint 0.

### Implementation Notes

- Tests must copy the fixture into an internal workspace rather than mutate it.
- Expectation manifests should be reviewed and version-controlled.
- Prompt-injection text must be harmless and explicitly marked as test data.
- Keep dependencies stable through a committed lockfile.

### Acceptance Criteria

- Fixture builds in its documented source runtime.
- Fixture includes route, API, interceptor/config, form, style, and environment signals.
- Expected manifests are version-controlled.
- A regression test compares mock discovery output with expected manifests.
- Fixture source integrity hash remains unchanged after tests.
- Known failure and untrusted-content cases are represented.

### Definition of Done

- Fixture README completed.
- Build and integrity test pass.
- Expectation manifests reviewed.
- Fixture included in Sprint 0 demo guide.

### Risks and Edge Cases

- Fixture too simple to expose design flaws.
- Dependency drift.
- Tests mutating the fixture.
- Prompt-injection fixture accidentally entering real prompts without labels.

---

## AMF-S0-17 — Developer Scripts and Quality Gates

**Type:** DevOps / Developer Experience  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `devex`, `scripts`, `tests`, `quality`  
**Dependencies:** AMF-S0-02, AMF-S0-06, AMF-S0-07

### User Story / Technical Story

As a development team, we need repeatable commands to start, test, validate, format, migrate, and demonstrate the platform skeleton across supported developer environments.

### Context / Why This Issue Exists

The project combines Python, Node.js, database migrations, OpenAPI generation, frontend tests, SSE tests, fixtures, and artifact integrity. Manual undocumented command sequences will create inconsistent local environments and slow later sprints.

### Scope

- Add commands for backend/frontend startup, all tests, backend lint/format/typecheck, frontend lint/typecheck/test, OpenAPI client generation, Alembic migration, database reset, mock workflow, SSE replay test, artifact integrity test, fixture contract test, and architecture checks.
- Document Python virtual environment and Node package installation.
- Provide PowerShell-compatible instructions.
- Add safe corporate proxy/certificate troubleshooting notes without disabling certificate validation globally.

### Out of Scope

- Production CI/CD deployment.
- Unsafe proxy workarounds.
- Containerization unless separately approved.
- Automatic developer-tool installation.

### Implementation Notes

- Use a consistent command runner such as documented scripts, Makefile/justfile, npm scripts, or PowerShell scripts.
- Commands should fail fast and return non-zero on quality violations.
- Contract generation must happen before frontend type checking in the aggregate quality command.

### Acceptance Criteria

- A new developer can start backend and frontend from documentation.
- One aggregate quality command runs all core checks in the correct order.
- Database migration/reset commands work.
- Mock workflow and SSE replay demos are reproducible.
- Artifact integrity and fixture contract tests are executable.
- PowerShell instructions are verified.

### Definition of Done

- Developer setup guide completed.
- Scripts tested on the team environment.
- Troubleshooting section added.
- No unsafe TLS/certificate bypass is recommended.

### Risks and Edge Cases

- OS differences.
- Corporate proxy and certificate issues.
- Python/Node version mismatch.
- Generated contracts not refreshed.
- Commands succeeding while silently skipping checks.

---

## AMF-S0-18 — Architecture Boundaries, Threats, and ADRs

**Type:** Architecture / Security  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `adr`, `architecture`, `security`, `governance`  
**Dependencies:** AMF-S0-01

### User Story / Technical Story

As the team, we need concise architecture decision records so critical safety and ownership rules are reviewable and cannot be bypassed by implementation shortcuts.

### Context / Why This Issue Exists

The factory handles source code, commands, LLMs, filesystem paths, approvals, and long-running state. These boundaries must be explicit before real migration work begins.

### Scope

- Create ADRs for platform boundaries, state/event model, structured command authority, internal workspace/atomic delivery, deterministic components versus AI agents, untrusted repository content/LLM boundary, and SQLite MVP operating boundary.
- Add a code-review checklist linked to ADRs.
- Document forbidden shortcuts and rationale.
- Add a concise Sprint 0 threat overview covering path traversal, command injection, prompt injection, secret leakage, source mutation, duplicate execution, stale approval, and artifact overwrite.

### Out of Scope

- Full enterprise threat model.
- Formal compliance certification.
- Production RBAC design.
- Penetration testing.

### Implementation Notes

- Keep ADRs specific and actionable.
- Include examples of allowed and forbidden dependency directions.
- Document that SQLite is single-host MVP storage and define future PostgreSQL triggers.
- Link ADR rules from root README and pull-request checklist.

### Acceptance Criteria

- All seven ADRs exist and are linked.
- Forbidden shortcuts are explicit.
- Code-review checklist covers source immutability, backend state, command authority, artifact integrity, approvals, prompt injection, and delivery publication.
- Threat overview includes mitigations and future gaps.
- Team reviews and accepts the decisions.

### Definition of Done

- ADRs committed and reviewed.
- README and PR template link to ADRs.
- Sprint demo references the key boundaries.
- Open architecture questions are tracked separately.

### Risks and Edge Cases

- ADRs becoming generic and ignored.
- Documentation diverging from code.
- Security boundaries being deferred until after real execution exists.
- Team misunderstanding SQLite or LLM limits.

---

## AMF-S0-19 — Internal Workspace, Snapshot, and Atomic Delivery Skeleton

**Type:** Backend / Platform  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `workspace`, `snapshot`, `source-integrity`, `delivery`  
**Dependencies:** AMF-S0-01, AMF-S0-03

### User Story / Technical Story

As the platform, I need separate source snapshot, mutable run workspace, and delivery publication abstractions so incomplete or failed work is never exposed as the final migrated application.

### Context / Why This Issue Exists

Writing directly to `<target>/migrated-app` during migration makes partial results look complete and complicates rollback. The platform must preserve source integrity and publish only after final assurance and delivery checks.

### Scope

- Create interfaces for `SourceManifestBuilder`, `SnapshotService`, `WorkspaceService`, `SourceIntegrityVerifier`, and `DeliveryService`.
- Create canonical directories for snapshots, internal run workspaces, run artifacts, and final `migrated-app` publication.
- Implement fixture-bound source manifest and copy in automated tests.
- Implement mock delivery through temporary destination and atomic rename where supported.
- Define conflict policies for an existing `migrated-app`.
- Expose publication status and delivery manifest contracts.

### Out of Scope

- Arbitrary user-project copying.
- Production filesystem permissions.
- Remote Git clone.
- Real migration output delivery.
- Pull-request creation.

### Implementation Notes

- Canonical layout: `<target>/.migration-factory/snapshots/{snapshotId}`, `<target>/.migration-factory/workspaces/{runId}/repository`, run artifacts, and `<target>/migrated-app`.
- Source, workspace, artifact, and delivery paths must not overlap.
- Use content hashes to verify the fixture source remains unchanged.
- Failed or cancelled runs must retain internal evidence but not publish final output.

### Acceptance Criteria

- Fixture source manifest and checksum are generated.
- Fixture is copied only into the internal workspace during tests.
- Source integrity verification passes after mock workflow.
- Workspace and delivery cannot overlap source or each other incorrectly.
- Mock delivery uses temporary directory plus atomic rename where supported.
- Existing output conflict requires an explicit policy.
- Failed and cancelled mock runs do not create/publish `migrated-app`.

### Definition of Done

- Workspace/snapshot/delivery tests pass.
- Path layout documented.
- Publication state visible in API/UI mock.
- Integrity artifact generated.

### Risks and Edge Cases

- Partial output mistaken for final delivery.
- Source mutation.
- Cross-filesystem atomic rename limitations.
- Output conflict causing data loss.
- Large snapshots consuming disk space.

---

## AMF-S0-20 — State Transition, Idempotency, Lease, Cancel, and Resume Service

**Type:** Backend / Orchestration  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `state-machine`, `idempotency`, `cancellation`, `resume`, `lease`  
**Dependencies:** AMF-S0-04, AMF-S0-05

### User Story / Technical Story

As the platform, I need one transactional transition service so APIs, LangGraph nodes, workers, approvals, cancellation, and resume cannot update workflow state inconsistently.

### Context / Why This Issue Exists

Distributed-looking workflow behavior can occur even on one host: browser retries, SSE reconnects, backend restart, duplicate node execution, stale workers, and repeated approval submissions. State changes therefore need optimistic concurrency, idempotency, ordered events, and leases.

### Scope

- Implement transition request/result with run ID, event ID, event sequence, idempotency key, expected state version, previous and next state dimensions, actor, reason, artifact references, and worker lease.
- Persist state update and ordered event transactionally.
- Implement worker lease acquire/renew/release and expiry behavior.
- Implement mock cancellation sequence: request, cancelling, terminate/acknowledge, preserve evidence, cancelled.
- Implement resume validation from the last safe mock checkpoint.
- Implement idempotent approval and policy-change handling.

### Out of Scope

- Distributed consensus.
- Production job queue.
- Real process orchestration beyond the safe mock worker.
- Cross-region recovery.

### Implementation Notes

- No caller may update run/stage/step status directly in repositories.
- Every accepted transition increments state version and creates exactly one ordered event.
- A worker without a current lease cannot mark a step complete.
- Resume must validate checkpoint, workspace integrity, and policy/runtime compatibility placeholders.

### Acceptance Criteria

- Stale expected state versions are rejected.
- Duplicate idempotency keys return the existing result.
- State and event persistence are transactionally consistent.
- Worker lease prevents stale completion.
- Cancel is tested during a waiting gate and a running mock step.
- Resume continues from the last safe checkpoint.
- Repeated approval and cancellation calls are safe.
- Every accepted transition appears in state history.

### Definition of Done

- Transition service tests pass.
- Concurrency/idempotency tests pass.
- Cancel/resume tests pass.
- All mock orchestrator state changes use the service.

### Risks and Edge Cases

- Direct repository updates bypassing invariants.
- Stale worker completing after cancellation.
- Duplicate events for one transition.
- Resume from an unsafe or changed workspace.
- SQLite contention from oversized transactions.

---

## AMF-S0-21 — Observability and Run Metrics Foundation

**Type:** Backend / Platform  
**Priority:** Should  
**Suggested labels:** `sprint-0`, `observability`, `metrics`, `diagnostics`, `operations`  
**Dependencies:** AMF-S0-04, AMF-S0-08, AMF-S0-12, AMF-S0-14

### User Story / Technical Story

As an operator and developer, I need structured run metrics and diagnostics so performance, retries, cancellation, SSE behavior, commands, artifacts, and LLM usage can be understood without reading raw logs.

### Context / Why This Issue Exists

The migration factory will execute long-running, multi-stage work. Observability should be designed alongside the state model rather than added after failures become difficult to diagnose.

### Scope

- Record duration, queue wait, command duration/exit code, retry count, repair attempts, rollback count, artifact size, SSE reconnect/replay count, worker heartbeat, LLM latency/tokens/calls/failures/cost, accepted risks, manual/deferred items, and cancellation latency.
- Define structured alert events for worker loss, stuck state, source-integrity failure, disk threshold, repeated timeout, state/artifact inconsistency, and SQLite contention.
- Add a small run diagnostics summary to the Control Tower.
- Ensure metrics contain no secrets or full source code.

### Out of Scope

- Production monitoring platform integration.
- Distributed tracing backend.
- Pager/notification integration.
- Full business KPI dashboard.

### Implementation Notes

- Metrics collection must be non-authoritative and must not block state transitions when it fails.
- Use run/stage/step IDs and correlation IDs consistently.
- Aggregate LLM metrics from canonical usage records rather than parsing logs.
- Do not duplicate full logs in metrics.

### Acceptance Criteria

- Mock run metrics are queryable by run and stage.
- Control Tower displays a concise diagnostics summary.
- SSE reconnect/replay and command metrics are recorded.
- LLM usage and cost totals match usage records.
- Metrics contain no credentials or full source content.
- Metrics failure does not corrupt workflow state.
- Mock alert events can be generated in tests.

### Definition of Done

- Metric model and service tests pass.
- Diagnostics UI sample implemented.
- Alert-event vocabulary documented.
- Run report can reference metric summaries.

### Risks and Edge Cases

- High-volume metrics increasing SQLite contention.
- Sensitive data entering labels.
- Metrics becoming a second state store.
- Operator confusion between mock and real measurements.

---

# 10. Canonical State and Event Reference

## 10.1 Run Status

```text
CREATED
RUNNING
WAITING
CANCELLING
CANCELLED
COMPLETED
FAILED
DIAGNOSTIC_HOLD
```

## 10.2 Run Phase

```text
PREFLIGHT_SNAPSHOT
DISCOVERY_BASELINE
FEASIBILITY_PLANNING
STAGED_MIGRATION
FINAL_ASSURANCE
DELIVERY_REPORTING
```

## 10.3 Stage Status

```text
PENDING
RUNNING
WAITING_APPROVAL
REPAIRING
PASSED
FAILED
ROLLED_BACK
CANCELLED
DIAGNOSTIC_HOLD
```

## 10.4 Step Status

```text
PENDING
QUEUED
RUNNING
PASSED
FAILED
BLOCKED
WAITING_APPROVAL
SKIPPED
MANUAL
DEFERRED
ACCEPTED_RISK
CANCELLED
```

## 10.5 Validation Status

```text
passed
failed
not_configured
manual_validation_required
deferred_company_tool_required
blocked_by_environment
accepted_risk
skipped_not_applicable
```

## 10.6 Assurance Dimensions

Every final run must report the dimensions separately:

```text
technical_upgrade_status
functional_parity_status
security_assurance_status
quality_assurance_status
delivery_readiness
```

A successful build must not automatically imply verified functional parity.

---

# 11. Canonical Artifact Layout

```text
<target-output>/
  migrated-app/                         # published only after delivery gate
  .migration-factory/
    snapshots/
      {snapshotId}/
    workspaces/
      {runId}/
        repository/
    runs/
      {runId}/
        global/
          00_setup/
          01_discovery/
          02_baseline/
          03_analysis/
          04_planning/
          05_state/
        stages/
          {stageId}/
            00_checkpoint/
            01_transform/
            02_validation/
            03_repair/
              attempt-001/
              attempt-002/
              attempt-003/
        final_assurance/
        delivery/
        final_report/
```

Every artifact uses an immutable envelope:

```json
{
  "schema_version": "1.0",
  "artifact_id": "uuid",
  "run_id": "uuid",
  "stage_id": "angular-18-to-19",
  "attempt": 1,
  "producer": "repair_agent",
  "created_at": "ISO-8601",
  "artifact_type": "repair_patch_proposal",
  "content_type": "application/json",
  "input_artifact_hashes": [],
  "policy_version": "policy-v1",
  "content_hash": "sha256:...",
  "relative_path": "stages/angular-18-to-19/03_repair/attempt-001/proposal.json"
}
```

---

# 12. Canonical Structured Command Contract

```json
{
  "command_id": "node_version",
  "executable": "node",
  "arguments": ["--version"],
  "shell": false,
  "working_directory_alias": "run_workspace",
  "runtime_profile_id": "source-runtime-profile",
  "timeout_seconds": 30,
  "network_profile": "none",
  "cancellation_policy": "terminate_process_tree",
  "idempotency_key": "run-001-node-version-v1",
  "requested_by": "runtime_preflight_component"
}
```

The backend rejects:

- unknown command IDs;
- non-allowlisted executables or arguments;
- `shell=true`;
- arbitrary working directories;
- unknown runtime profiles;
- duplicate execution without idempotent result reuse;
- commands requested directly by the frontend or LLM.

---

# 13. Recommended Dependency and Delivery Order

The team may parallelize work, but contracts must stabilize before dependent implementation expands.

1. AMF-S0-01 — Repository and Platform Boundary Skeleton
2. AMF-S0-18 — Architecture Boundaries, Threats, and ADRs
3. AMF-S0-02 — FastAPI Backend and API Surface Skeleton
4. AMF-S0-03 — Configuration, Policy, and Environment Foundation
5. AMF-S0-05 — Canonical Contracts and State Vocabulary
6. AMF-S0-04 — SQLAlchemy, Alembic, and SQLite State Schema
7. AMF-S0-19 — Internal Workspace, Snapshot, and Atomic Delivery
8. AMF-S0-20 — State Transition, Idempotency, Lease, Cancel, and Resume
9. AMF-S0-11 — Immutable Stage-Scoped Artifact Store
10. AMF-S0-12 — Structured Command Worker and Supervisor
11. AMF-S0-13 — Preflight and Runtime Capability
12. AMF-S0-08 — Ordered SSE, Replay, and State Recovery
13. AMF-S0-09 — Optimized LangGraph Mock Orchestrator
14. AMF-S0-10 — Deterministic Component and AI-Agent Contracts
15. AMF-S0-06 — Next.js Control Tower Skeleton
16. AMF-S0-07 — Generated Typed Frontend API Client
17. AMF-S0-14 — LLM Gateway Mock, Redaction, Usage, and Cost
18. AMF-S0-15 — Log, Diff, Markdown, and Artifact Viewers
19. AMF-S0-16 — Angular 18 Fixture and Evaluation Foundation
20. AMF-S0-21 — Observability and Run Metrics Foundation
21. AMF-S0-17 — Developer Scripts and Quality Gates

### Parallel Work After Contract Stabilization

- The fixture and ADR work can begin immediately.
- The frontend shell can progress against generated mock DTOs after AMF-S0-05.
- Artifact and workspace services can progress alongside persistence after path and envelope contracts are frozen.
- The LLM Gateway mock can progress independently after agent and usage contracts exist.
- Viewers can progress against static mock artifacts while the artifact API is completed.

---

# 14. Sprint 0 Definition of Done

Sprint 0 is complete when all of the following are true:

- FastAPI and Next.js run locally.
- Setup validation produces a checksum-bound, expiring preflight result.
- Mock run creation requires a valid preflight checksum.
- Run status, run phase, stage status, and step status are separate canonical contracts.
- SQLite/Alembic supports state versions, ordered events, commands, leases, approvals, artifacts, repair attempts, assurance statuses, and LLM usage.
- A single transition service controls all mock workflow state changes.
- LangGraph executes the optimized six-phase mock workflow.
- Parallel mock discovery fan-out/fan-in works.
- Analysis and plan approvals pause and resume durably.
- Auto approval is persisted, read at every gate, and immediately reevaluates the current eligible gate.
- SSE supports ordered IDs, replay, duplicate suppression, heartbeat, and snapshot recovery.
- Deterministic components and AI-assisted agents are separated in code, execution history, and UI labels.
- Commands use structured requests with `shell=false`, allowlists, runtime profile, idempotency, timeout, and cancellation policy.
- Safe runtime version commands execute only through the worker.
- Internal snapshot, workspace, artifact, and delivery directories are distinct.
- Failed and cancelled runs do not publish `migrated-app`.
- Artifacts are append-only, checksum-bound, and stage/repair-attempt scoped.
- The UI safely opens logs, diffs, Markdown reports, and artifact metadata.
- Mock cancellation and resume operate from backend state.
- The LLM Gateway mock redacts secrets and treats repository content as untrusted data.
- LLM usage records include input, output, total tokens, pricing snapshot, and cost.
- The Angular 18 fixture includes expected baseline, discovery, backend-contract, risk, and parity manifests.
- Observability records basic run, SSE, command, artifact, cancellation, and LLM metrics.
- ADRs document all critical boundaries and forbidden shortcuts.
- Developer scripts and the Sprint 0 demo are reproducible.
- No real `ng update`, arbitrary package installation, real repair, or arbitrary user-source mutation occurs.

---

# 15. Guidance for Work Already Started

Do not discard valid skeleton code. Apply the optimized design in this order:

1. Freeze AMF-S0-05 contracts before adding more UI cards or graph states.
2. Update AMF-S0-04 persistence to match the separated state dimensions.
3. Replace raw command fields before adding any additional command execution.
4. Introduce AMF-S0-20 before implementing more approval, cancellation, or resume logic.
5. Upgrade SSE before many UI features rely on an unreliable event model.
6. Change artifact paths before later sprints generate real stage evidence.
7. Treat `migrated-app/` as a publication target, never as the active workspace.
8. Keep the existing Angular 18 fixture but enrich it with expectation manifests and controlled regression cases.
9. Preserve working FastAPI/Next.js scaffolding and add missing modules incrementally rather than repeatedly reorganizing the repository.
10. Record any deliberate temporary deviation as a backlog item or ADR decision; do not silently build against obsolete contracts.

---

# 16. Sprint 0 Non-Negotiable Rules

```text
Frontend does not infer workflow progress.
Agents and LLMs do not execute commands.
Only the backend transition service changes workflow state.
Only the backend command authority starts processes.
Repository content is untrusted data, not policy.
Original source remains immutable.
Mutation occurs only inside the internal run workspace.
Artifacts are immutable evidence.
SSE is not the source of truth.
Approvals are checksum-bound and state-bound.
Auto approval never bypasses forbidden or high-risk gates.
Failed or cancelled work is never published as migrated-app.
Technical build success is not automatically functional-parity proof.
```