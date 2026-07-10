# AI Frontend Migration Factory — Sprint 0 Backlog

**Sprint 0:** Technical Skeleton, Contracts, Mock Workflow, and Developer Foundation  
**Project:** AI Frontend Migration Factory  
**MVP reference migration:** Angular 18.x → Angular 21.x  
**Migration mode:** Strict compatibility / strict functional parity  
**Backend:** unchanged  
**Mutation policy:** sandbox-only  
**Execution authority:** backend-controlled  

---

## 1. Sprint Goal

Create the clean technical foundation of the AI Frontend Migration Factory using the final stack, without implementing real Angular migration logic yet.

Sprint 0 must prove that the product is being built as a **platform** and not as a one-shot migration script. The goal is to establish the backend, frontend, contracts, mock workflow, mock agents, artifact structure, execution boundaries, and local developer workflow.

---

## 2. Sprint Outcome / Demo

At the end of Sprint 0, the team can:

- Run the FastAPI backend locally with Uvicorn.
- Run the Next.js Control Tower frontend locally.
- Open the migration setup page.
- Create a mock migration run.
- Watch mock workflow progress through Server-Sent Events.
- See mock stages, mock agents, mock validation gates, mock approvals, mock artifacts, mock logs, mock diff, and mock Markdown report.
- Confirm that the repository structure, contracts, state model, artifact folder model, and future sandbox execution boundaries are ready.
- Confirm that the frontend renders backend-owned state and does not infer workflow state locally.

---

## 3. Main Technical Focus

- Repository and workspace structure.
- FastAPI backend shell.
- Next.js Control Tower shell.
- Pydantic v2 API contracts.
- SQLAlchemy / Alembic / SQLite bootstrap.
- Server-Sent Events skeleton.
- LangGraph mock orchestration.
- Mock agents with shared input/output contracts.
- Local filesystem artifact store skeleton.
- Python sandbox execution worker shell.
- Azure OpenAI LLM Gateway mock.
- Runtime preflight checker.
- Custom log viewer, unified diff viewer, and Markdown report viewer skeleton.
- Angular 18 fixture project.
- Local developer scripts and quality checks.
- Architecture boundary documentation.

---

## 4. Dependencies on Previous Sprints

None.

Sprint 0 is the foundation sprint.

---

## 5. Stack for Sprint 0

### Backend

- Python
- FastAPI
- Uvicorn
- Pydantic v2
- SQLAlchemy
- Alembic
- SQLite
- LangGraph
- Azure OpenAI LLM Gateway shell
- Local filesystem artifact store
- Python sandbox execution worker shell
- Server-Sent Events

### Migration Worker Runtime

- Python
- Node.js
- npm
- Angular CLI through `npx`
- Git

### Frontend

- Node.js
- Next.js
- React
- TypeScript
- Custom React components with CSS Modules
- Server-Sent Events client
- Custom log viewer
- Custom unified diff viewer
- Markdown report viewer

---

## 6. Sprint 0 Demo Scenario

The Sprint 0 demo should follow this sequence:

```text
1. Start FastAPI backend with Uvicorn.
2. Start Next.js frontend.
3. Open /migrations/new.
4. Click “Start Mock Migration”.
5. Backend creates a mock run DTO.
6. LangGraph mock workflow starts.
7. SSE streams backend-owned state updates.
8. UI shows stages:
   - Angular 18.x → 19.x
   - Angular 19.x → 20.x
   - Angular 20.x → 21.x
9. UI shows mock agents:
   - Eligibility Agent
   - Analysis Agent
   - Planning Agent
   - Transformation Agent
   - Build / Validation Agent
   - Repair Agent
   - Report Agent
10. UI opens mock command log.
11. UI opens mock unified diff.
12. UI opens mock Markdown report.
13. Artifact folders are created locally.
14. Runtime preflight report shows Python, Node, npm, npx, and Git availability.
```

---

## 7. Sprint 0 Should Not Include Yet

The following items must stay out of Sprint 0 to keep the sprint focused on the technical skeleton:

| Not in Sprint 0 | Reason |
|---|---|
| Real migration job creation | Sprint 1 platform foundation. |
| Real sandbox copy of source project | Sprint 1. |
| Real eligibility scan | Sprint 1. |
| Real baseline install/build/test/lint | Sprint 1. |
| Real Angular analysis | Sprint 2. |
| Real compatibility resolver | Sprint 2. |
| Real `ng update` execution | Sprint 3. |
| Real repair patches | Sprint 4. |
| Real final evidence report | Sprint 4. |

---

# 8. Issues

---

## AMF-S0-01 — Repository and Workspace Skeleton

**Type:** DevOps / Infrastructure  
**Priority:** Must  
**Suggested labels:** `sprint-0`, `repo-structure`, `foundation`, `devex`  
**Dependencies:** None

### User Story / Technical Story

