# Backend

This workspace is the AI Frontend Migration Factory's execution authority. It
owns API state, persistence, orchestration, artifacts, approvals, sandbox
policy, command execution, and the LLM Gateway as those capabilities are added.

## AMF-S0-02 FastAPI skeleton

The shell keeps routers thin and delegates response construction to services.
The mock migration endpoint is deliberately read-only and static; it is not
orchestration or persistence.

```text
app/
  api/routes/          HTTP adapters only
  core/                application metadata and configuration
  domain/              Pydantic response models
  services/            backend business-service boundary
  repositories/        persistence boundary (AMF-S0-04)
  orchestration/       workflow boundary (AMF-S0-09)
  agents/              agent boundary (AMF-S0-10)
  artifact_store/      artifact boundary (AMF-S0-11)
  sandbox/             sandbox-policy boundary
  command_execution/   command authority boundary (AMF-S0-12)
  llm_gateway/         LLM access boundary (AMF-S0-14)
```

## Configuration

`app.core.config.Settings` is the single backend configuration source. It reads
process environment variables first, then `backend/.env` when present. Copy
[.env.example](.env.example) to `.env` only for local overrides; `.env` is
ignored by Git.

| Variable | Local default | Notes |
| --- | --- | --- |
| `APP_ENV` | `development` | Allowed values: `development`, `test`, `production`. |
| `DATABASE_URL` | `sqlite:///./.migration-factory/migration-factory.db` | Used by AMF-S0-04. |
| `ARTIFACT_ROOT` | `.migration-factory/artifacts` | Used by AMF-S0-11. |
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

## Boundaries

Frontend code and fixture applications do not belong here. Agents may propose
actions only through backend contracts; they must not execute commands directly.
The backend will validate and execute approved work only within a sandbox.