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
| `APPLICATION_DATA_ROOT` | `%LOCALAPPDATA%\\AngularMigrationControlTower` | Platform operational state, outside the repository. |
| `DATABASE_URL` | `<application-data-root>/control-tower.db` | Global MVP SQLite state. |
| Run paths | registered output root | Never configure repository-relative run artifacts, sandboxes, or logs. |
| `ALLOWED_SOURCE_ROOTS` | `external source directories` | Comma-delimited normalized source roots. Windows example: `C:\projects\approved-sources`; POSIX example: `/opt/approved-sources`. |
| `ALLOWED_TARGET_ROOTS` | `.migration-factory` | Comma-delimited normalized target roots. Windows example: `C:\tmp\migration-output`; POSIX example: `/tmp/migration-output`. |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3000` | Comma-delimited allowlist. |
| `COMMAND_TIMEOUT_SECONDS` | `300` | Must be positive. |
| `COMMAND_MAX_OUTPUT_BYTES` | `1000000` | Captured command output cap. |
| `WORKER_LEASE_SECONDS` | `120` | Mock worker lease duration. |
| `SSE_HEARTBEAT_SECONDS` | `15` | Event-stream heartbeat interval. |
| `SSE_REPLAY_RETENTION_EVENTS` | `1000` | Event replay retention count. |
| `LOG_CHUNK_BYTES` | `64000` | Log chunk size for future viewers. |
| `SQLITE_WAL_ENABLED` | `true` | SQLite single-host MVP WAL toggle. |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | SQLite busy timeout. |
| `LLM_ENABLED` | `false` | When true, all Azure settings are required. |
| `AZURE_OPENAI_*` | unset | Server-side only; never expose or log the API key. |
| `LLM_*` budget and price settings | `0` | Snapshot into runs before real LLM use. |

The server applies the configured CORS allowlist at startup. Azure settings are
validated only when LLM access is enabled. `AZURE_OPENAI_API_KEY` is held as a
Pydantic secret and no configuration endpoint exists.

## Persistence bootstrap

SQLAlchemy owns the backend persistence boundary; API routers and agents do not
access database sessions directly. The initial Alembic revision creates the
Sprint 0 state tables: `migration_runs`, `migration_stages`, `stage_steps`,
`agent_executions`, `workflow_events`, `approval_events`,
`approval_policy_events`, `artifact_metadata`, `command_executions`,
`worker_leases`, `repair_attempts`, `llm_usage_records`, and
`run_assurance_statuses`. S2-F06 adds `migration_plans`,
`stage_execution_plans`, `build_system_decisions`, and
`active_plan_versions` for immutable, checksum-bound plan evidence.

The schema stores run `state_version` for optimistic concurrency, ordered
per-run workflow event `sequence` values, scoped command `idempotency_key`
constraints, stage/attempt IDs, lease owner/expiry fields, artifact checksums
and schema versions, and LLM usage price/cost snapshots. Artifact contents are
not stored in SQLite; only metadata is persisted there.

The configured `DATABASE_URL` is used by both FastAPI startup connectivity and
Alembic. The default is a local SQLite file. File-backed SQLite connections
apply `SQLITE_BUSY_TIMEOUT_MS` and, when `SQLITE_WAL_ENABLED=true`, WAL mode.
From `backend/`, create or upgrade the schema with:

```powershell
python -m alembic -c alembic.ini upgrade head
```

To inspect the applied revision:

```powershell
python -m alembic -c alembic.ini current
```

To reset a local development database, stop the backend, remove the configured
SQLite file under `.migration-factory/`, then run the upgrade command again. Do
not use `Base.metadata.create_all()` in runtime application code; Alembic is the
schema authority. It is used only in repository unit tests to isolate adapters
from migration execution.

## Workspace, snapshot, and delivery layout

AMF-S0-19 separates immutable source evidence, mutable migration work, run
artifacts, and final publication:

```text
{resolved-output-root}/.migration-factory/runs/{runId}/source-snapshot/
{resolved-output-root}/.migration-factory/runs/{runId}/baseline-sandbox/
{resolved-output-root}/.migration-factory/runs/{runId}/artifacts/
{target}/migrated-app/
```

`SourceManifestBuilder` records fixture file paths, sizes, and SHA-256 checksums.
`SnapshotService` copies the source into an immutable snapshot and writes
`source-manifest.json`. `WorkspaceService` copies the snapshot into the internal
run workspace, never into `migrated-app`. `SourceIntegrityVerifier` compares the
current source to the original manifest before delivery. `DeliveryService`
publishes only non-failed/non-cancelled runs by copying workspace output to a
temporary directory and renaming it to `migrated-app`. Existing output requires
an explicit conflict policy; the default policy refuses to overwrite it.

## Workspace, snapshot, and delivery layout

AMF-S0-19 separates immutable source evidence, mutable migration work, run
artifacts, and final publication:

```text
{resolved-output-root}/.migration-factory/runs/{runId}/source-snapshot/
{resolved-output-root}/.migration-factory/runs/{runId}/baseline-sandbox/
{resolved-output-root}/.migration-factory/runs/{runId}/artifacts/
{target}/migrated-app/
```

`SourceManifestBuilder` records fixture file paths, sizes, and SHA-256 checksums.
`SnapshotService` copies the source into an immutable snapshot and writes
`source-manifest.json`. `WorkspaceService` copies the snapshot into the internal
run workspace, never into `migrated-app`. `SourceIntegrityVerifier` compares the
current source to the original manifest before delivery. `DeliveryService`
publishes only non-failed/non-cancelled runs by copying workspace output to a
temporary directory and renaming it to `migrated-app`. Existing output requires
an explicit conflict policy; the default policy refuses to overwrite it.

## Artifact store

The local filesystem artifact store writes append-only evidence beneath
`ARTIFACT_ROOT` using the Sprint 0 run layout:

```text
{resolved-output-root}/.migration-factory/runs/{runId}/artifacts/
  00_job_setup/
  01_baseline/
  02_analysis/
  03_planning/
  04_workflow_state/
  05_sandbox_transform/
  06_validation/
  07_repair/
  08_final/
  global/
  stages/{stageId}/
  repair_attempts/{stageId}/{attemptId}/
  final_assurance/
  delivery/
  final_report/