As a development team, we need a clean repository structure so backend, frontend, agents, orchestration, shared contracts, demo apps, scripts, and docs are separated from the beginning.

### Context / Why This Issue Exists

The AI Frontend Migration Factory is a platform composed of several parts: Control Tower UI, backend execution authority, LangGraph orchestrator, agents, artifact store, state store, sandbox execution worker, and reporting layer.

If the repository structure is not clear from the start, the team may mix workflow logic, UI logic, command execution, and agent logic in the same places. That would make the solution hard to maintain and unsafe.

### Scope

Create the repository structure:

```text
backend/
frontend/
shared/
demo-apps/
scripts/
docs/
tests/
```

Add README files for the main folders:

```text
backend/README.md
frontend/README.md
shared/README.md
demo-apps/README.md
scripts/README.md
docs/README.md
```

### Out of Scope

- Real migration execution.
- Real Angular analysis.
- Real LLM calls.
- Real command execution.

### Implementation Notes

The repository should reflect the platform boundaries:

- `backend/` owns APIs, persistence, orchestration services, artifact access, approval processing, command execution authority, sandbox policy, and LLM Gateway.
- `frontend/` owns the Control Tower UI only.
- `shared/` can contain schema documentation, generated client types, or shared contract references.
- `demo-apps/` contains fixture Angular apps.
- `scripts/` contains local developer scripts.
- `docs/` contains architecture notes, ADRs, setup docs, and sprint documentation.

### Acceptance Criteria

- Repository has clear top-level folders.
- Backend and frontend can be started independently.
- Each main folder has a README.
- No migration logic is placed in the frontend.
- No command execution logic is placed in agents directly.

### Definition of Done

- Project structure committed.
- Root README explains the architecture boundaries.
- Folder-level README files are present.
- Team can understand where to add backend, frontend, agent, orchestration, and documentation code.

### Risks and Edge Cases

- A poor structure may turn the MVP into a script instead of a platform.
- Developers may accidentally put workflow logic in the frontend.
- Agents may accidentally bypass the backend execution authority if boundaries are not explicit.

---

## AMF-S0-02 — Backend FastAPI Skeleton

**Type:** Backend  
**Priority:** Must  
**Suggested labels:** `backend`, `fastapi`, `uvicorn`, `foundation`  
**Dependencies:** AMF-S0-01

### User Story / Technical Story

As a backend developer, I need a FastAPI skeleton so the migration APIs, state services, artifact services, orchestration services, and agent services can be implemented safely later.

### Context / Why This Issue Exists

The backend is the execution authority of the migration factory. It must own run state, stage state, artifact access, command execution, approvals, sandbox policy, and LLM Gateway access.

Sprint 0 does not implement the real migration yet, but it must create the backend structure that all later sprints will build on.

### Scope

Create the FastAPI backend structure:

```text
backend/app/main.py
backend/app/api/
backend/app/core/
backend/app/domain/
backend/app/services/
backend/app/repositories/
backend/app/orchestration/
backend/app/agents/
backend/app/artifact_store/
backend/app/sandbox/
backend/app/command_execution/
backend/app/llm_gateway/
```

Add initial endpoints:

```http
GET /health
GET /version
GET /migrations/mock-state
```

### Out of Scope

- Real migration creation.
- Real sandbox creation.
- Real command execution.
- Real database-backed workflow state.

### Implementation Notes

Use FastAPI and Pydantic v2.

Keep API routers thin. Business logic must be placed in services. Repository logic must be separated from services. Orchestration must not be implemented directly inside API handlers.

Suggested initial router structure:

```text
backend/app/api/routes/health.py
backend/app/api/routes/version.py
backend/app/api/routes/migrations.py
```

### Acceptance Criteria

- Backend starts successfully with Uvicorn.
- `GET /health` returns an OK response.
- `GET /version` returns app name, version, and environment.
- `GET /migrations/mock-state` returns a valid mock migration run DTO.
- Backend module structure is clear and documented.

### Definition of Done

- Backend README added.
- Basic tests for health and version endpoints added.
- Uvicorn start command documented.
- No workflow logic is hardcoded in routers.

### Risks and Edge Cases

- If routers contain business logic early, the backend will become hard to maintain.
- If the backend skeleton ignores orchestration and command execution boundaries, agents may later bypass platform rules.

---

## AMF-S0-03 — Backend Configuration and Environment Setup

**Type:** Backend  
**Priority:** Must  
**Suggested labels:** `backend`, `configuration`, `environment`, `devex`  
**Dependencies:** AMF-S0-02

### User Story / Technical Story

As a developer, I need centralized configuration so paths, database URL, artifact root, sandbox root, CORS, command timeout, and LLM settings are not hardcoded.

### Context / Why This Issue Exists

The migration factory will run local filesystem operations, command execution, artifact persistence, and LLM calls. These settings must be configurable and safe.

Hardcoded local paths or credentials would make the application fragile and unsafe.

### Scope

Add backend configuration for:

```text
APP_ENV
DATABASE_URL
ARTIFACT_ROOT
SANDBOX_ROOT
BACKEND_CORS_ORIGINS
COMMAND_TIMEOUT_SECONDS
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_DEPLOYMENT
AZURE_OPENAI_API_VERSION
AZURE_OPENAI_API_KEY
LLM_ENABLED
```

Add:

```text
backend/.env.example
```

### Out of Scope

- Real Azure OpenAI call.
- Secret manager integration.
- Production deployment configuration.

### Implementation Notes

Use Pydantic settings.

Secrets must never be returned to the frontend. Secrets must not be logged. Any future configuration endpoint must return redacted values only.

### Acceptance Criteria

- Backend loads configuration from environment variables or `.env`.
- Missing required local configuration fails with a readable error.
- `.env.example` contains safe placeholders only.
- No secret is logged at startup.

### Definition of Done

- Configuration tests added.
- `.env.example` committed.
- README explains local configuration.

### Risks and Edge Cases

- Hardcoded Windows paths can break other developer environments.
- Logging Azure OpenAI credentials would be a serious security issue.
- CORS misconfiguration can block the frontend during local development.

---

## AMF-S0-04 — SQLAlchemy, Alembic, and SQLite Bootstrap

**Type:** Backend  
**Priority:** Must  
**Suggested labels:** `backend`, `sqlite`, `sqlalchemy`, `alembic`, `state-store`  
**Dependencies:** AMF-S0-02, AMF-S0-03

### User Story / Technical Story

As the platform, I need a database foundation so Sprint 1 can persist migration run state, stage state, approvals, artifacts, and agent history.

### Context / Why This Issue Exists

The frontend must never infer workflow state locally. Backend-owned state requires persistence. SQLite is sufficient for the MVP, but the structure should be clean enough to evolve later.

### Scope

Add SQLAlchemy setup, Alembic setup, and SQLite database connection.

Create initial placeholder tables:

```text
migration_runs
migration_stages
agent_executions
artifact_metadata
approval_events
workflow_events
```

### Out of Scope

- Full real workflow persistence.
- Resume logic.
- Production database support.

### Implementation Notes

Use Alembic migrations from Sprint 0. Mock state can optionally be stored in SQLite to validate the persistence pattern.

Suggested repository structure:

```text
backend/app/repositories/models/
backend/app/repositories/session.py
backend/alembic/
```

### Acceptance Criteria

- Alembic can create the SQLite schema.
- Backend starts with database connection.
- A test can insert and read a mock migration run.
- Database path is configurable.

### Definition of Done

- Initial Alembic migration committed.
- Database setup documented.
- Persistence test added.

### Risks and Edge Cases

- If persistence is delayed, Sprint 1 will become overloaded.
- If state is only in memory, refresh/resume behavior cannot be validated later.

---

## AMF-S0-05 — Shared API Contracts and OpenAPI Foundation

**Type:** Backend  
**Priority:** Must  
**Suggested labels:** `contracts`, `pydantic-v2`, `openapi`, `state-model`  
**Dependencies:** AMF-S0-02

### User Story / Technical Story

As the team, we need shared contracts so backend, frontend, orchestrator, and agents use the same vocabulary.

### Context / Why This Issue Exists

The migration workflow has many states: run states, stage states, agent statuses, validation gate statuses, approval decisions, command statuses, risk levels, and final statuses.

If these contracts are not defined early, the frontend may invent statuses and agents may return inconsistent outputs.

### Scope

Define Pydantic v2 schemas for:

```text
MigrationRunDto
MigrationStageDto
AgentExecutionDto
ValidationGateDto
ApprovalEventDto
ArtifactRefDto
CommandRequestDto
CommandResultDto
PatchLedgerEntryDto
RepairAttemptDto
WorkflowEventDto
```

Define enums for:

```text
RunStatus
StageStatus
AgentStatus
ValidationStatus
ApprovalDecision
RiskLevel
ArtifactType
CommandStatus
```

### Out of Scope

- Real workflow enforcement.
- Generated TypeScript client. That is handled in AMF-S0-07.

### Implementation Notes

Status names must match the architecture vocabulary, including:

```text
WAITING_ANALYSIS_APPROVAL
WAITING_PLAN_APPROVAL
STAGE_RUNNING
REPAIR_RUNNING
WAITING_REPAIR_APPROVAL
DIAGNOSTIC_HOLD
CANCELLED
COMPLETED_WITH_MANUAL_ITEMS
COMPLETED_WITH_ACCEPTED_RISK
```

Validation statuses must include:

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

### Acceptance Criteria

- OpenAPI contains all mock DTOs.
- Invalid enum values are rejected.
- Mock state endpoint uses these contracts.
- Every DTO includes required IDs and timestamps where relevant.

### Definition of Done

- Schema tests added.
- Contracts documented.
- Frontend can consume the mock DTO shape.

### Risks and Edge Cases

