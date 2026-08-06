# Scripts

PowerShell scripts in this directory provide repeatable Sprint 0 developer workflows.

## Core Commands

- `dev-backend.ps1` applies migrations and supervises the Uvicorn API plus the
  separate durable Transformer worker. It accepts `-TargetRoot <path>` and
  `-Port <number>`.
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

Start the complete local solution in two terminals:

```powershell
.\scripts\dev-backend.ps1 `
  -TargetRoot "C:\Users\hamdaoui.ali\Downloads\MSA-COMMON-STG1"
```

```powershell
.\scripts\dev-frontend.ps1
```

The backend launcher keeps the API and Transformer worker in separate Python
processes while giving developers one backend command. If either child exits,
the launcher stops the other; `Ctrl+C` stops both launched process trees.

The scripts intentionally do not install tools automatically and do not disable TLS or certificate validation.
