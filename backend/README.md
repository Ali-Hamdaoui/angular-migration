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
  core/                application metadata and future configuration
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

### Run locally

From this directory, install the declared dependencies, then run:

```powershell
python -m uvicorn app.main:app --reload
```

Initial endpoints: `GET /health`, `GET /version`, and
`GET /migrations/mock-state`. Interactive OpenAPI documentation is at `/docs`.
Run tests with `python -m pytest`.

## Boundaries

Frontend code and fixture applications do not belong here. Agents may propose
actions only through backend contracts; they must not execute commands directly.
The backend will validate and execute approved work only within a sandbox.