- Missing statuses will hide blocked workflow reasons.
- Too many uncontrolled statuses will confuse UI rendering.
- Inconsistent naming between backend and frontend will cause contract drift.

---

## AMF-S0-06 — Frontend Next.js Control Tower Skeleton

**Type:** Frontend  
**Priority:** Must  
**Suggested labels:** `frontend`, `nextjs`, `react`, `typescript`, `control-tower`  
**Dependencies:** AMF-S0-05

### User Story / Technical Story

As a user, I need a first Control Tower UI shell so I can create a mock migration and follow backend-owned workflow state.

### Context / Why This Issue Exists

The Control Tower is the main product interface. It must show the migration setup, workflow state, stage progress, agent activity, validation gates, approvals, logs, diffs, reports, and assistant entry point.

Sprint 0 should create the skeleton UI using mock backend-shaped data.

### Scope

Create a Next.js app with React, TypeScript, and CSS Modules.

Pages:

```text
/migrations/new
/migrations/[runId]
```

Components:

```text
ControlTowerShell
MigrationSetupForm
RunHeader
WorkflowTimeline
StageCards
AgentActivityPanel
ValidationGatePanel
ApprovalPanel
ArtifactPanel
AssistantPanel
ReportPanel
```

### Out of Scope

- Real job creation.
- Real approval actions.
- Real artifact browser.
- Real assistant chat.

### Implementation Notes

The UI must render backend DTOs. It must not contain a local workflow state machine.

The setup form should include:

```text
sourcePath
targetOutputPath
targetAngularFamily
migrationMode
autoApprovalEnabled
```

For Sprint 0, the Start button can call a mock endpoint or route to a mock run page.

### Acceptance Criteria

- Frontend starts locally.
- Setup page renders.
- Mock run page renders backend mock state.
- Stage and agent cards use backend status values.
- Manual/deferred gates are displayed clearly.

### Definition of Done

- Frontend README added.
- Basic render tests added.
- No local state inference logic exists in frontend.

### Risks and Edge Cases

- The frontend may accidentally implement fake progress logic.
- UI components may use labels that do not match backend enums.

---

## AMF-S0-07 — Typed Frontend API Client Foundation

**Type:** Frontend  
**Priority:** Should  
**Suggested labels:** `frontend`, `api-client`, `openapi`, `typescript`  
**Dependencies:** AMF-S0-05, AMF-S0-06

### User Story / Technical Story

As a frontend developer, I need a typed API client so frontend DTOs stay aligned with backend OpenAPI contracts.

### Context / Why This Issue Exists

The Control Tower will consume many backend DTOs. A typed API client reduces contract drift and prevents scattered `fetch()` calls across UI components.

### Scope

Add API client layer:

```text
frontend/src/api/client.ts
frontend/src/api/migrations.ts
frontend/src/types/generated/
```

Use generated or manually synchronized types for Sprint 0.

### Out of Scope

- Authentication.
- Production API gateway.
- Advanced retry policy.

### Implementation Notes

Centralize backend base URL configuration.

All UI calls must go through the API client layer.

### Acceptance Criteria

- Frontend can fetch `/health`.
- Frontend can fetch `/version`.
- Frontend can fetch `/migrations/mock-state`.
- Types are reused in UI components.
- No scattered direct `fetch()` calls exist across components.

### Definition of Done

- API client documented.
- Basic API client test or mocked integration test added.

### Risks and Edge Cases

- Contract drift between backend and frontend.
- Frontend components becoming tightly coupled to raw API calls.

---

## AMF-S0-08 — Server-Sent Events Backend and Frontend Skeleton

**Type:** Backend / Frontend  
**Priority:** Must  
**Suggested labels:** `sse`, `realtime-state`, `control-tower`, `backend-state`  
**Dependencies:** AMF-S0-05, AMF-S0-06

### User Story / Technical Story

As a user, I need the Control Tower to receive backend workflow state updates without the frontend inventing progress locally.

### Context / Why This Issue Exists

The frontend must not infer workflow status locally. Server-Sent Events will allow the backend to push workflow updates to the Control Tower.

Sprint 0 should validate the real-time communication pattern using mock events.

### Scope

Backend endpoint:

```http
GET /migrations/{runId}/events
```

Frontend hook:

```text
useMigrationEvents(runId)
```

Mock event types:

```text
run_state_changed
stage_state_changed
agent_state_changed
validation_gate_changed
artifact_created
approval_required
workflow_completed
```

### Out of Scope

- Production-grade retry strategy.
- Backpressure handling.
- Real orchestration events.

### Implementation Notes

SSE should stream mock workflow events from the backend.

The frontend should update rendered state only from backend event payloads or backend state refetches.

### Acceptance Criteria

- UI receives mock events.
- Stage status updates through SSE.
- Agent status updates through SSE.
- Connection loss displays a clear reconnecting state.
- Refreshing the page reloads state from backend mock endpoint.