```

Artifacts are written with temporary files plus atomic rename where supported.
An existing artifact path is never overwritten; a second write receives a new
artifact ID and versioned relative path such as `report__v2.md`. Each artifact
has a sibling `*.meta.json` envelope with schema version, artifact ID,
run/stage/attempt, producer, artifact type, content type, input hashes, policy
version, content hash, relative path, and timestamp. Artifact content remains on
the filesystem, outside SQLite and workflow events.

The backend rejects path traversal and symlink escapes. The public API surface
for this store is:

```http
GET /migrations/{runId}/artifacts
GET /migrations/{runId}/artifacts/{artifactPath}
GET /artifacts/{artifactId}
```

The first endpoint lists stored artifacts. The second keeps path-based access
for run-scoped compatibility, and the third opens immutable artifacts by ID.

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
that is missing or outside a registered mutable workspace alias. It invokes subprocesses with
`shell=False`, captures stdout/stderr/exit code/timing, and writes a command-log
artifact to `04_workflow_state/command_logs/{commandId}.json`. Those logs are
opened through the artifact API like any other run artifact.

## Run locally

From this directory, install dependencies and migrate the configured SQLite
database:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Run the API and the durable Transformer/command worker in separate terminals.
The API only queues authorized commands; it never spawns migration processes:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
.\.venv\Scripts\python.exe -m app.orchestration.transformer_worker
```

The Transformer worker owns continuation claims, command leases, restart
reconciliation, cancellation polling, and Windows process-tree supervision.
Run more than one worker only against the same single-host SQLite database and
workspace roots.

Core route shells:

- `GET /health`
- `GET /version`
- `POST /migrations/preflight`
- `POST /migrations/mock`
- `GET /migrations/mock-state`
- `GET /migrations/{run_id}/state`
- `GET /migrations/{run_id}/events` (SSE)
- `POST /migrations/{run_id}/approvals`
- `PUT /migrations/{run_id}/approval-policy`
- `POST /migrations/{run_id}/cancel`
- `POST /migrations/{run_id}/resume`
- `GET /migrations/{run_id}/artifacts`
- `GET /migrations/{run_id}/artifacts/{artifact_path}`
- `GET /artifacts/{artifact_id}`
- `POST /api/v1/runs/{run_id}/plans`
- `GET /api/v1/runs/{run_id}/plan`
- `GET /api/v1/runs/{run_id}/stages/{stage_id}/plan`
- `POST /assistant/messages`

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
workflow graph shape with optimized mock nodes:

```text
create_run_mock -> snapshot_topology_mock -> source_runtime_resolution_mock
  -> parallel_discovery_fanout_mock -> parallel_discovery_join_mock
  -> baseline_qualification_mock -> analysis_feasibility_mock
  -> wait_analysis_approval_mock -> planning_mock -> wait_plan_approval_mock
  -> stage_loop_mock -> final_assurance_mock -> delivery_gate_mock
  -> report_mock -> END
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
assert all(s["status"].value == "PASSED" for s in state["stages"])
```

Stage order is always Angular 18-to-19, 19-to-20, 20-to-21 as defined by the
initial state's `stages` list.
## Common component and agent contracts

Deterministic components use `ComponentInputEnvelope`,
`ComponentOutputEnvelope`, and `DeterministicComponentContract`. Component
contracts are frozen Pydantic v2 models with `extra="forbid"`; they reject LLM
access and direct command execution. Component calls are exposed in the mock read
model as `ComponentExecutionDto` entries under `component_executions`.

All agents - mock or real - inherit `BaseMockAgent` and implement `execute`.
They receive an `AgentInputEnvelope` and return an `AgentOutputEnvelope`, both
frozen Pydantic v2 models with `extra="forbid"`.

**Input envelope fields:** `run_id`, `stage_id`, `agent_kind`, `workspace`,
`client_constraints`, `current_workflow_state`, `allowed_actions`,
`artifact_locations`, `approved_plan_checksum`, and `untrusted_context`.

**Output envelope fields:** `agent_name`, `agent_kind`, `run_id`, `stage_id`,
`status`, `summary`, `artifacts_created`, `risks`, `action_proposals`,
`patch_proposals`, `requires_human_action`, authorization flags, and
`next_recommended_state`.

`ActionProposalDto` references backend-registered action IDs for executable
requests. `PatchProposalDto` identifies files, rationale, risk, expected
behavior impact, and validation requests. AI output cannot authorize execution,
approval, or patch application.

Eight mock agents are registered in `app/agents/registry.py`:

| Agent | Mock behavior | Status |
| --- | --- | --- |
| AI Assistant Agent | Explains state; no artifacts | COMPLETED |
| Eligibility and Constraint Agent | Accepts Angular 18.x; creates eligibility artifacts | COMPLETED |
| Analysis Agent | Inventories workspace; reports dependency risk | COMPLETED |
| Planning Agent | Generates upgrade ladder and toolchain profiles | COMPLETED |
| Transformation Agent | Mock upgrade; creates sandbox transform artifacts and proposals | COMPLETED |
| Build / Validation Agent | Mock build pass; reports manual browser-smoke risk | COMPLETED |
| Repair Agent | No errors detected; repair skipped with example patch proposal | SKIPPED |
| Report Agent | Generates final evidence report artifacts | COMPLETED |

Agents never call shell commands, mutate files, approve gates, or bypass backend
authority. They return structured outputs only; the orchestrator records each AI
call as an `AgentExecutionDto` and emits SSE events. Deterministic component
activity is recorded separately and must be labeled separately in the UI.

## Boundaries

Frontend code and fixture applications do not belong here. Agents may propose
actions only through backend contracts; they must not execute commands directly.
The backend will validate and execute approved work only within a sandbox.
