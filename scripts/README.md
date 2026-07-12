# Scripts

PowerShell scripts in this directory provide repeatable Sprint 0 developer workflows.

## Core Commands

- `dev-backend.ps1` starts FastAPI with Uvicorn reload.
- `dev-frontend.ps1` starts the Next.js Control Tower.
- `test-backend.ps1` runs backend pytest.
- `test-frontend.ps1` runs frontend Vitest.
- `quality.ps1` runs the aggregate Sprint 0 quality gate.
- `generate-openapi-client.ps1` exports backend OpenAPI to `shared/openapi.json` before frontend contract checks.
- `migrate-db.ps1` applies Alembic migrations.
- `reset-db.ps1 -ConfirmReset` resets only the local Sprint 0 SQLite database.
- `mock-workflow.ps1` exercises mock preflight and run creation against a running backend.
- `sse-replay-test.ps1` verifies mock SSE replay against a running backend.
- `artifact-integrity-test.ps1` runs artifact/workspace integrity tests.
- `fixture-contract-test.ps1` runs Angular 18 fixture contract tests.
- `architecture-check.ps1` scans for forbidden Sprint 0 shortcuts.

Run scripts from the repository root with PowerShell:

```powershell
.\scripts\quality.ps1
```

The scripts intentionally do not install tools automatically and do not disable TLS or certificate validation.