### Definition of Done

- SSE endpoint tested.
- Frontend hook tested.
- Control Tower connected to mock stream.

### Risks and Edge Cases

- Duplicate events.
- Reconnection after backend restart.
- Stale state after page refresh.
- UI state diverging from backend state.

---

## AMF-S0-09 — LangGraph Mock Orchestrator Skeleton

**Type:** Orchestration  
**Priority:** Must  
**Suggested labels:** `langgraph`, `orchestration`, `mock-workflow`, `state-machine`  
**Dependencies:** AMF-S0-04, AMF-S0-05, AMF-S0-08

### User Story / Technical Story

As the platform, I need a LangGraph-based mock orchestrator so workflow sequencing is designed before real agents are implemented.

### Context / Why This Issue Exists

The orchestrator is responsible for state transitions, approval pauses, stage sequencing, repair loop control, cancellation, diagnostic hold, and final reporting.

Sprint 0 should create the graph shape with mock nodes so future real agents can replace mock logic incrementally.

### Scope

Create mock LangGraph nodes:

```text
create_run_mock
eligibility_mock
baseline_mock
analysis_mock
wait_analysis_approval_mock
planning_mock
wait_plan_approval_mock
stage_18_to_19_mock
stage_19_to_20_mock
stage_20_to_21_mock
report_mock
```

### Out of Scope

- Real agents.
- Real approval persistence.
- Real migration.
- Real validation.

### Implementation Notes

The mock graph must call backend services to update state and emit SSE events.

Graph nodes must not write directly to the frontend or bypass state services.

### Acceptance Criteria

- Mock graph can run end to end.
- Mock graph pauses at mock approval gates.
- Mock graph emits backend state updates.
- Control Tower displays progress from the graph.
- Stage order is Angular 18→19, 19→20, 20→21.

### Definition of Done

- Graph test added.
- State transition test added.
- Demo flow documented.

### Risks and Edge Cases

- The orchestrator may duplicate backend state logic if boundaries are not clear.
- Approval pauses may be skipped if the mock graph is too simple.

---

## AMF-S0-10 — Common Agent Contract and Mock Agents

**Type:** Agent  
**Priority:** Must  
**Suggested labels:** `agents`, `contract`, `mock-agent`, `sprint-0`  
**Dependencies:** AMF-S0-05, AMF-S0-09

### User Story / Technical Story

As the platform, I need a common agent contract so future real agents behave consistently.

### Context / Why This Issue Exists

Every agent must have bounded responsibilities and structured inputs/outputs. Agents must not directly execute commands, approve gates, mutate files, or bypass backend authority.

### Scope

Define common input envelope:

```text
run_id
stage_id
workspace
client_constraints
current_workflow_state
allowed_actions
artifact_locations
approved_plan_checksum
```

Define common output envelope:

```text
agent_name
run_id
stage_id
status
summary
artifacts_created
risks
requires_human_action
next_recommended_state
```

Create mock agents:

```text
AI Assistant Agent
Eligibility and Constraint Agent
Analysis Agent
Planning Agent
Transformation Agent
Build / Validation Agent
Repair Agent
Report Agent
```

### Out of Scope

- LLM reasoning.
- File mutation.
- Shell execution.
- Real analysis.

### Implementation Notes

Mock agents must return structured outputs only.

Agents must never call shell commands directly. They can only return action requests for the backend to validate in later sprints.

### Acceptance Criteria

- Every mock agent uses the same input/output envelope.
- Agent executions are recorded.
- Completed, failed, blocked, skipped, and requires approval statuses are supported.
- Mock artifacts are created by mock agents through the artifact service.

### Definition of Done

- Agent contract documented.
- Mock agent tests added.
- Orchestrator calls mock agents using the shared contract.

### Risks and Edge Cases

- Agent contract may become too permissive.
- Future real agents may bypass backend authority if this boundary is not established early.

---

## AMF-S0-11 — Local Filesystem Artifact Store Skeleton

**Type:** Backend  
**Priority:** Must  
**Suggested labels:** `artifact-store`, `filesystem`, `audit`, `evidence`  
**Dependencies:** AMF-S0-03, AMF-S0-05

### User Story / Technical Story

As the platform, I need a local filesystem artifact store so every mock step can write evidence in the final folder structure.

### Context / Why This Issue Exists

Artifacts are the evidence backbone of the migration factory. Every future analysis, approval, command, patch, validation, repair, rollback, and report must be reviewable and auditable.

### Scope

Create artifact layout:

```text
.migration-factory/runs/{runId}/
  00_job_setup/
  01_baseline/
  02_analysis/
  03_planning/
  04_workflow_state/
  05_sandbox_transform/
  06_validation/
  07_repair/
  08_final/
```

Support writing:

```text
JSON
YAML
Markdown
text logs
patch/diff files
```

### Out of Scope

- Cloud storage.
- Real report generation.
- Advanced artifact indexing.

