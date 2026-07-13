# Developer Setup and Quality Gates

This guide is the Sprint 0 entry point for local development on Windows PowerShell. The same commands work in PowerShell 7 (`pwsh`) on other operating systems when Python, Node.js, npm, Git, and ripgrep are available.

## Prerequisites

- Python 3.12 or newer available as `python`.
- Node.js and npm compatible with the frontend workspace.
- Git.
- `rg` / ripgrep for architecture checks.
- Optional: a Python virtual environment under `backend/.venv`.

## Install Dependencies

Backend:

```powershell
cd backend
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install pytest httpx
```

Frontend:

```powershell
cd frontend
npm install
```

Angular 18 fixture, only when validating the fixture build:

```powershell
cd demo-apps/angular-18-basic
npm ci
npm run build
```

## Start Locally

Backend:

```powershell
.\scripts\dev-backend.ps1
```

Frontend:

```powershell
.\scripts\dev-frontend.ps1
```

## Quality Gates

Aggregate Sprint 0 quality command:

```powershell
.\scripts\quality.ps1
```

The aggregate command fails fast and runs contract export before frontend checks:

1. Export backend OpenAPI to `shared/openapi.json`.
2. Compile backend Python modules.
3. Run backend pytest.
4. Run frontend typecheck, tests, and production build.
5. Run artifact/workspace integrity tests.
6. Run Angular 18 fixture contract tests.
7. Run architecture shortcut checks.

Focused commands:

```powershell
.\scripts\test-backend.ps1
.\scripts\test-frontend.ps1
.\scripts\backend-static-check.ps1
.\scripts\artifact-integrity-test.ps1
.\scripts\fixture-contract-test.ps1
.\scripts\architecture-check.ps1
```

## Contracts

```powershell
.\scripts\generate-openapi-client.ps1
```

This exports `shared/openapi.json`. Keep `frontend/src/types/generated/api.ts` synchronized with backend contracts before frontend type checking.

## Database

Apply migrations:

```powershell
.\scripts\migrate-db.ps1
```

Reset the local Sprint 0 SQLite database:

```powershell
.\scripts\reset-db.ps1 -ConfirmReset
```

The reset script refuses to delete anything unless `-ConfirmReset` is supplied and only targets `backend/.migration-factory/migration-factory.db`.

## Mock Workflow and SSE Replay

Start the backend first, then run:

```powershell
.\scripts\mock-workflow.ps1
.\scripts\sse-replay-test.ps1
```

`mock-workflow.ps1` validates mock setup and creates a checksum-bound mock run. `sse-replay-test.ps1` requests replay after event 3 and fails if event 4 is not returned.

## Corporate Proxy and Certificates

Use approved enterprise proxy and certificate configuration. Do not disable TLS validation globally. Recommended safe options:

- Configure npm with the company CA: `npm config set cafile <approved-ca.pem>`.
- Configure Python/pip with the company CA through approved environment variables or pip configuration.
- Keep proxy settings scoped to the current shell or approved user config.
- Do not commit proxy credentials, tokens, private registry passwords, or certificate files.
