# Backend

This workspace is the AI Frontend Migration Factory's execution authority. It
owns API state, persistence, orchestration, artifacts, approvals, sandbox
policy, command execution, and the LLM Gateway as those capabilities are added.

## Module structure

The shell keeps routers thin and delegates response construction to services.
The mock migration endpoint is deliberately read-only and static; it is not
orchestration or persistence.

```text
app/
  api/                 HTTP adapters only - routers depend on services, not repositories
  core/                application metadata and configuration
  domain/              canonical Pydantic v2 contracts and state vocabulary
  repositories/        persistence boundary (SQLAlchemy/Alembic)
  state/               state transition service with optimistic concurrency
  events/              ordered event persistence and SSE emission
  orchestration/       LangGraph workflow boundary
  components/          deterministic workflow components (non-LLM)
  agents/              AI-assisted agents only
  preflight/           preflight and runtime capability checks
  snapshots/           immutable source snapshot service
  runtime_profiles/    runtime-profile abstraction and registry
  workspaces/          internal run workspace management
  checkpoints/         checkpoint service for resume
  delivery/            atomic delivery publication
  artifact_store/      immutable, checksum-bound artifact store
  command_execution/   structured command worker and supervisor
  llm_gateway/         Azure OpenAI LLM Gateway abstraction
  observability/       run metrics and diagnostics
  policies/            command allowlists, auto-approval, sensitivity, topology
  services/            shared backend service helpers
  sandbox/             sandbox-policy boundary (legacy, merging into workspaces/)
```

Deterministic components (`components/`) and AI-assisted agents (`agents/`)
are clearly separated. Agents must not import command-worker implementations
or secret-bearing configuration. API routers must depend on application
services, not repositories or workers directly. LangGraph nodes must call
state, event, artifact, and execution services rather than implement those
concerns internally.

## Configuration

`app.core.config.Settings` is the single backend configuration source. It reads
process environment variables first, then `backend/.env` when present. Copy
[.env.example](.env.example) to `.env` only for local overrides; `.env` is
ignored by Git.

| Variable | Local default | Notes |
| --- | --- | --- |
| `APP_ENV` | `development` | Allowed values: `development`, `test`, `production`. |
| `DATABASE_URL` | `sqlite:///./.migration-factory/migration-factory.db` | Used by AMF-S0-04. |
| `ARTIFACT_ROOT` | `.migration-factory/runs` | Used by AMF-S0-11. |
| `SANDBOX_ROOT` | `.migration-factory/sandboxes` | Used by later sandbox work. |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3000` | Comma-delimited allowlist. |
| `COMMAND_TIMEOUT_SECONDS` | `300` | Must be a positive integer. |
| `LLM_ENABLED` | `false` | When true, all Azure settings are required. |
| `AZURE_OPENAI_*` | unset | Server-side only; never expose or log the API key. |

The server applies the configured CORS allowlist at startup. Azure settings are
validated only when LLM access is enabled. `AZURE_OPENAI_API_KEY` is held as a
Pydantic secret and no configuration endpoint exists.

## Persistence bootstrap

SQLAlchemy owns the backend persistence boundary; API routers and agents do not
access database sessions directly. The initial Alembic revision creates these
placeholder tables: `migration_runs`, `migration_stages`, `agent_executions`,
`artifact_metadata`, `approval_events`, and `workflow_events`. Their lifecycle
values remain free-form placeholders until AMF-S0-05 defines the shared enums.

The configured `DATABASE_URL` is used by both FastAPI startup connectivity and
Alembic. The default is a local SQLite file. From `backend/`, create or upgrade
the schema with:

```powershell
python -m alembic -c alembic.ini upgrade head
```

To inspect the applied revision:

```powershell
python -m alembic -c alembic.ini current
```

Do not use `Base.metadata.create_all()` in runtime application code; Alembic is
the schema authority. It is used only in the repository unit test to isolate
that adapter from migration execution.

## Artifact store

The local filesystem artifact store writes beneath `ARTIFACT_ROOT` using the
Sprint 0 run layout:

```text
{ARTIFACT_ROOT}/{runId}/
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

Artifacts are written as text files with a sibling `*.meta.json` sidecar that
stores the backend-owned metadata, including checksum, timestamps, and the
artifact type. The backend rejects paths that would escape the run folder.

The public API surface for this store is:

```http
GET /migrations/{runId}/artifacts
GET /migrations/{runId}/artifacts/{artifactPath}
```

The first endpoint lists stored artifacts; the second opens a single artifact
and returns the backend-owned metadata plus file content.

## Command execution worker

`app.command_execution` is the backend command-authority boundary. Agents and
LLM-assisted code never run shell commands directly; they submit a structured
`CommandRequestDto`, and the worker validates it before execution.

Sprint 0 allows only preflight version commands:

```text
python --version
node --version
npm --version
git --version
```

The worker rejects any command outside that allowlist and any working directory
that is missing or outside `SANDBOX_ROOT`. It invokes subprocesses with
`shell=False`, captures stdout/stderr/exit code/timing, and writes a command-log
artifact to `04_workflow_state/command_logs/{commandId}.json`. Those logs are
opened through the artifact API like any other run artifact.

## Run locally

From this directory, install the declared dependencies, then run:

```powershell
python -m uvicorn app.main:app --reload
```

Initial endpoints: `GET /health`, `GET /version`,
`GET /migrations/mock-state`, and `GET /migrations/{run_id}/events` (SSE).
Interactive OpenAPI documentation is at `/docs`. Run tests with
`python -m pytest`.

## Server-Sent Events

The `GET /migrations/{run_id}/events` endpoint streams mock workflow events as
`text/event-stream`. Each SSE block carries a typed `event:` line
(`run_state_changed`, `stage_state_changed`, `agent_state_changed`,
`validation_gate_changed`, `artifact_created`, `approval_required`,
`workflow_completed`) and a `data:` line with a JSON `MigrationEventDto`. The
mock event service emits a deterministic sequence covering every event type;
the inter-event delay is controlled by `MOCK_EVENT_DELAY_SECONDS` (default 1s,
patched to 0 in tests). No real orchestration drives this stream in Sprint 0.

## Mock orchestrator

The LangGraph mock orchestrator (`app/orchestration/`) defines the Sprint 0
workflow graph shape with 11 mock nodes:

```text
create_run_mock → eligibility_mock → baseline_mock → analysis_mock
  → wait_analysis_approval_mock
      ↓ (conditional: approved → continue, rejected → END, no decision → pause)
  planning_mock → wait_plan_approval_mock
      ↓ (conditional: approved → continue, rejected → END, no decision → pause)
  stage_18_to_19_mock → stage_19_to_20_mock → stage_20_to_21_mock
  → report_mock → END
```

Nodes mutate `OrchestratorState` only and emit `MigrationEventDto` entries
into `state["emitted_events"]`; they never write to the frontend or bypass
state services. The `workflow_service` module wraps graph execution and
exposes `run_mock_workflow`, `run_mock_workflow_step` (resume after
approval), `get_emitted_events`, and `get_run_dto`.

### Demo flow

```python
from app.services.workflow_service import run_mock_workflow
from app.domain.contracts import ApprovalDecision

# Pause at first approval gate
state = run_mock_workflow()
assert state["paused"] is True

# Run end-to-end with auto-approvals
state = run_mock_workflow(approvals={
    "analysis": ApprovalDecision.APPROVED,
    "plan": ApprovalDecision.APPROVED,
})
assert state["run_status"].value == "COMPLETED"
assert all(s["status"].value == "STAGE_COMMITTED" for s in state["stages"])
```

Stage order is always Angular 18→19, 19→20, 20→21 as defined by the initial
state's `stages` list.

## Common agent contract

All agents — mock or real — inherit `BaseMockAgent` and implement `execute`.
They receive an `AgentInputEnvelope` and return an `AgentOutputEnvelope`,
both defined as frozen Pydantic v2 models with `extra="forbid"`.

**Input envelope fields:** `run_id`, `stage_id`, `workspace`,
`client_constraints`, `current_workflow_state`, `allowed_actions`,
`artifact_locations`, `approved_plan_checksum`.

**Output envelope fields:** `agent_name`, `run_id`, `stage_id`, `status`,
`summary`, `artifacts_created`, `risks`, `requires_human_action`,
`next_recommended_state`.

Eight mock agents are registered in `app/agents/registry.py`:

| Agent | Mock behavior | Status |
| --- | --- | --- |
| AI Assistant Agent | Explains state; no artifacts | COMPLETED |
| Eligibility and Constraint Agent | Accepts Angular 18.x; creates eligibility artifacts | COMPLETED |
| Analysis Agent | Inventories workspace; reports dependency risk | COMPLETED |
| Planning Agent | Generates upgrade ladder and toolchain profiles | COMPLETED |
| Transformation Agent | Mock upgrade; creates sandbox transform artifacts | COMPLETED |
| Build / Validation Agent | Mock build pass; reports manual browser-smoke risk | COMPLETED |
| Repair Agent | No errors detected; repair skipped | SKIPPED |
| Report Agent | Generates final evidence report artifacts | COMPLETED |

Agents never call shell commands, mutate files, approve gates, or bypass
backend authority. They return structured outputs only; the orchestrator
records each call as an `AgentExecutionDto` and emits SSE events.

## Boundaries

Frontend code and fixture applications do not belong here. Agents may propose
actions only through backend contracts; they must not execute commands directly.
The backend will validate and execute approved work only within a sandbox.