### Implementation Notes

Every artifact should include metadata:

```text
run_id
stage_id when applicable
created_at
created_by
artifact_type
checksum
```

The artifact service must prevent path traversal.

### Acceptance Criteria

- Mock workflow creates artifact folders.
- Mock artifacts can be listed.
- Mock artifacts can be opened from UI.
- No artifact can be written outside artifact root.
- Artifact checksums are generated.

### Definition of Done

- Artifact writer tested.
- Artifact folder contract documented.
- UI can open mock artifact references.

### Risks and Edge Cases

- Artifact paths may become inconsistent across agents.
- Path traversal could expose files outside the artifact root.
- User-facing migrated app files may be mixed with internal evidence if layout is unclear.

---

## AMF-S0-12 — Python Sandbox Execution Worker Shell

**Type:** Backend  
**Priority:** Must  
**Suggested labels:** `sandbox`, `execution-worker`, `command-authority`, `security`  
**Dependencies:** AMF-S0-02, AMF-S0-03

### User Story / Technical Story

As the backend execution authority, I need a sandbox execution worker interface so future commands can only run through controlled backend validation.

### Context / Why This Issue Exists

The architecture requires backend-controlled command execution. Agents and LLMs may propose actions, but the backend validates and executes them.

Sprint 0 should not run migration commands, but it must establish the execution boundary.

### Scope

Create execution worker abstraction:

```text
CommandRequest
CommandPolicy
CommandExecutionResult
ExecutionWorker
CommandLogWriter
```

For Sprint 0, implement only safe preflight commands:

```text
python --version
node --version
npm --version
git --version
```

### Out of Scope

- `ng update`.
- `npm install`.
- File mutation.
- Real sandbox workspace creation.

### Implementation Notes

All future command execution must pass through this interface.

Record:

```text
command
working_directory
requester
stdout
stderr
exit_code
started_at
finished_at
duration_ms
status
```

### Acceptance Criteria

- Worker can run safe preflight version commands.
- Commands outside allowlist are rejected.
- Command result is stored as mock command log artifact.
- Command logs are visible through artifact API.

### Definition of Done

- Execution worker tests added.
- Unsafe command rejection tested.
- Command log artifact generated.

### Risks and Edge Cases

- Command injection.
- Path traversal.
- Long-running processes.
- Windows vs Linux command differences.
- Shell-specific behavior.

---

## AMF-S0-13 — Runtime Preflight Checker

**Type:** DevOps / Infrastructure  
**Priority:** Must  
**Suggested labels:** `runtime`, `preflight`, `node`, `npm`, `git`, `angular-cli`  
**Dependencies:** AMF-S0-12

### User Story / Technical Story

As a developer, I need to know whether the local machine has the required worker runtime before real migration execution starts in later sprints.

### Context / Why This Issue Exists

The migration worker runtime depends on Python, Node.js, npm, npx, Angular CLI through npx, and Git. Missing tools or PATH issues should be detected early.

### Scope

Check availability of:

```text
Python
Node.js
npm
npx
Git
Angular CLI through npx
```

Generate artifact:

```text
00_job_setup/runtime_preflight_report.json
```

### Out of Scope

- Automatic installation of missing tools.
- Real Angular project validation.
- Exact Angular compatibility checks.

### Implementation Notes

For Sprint 0, the checker can verify command availability and versions. Full project-specific `npx ng version` validation can be refined later.

### Acceptance Criteria

- Preflight checker reports installed and missing tools.
- Missing tool produces clear status, not a crash.
- Report is visible in UI artifact panel.
- Result includes command, detected version when available, and status.

### Definition of Done

- Preflight checker test added.
- Documentation explains required local runtime.
- Mock preflight report generated during Sprint 0 demo.

### Risks and Edge Cases

- Corporate proxy.
- Node version mismatch.
- npm not in PATH.
- Git not in PATH.
- `npx` blocked or unavailable.

---

## AMF-S0-14 — Azure OpenAI LLM Gateway Mock

**Type:** Backend / Agent  
**Priority:** Should  
**Suggested labels:** `llm-gateway`, `azure-openai`, `mock`, `governance`  
**Dependencies:** AMF-S0-03, AMF-S0-10

### User Story / Technical Story

As an agent engineer, I need a backend-controlled LLM Gateway interface so agents can later request LLM help without receiving credentials or executing actions directly.

### Context / Why This Issue Exists

All agents may later use Azure OpenAI for summaries, planning narratives, failure diagnosis, patch proposals, and report generation. However, agents and frontend must never receive credentials and the LLM must never execute commands or mutate files.

### Scope

Create LLM Gateway interface:

```text
LlmRequest
LlmResponse
LlmUsage
LlmRedactionResult
```

Add mock response for Sprint 0.

Add redaction utility placeholder.

Add artifact placeholder:

```text
04_workflow_state/llm_interaction_log_redacted.json
```

### Out of Scope

- Real Azure OpenAI API call.
- Token cost calculation.
- Prompt engineering for real agents.

### Implementation Notes

The gateway must hide endpoint, deployment name, API version, and API key from agents and frontend.

LLM output must be treated as a proposal only.

### Acceptance Criteria

- Mock agent can call LLM Gateway mock.
- LLM request/response metadata is logged without secrets.
- Frontend never receives LLM credentials.
- Mock LLM usage is visible as an artifact.

### Definition of Done

- Gateway interface documented.
- Mock tests added.
- Secret redaction placeholder tested with sample sensitive strings.

### Risks and Edge Cases

- Agents may later bypass the gateway if the boundary is not enforced early.
- Secrets may be logged accidentally.
- LLM output may be treated as trusted execution logic.

---

## AMF-S0-15 — Custom Log Viewer, Diff Viewer, and Markdown Report Viewer Skeleton

**Type:** Frontend  
**Priority:** Should  
**Suggested labels:** `frontend`, `log-viewer`, `diff-viewer`, `markdown-viewer`  
**Dependencies:** AMF-S0-06, AMF-S0-11

### User Story / Technical Story

As a user, I need to inspect logs, diffs, and Markdown reports from the Control Tower.

### Context / Why This Issue Exists

The final product must be reviewable and auditable. Users must be able to inspect command logs, source diffs, validation reports, repair reports, and final evidence reports.

Sprint 0 should create the basic UI components using mock artifacts.

### Scope

Create components:

```text
LogViewer
UnifiedDiffViewer
MarkdownReportViewer
ArtifactPreviewPanel
```

Use mock artifacts from the artifact store.

### Out of Scope

- Advanced syntax highlighting.
- Side-by-side diff view.
- PDF/DOCX report preview.

### Implementation Notes

The unified diff viewer should support:

```text
+ added lines
- removed lines
context lines
file headers
```

The Markdown viewer should render report content safely.

### Acceptance Criteria

- User can open a mock command log.
- User can open a mock unified diff.
- User can open a mock Markdown report.
- Large content is displayed in a scrollable panel.
- Unsafe Markdown rendering is avoided.

### Definition of Done

- Components created.
- Components connected to mock artifact API.
- Basic visual/rendering tests added.

### Risks and Edge Cases

- Very large logs.
- Unsafe Markdown rendering.
- Poor diff readability.
- Browser performance with large artifacts.

---

## AMF-S0-16 — Demo Angular 18 Fixture Project

**Type:** DevOps / Infrastructure  
**Priority:** Must  
**Suggested labels:** `demo-app`, `angular18`, `fixture`, `mvp-demo`  
**Dependencies:** None

### User Story / Technical Story

As the team, we need a small Angular 18.x fixture so future sprints can test analysis, staged migration, validation, repair, and reporting.

### Context / Why This Issue Exists

The MVP reference migration is Angular 18.x to Angular 21.x. The team needs a stable app to validate the workflow repeatedly.

### Scope

Add or document fixture under:

```text
demo-apps/angular-18-basic/
```

The fixture should include:

```text
package.json
angular.json
tsconfig files
src/app routes
environment files
simple HTTP service
component template
optional test/lint scripts
```

### Out of Scope

- Backend app.
- Complex authentication.
- Enterprise-scale fixture.

### Implementation Notes

The fixture should be copied later into sandbox, never mutated directly.

The fixture should contain enough structure to test:

- route inventory,
- backend config detection,
- package inventory,
- build validation,
- source diff generation.

### Acceptance Criteria

- Fixture exists or generation script exists.
- Fixture has Angular 18.x dependencies.
- Fixture has route and backend config signals.
- Fixture build command is documented.
- Team can use it as the reference app for later sprints.

### Definition of Done

- Fixture README added.
- Team can run the fixture locally.
- Fixture usage is documented in Sprint 0 demo guide.

### Risks and Edge Cases

- Fixture may be too simple to validate strict parity concepts.
- Node version mismatch may block local usage.
- Dependency installation may fail behind a corporate proxy.

---

## AMF-S0-17 — Local Developer Scripts and Quality Checks

**Type:** DevOps / Infrastructure  
**Priority:** Must  
**Suggested labels:** `devex`, `scripts`, `tests`, `quality`  
**Dependencies:** AMF-S0-02, AMF-S0-06

### User Story / Technical Story

As a development team, we need repeatable commands to run, test, lint, and validate the skeleton.

### Context / Why This Issue Exists

The team needs a stable local workflow before implementing migration complexity. Developer experience problems should be solved early, not during real migration implementation.

### Scope

Add scripts for:

```text
start backend
start frontend
run backend tests
run frontend tests
run backend lint/format
run frontend lint/typecheck
run alembic migration
run mock workflow demo
```

### Out of Scope

- CI/CD pipeline.
- Docker setup unless the team explicitly chooses it.
- Production deployment scripts.

### Implementation Notes

Use a `Makefile`, `justfile`, npm scripts, PowerShell scripts, or simple documented commands.

Because the team may use Windows, document PowerShell equivalents where useful.

### Acceptance Criteria

- A new developer can run backend and frontend using documented commands.
- Tests can be executed with one command per side.
- Mock workflow demo command is documented.
- Type checking and formatting commands are documented.

### Definition of Done

- Developer setup guide added.
- Scripts tested locally.
- README includes minimal troubleshooting notes.

### Risks and Edge Cases

- Different developer OS environments.
- Corporate proxy.
- Node/npm path issues.
- Python virtual environment confusion.

---

## AMF-S0-18 — Sprint 0 Architecture Boundary Document

**Type:** DevOps / Infrastructure  
**Priority:** Should  
**Suggested labels:** `architecture`, `security`, `decision-record`, `sprint-0`  
**Dependencies:** AMF-S0-01

### User Story / Technical Story

As the team, we need a short architecture boundary document so everyone respects the product rules before implementing real migration logic.

### Context / Why This Issue Exists

The factory has strict principles: backend-owned state, sandbox-only mutation, backend command authority, agent boundaries, approval gates, and artifact-first evidence. These rules must be written down early to prevent unsafe shortcuts.

### Scope

Create an ADR:

```text
docs/adr/0001-platform-boundaries.md
```

Document these rules:

```text
Frontend does not infer workflow state.
Agents do not execute commands.
LLM does not mutate files.
Backend validates and executes commands.
All mutation happens in sandbox.
Artifacts are the evidence source.
SSE carries backend state events.
MCP is disabled or read-only context only.
Approval gates are backend-controlled.
```

### Out of Scope

- Full security review.
- Threat model.
- Production governance process.

### Implementation Notes

Keep the ADR short and easy to reference during code reviews.

### Acceptance Criteria

- ADR exists.
- Forbidden shortcuts are clearly listed.
- Root README links to the ADR.
- Team can use the ADR as a code review reference.

### Definition of Done

- ADR committed.
- Root README links to it.
- Sprint 0 demo references the platform boundaries.

### Risks and Edge Cases

- Without this document, developers may accidentally put workflow logic in the UI or execution logic in agents.
- The team may start treating LLM output as trusted execution logic.

---

# 9. Final Sprint 0 Issue Order

Use this dependency order:

1. AMF-S0-01 — Repository and Workspace Skeleton
2. AMF-S0-02 — Backend FastAPI Skeleton
3. AMF-S0-03 — Backend Configuration and Environment Setup
4. AMF-S0-04 — SQLAlchemy, Alembic, and SQLite Bootstrap
5. AMF-S0-05 — Shared API Contracts and OpenAPI Foundation
6. AMF-S0-06 — Frontend Next.js Control Tower Skeleton
7. AMF-S0-07 — Typed Frontend API Client Foundation
8. AMF-S0-08 — Server-Sent Events Backend and Frontend Skeleton
9. AMF-S0-09 — LangGraph Mock Orchestrator Skeleton
10. AMF-S0-10 — Common Agent Contract and Mock Agents
11. AMF-S0-11 — Local Filesystem Artifact Store Skeleton
12. AMF-S0-12 — Python Sandbox Execution Worker Shell
13. AMF-S0-13 — Runtime Preflight Checker
14. AMF-S0-14 — Azure OpenAI LLM Gateway Mock
15. AMF-S0-15 — Custom Log Viewer, Diff Viewer, and Markdown Report Viewer Skeleton
16. AMF-S0-16 — Demo Angular 18 Fixture Project
17. AMF-S0-17 — Local Developer Scripts and Quality Checks
18. AMF-S0-18 — Sprint 0 Architecture Boundary Document

---

# 10. Sprint 0 Definition of Done

Sprint 0 is done when:

- Backend runs locally with FastAPI and Uvicorn.
- Frontend runs locally with Next.js, React, and TypeScript.
- Backend configuration is centralized and documented.
- SQLite database bootstrap works with SQLAlchemy and Alembic.
- Core Pydantic v2 contracts and status enums exist.
- OpenAPI exposes the mock migration state contract.
- Frontend renders backend-shaped migration state.
- SSE mock stream updates the Control Tower.
- LangGraph mock orchestrator can simulate the migration workflow.
- Mock agents use a common input/output contract.
- Artifact folder structure is created locally.
- Mock artifacts can be listed and opened.
- Python sandbox execution worker interface exists.
- Runtime preflight checker reports Python, Node.js, npm, npx, and Git availability.
- Azure OpenAI LLM Gateway mock exists and does not expose secrets.
- Log viewer, unified diff viewer, and Markdown report viewer skeletons exist.
- Angular 18 fixture project exists or is documented.
- Local developer scripts are documented.
- Architecture boundary ADR exists.
- No real migration command is executed yet.
- No original source project mutation exists.
- No frontend-owned workflow state machine exists.
