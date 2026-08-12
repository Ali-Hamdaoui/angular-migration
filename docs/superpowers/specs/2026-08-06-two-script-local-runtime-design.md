# Two-Script Local Runtime Design

**Date:** 2026-08-06  
**Status:** Approved by the user

## Goal

Make the normal local Angular Migration Factory workflow require only two operator-facing scripts:

1. `scripts/dev-frontend.ps1` for the frontend.
2. `scripts/dev-backend.ps1` for the FastAPI API and the durable Transformer/command worker.

The API and Transformer must remain separate operating-system processes. The change consolidates their startup and shutdown control without moving command execution into the FastAPI application.

## Current context

The repository currently documents `dev-backend.ps1` as an API-only launcher. The Transformer is started manually with `python -m app.orchestration.transformer_worker`, creating a three-terminal workflow together with the frontend. The specialized `run-fresh-backend.ps1` already starts both backend processes, but it is an end-to-end proof runner: it resets fresh external state, validates runtime routes, uses proof-specific parameters, and is not an appropriate everyday development launcher.

The existing backend runtime has two independent responsibilities:

- Uvicorn serves the FastAPI application and its planning worker.
- `app.orchestration.transformer_worker` claims durable transformation continuations, supervises authorized command executions, reconciles leases, and resumes waiting workflow state.

The repository architecture explicitly keeps the Transformer outside the API process. The two-script design therefore changes only the operator-facing launcher boundary.

## Approaches considered

### 1. One PowerShell backend supervisor launching two child processes — selected

`dev-backend.ps1` resolves the repository and backend paths, selects the backend virtual-environment Python, prepares the target root and environment, applies Alembic migrations, starts Uvicorn and the Transformer worker, monitors both processes, and cleans up both process trees on exit.

This preserves the existing runtime isolation, keeps the API from spawning migration commands, gives the worker the exact same configuration and Python environment as the API, and keeps the normal operator workflow to two scripts.

### 2. Start the Transformer from FastAPI lifespan — rejected

This would reduce the visible process count, but it would violate the documented boundary that the API never spawns migration processes. Uvicorn reload would also make worker ownership and duplicate-worker behavior ambiguous.

### 3. Run the worker as an in-process PowerShell job — rejected

This would still present one launcher, but it would hide worker output and make process ownership, restart reconciliation, and cleanup less explicit. It would also make it harder to detect a worker failure while the API remains healthy.

## Design

### Launcher inputs and environment

`scripts/dev-backend.ps1` will accept optional `-TargetRoot` and `-Port` parameters. The default target root will be:

```text
C:\Users\hamdaoui.ali\Downloads\MSA-COMMON-STG1
```

The launcher will create the target directory when needed and set `ALLOWED_TARGET_ROOTS` before either backend child process starts. The value will be restored in the parent PowerShell process when the launcher exits where a prior value existed.

The script will use `backend\.venv\Scripts\python.exe` when present and fail with a clear setup message when the backend virtual environment is missing. The same executable will run Alembic, Uvicorn, and the Transformer worker; no shell activation is required.

### Startup sequence

1. Resolve the repository root from `$PSScriptRoot` and change to `backend`.
2. Validate the backend Python executable and create the configured target root.
3. Run `python -m alembic -c alembic.ini upgrade heads`.
4. Start `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port <Port>`.
5. Start `python -m app.orchestration.transformer_worker` as a separate child process.
6. Print the API URL, target root, process IDs, and worker/API log locations.
7. Monitor both children until the user stops the launcher or either child exits unexpectedly.

The worker starts after migrations complete so it never races database schema setup. Both children inherit the configured environment and backend working directory.

### Monitoring and shutdown

The launcher will use explicit process objects and a small process-tree cleanup helper. If Uvicorn or the Transformer exits unexpectedly, the launcher will stop the remaining backend process tree and fail with the exited process and exit code. On Ctrl+C or another terminating path, the `finally` block will stop both child trees and restore the prior target-root environment variable.

Uvicorn reload may create a server child beneath its reloader process; cleanup must therefore walk descendants rather than stopping only the direct launcher PID.

### Frontend

`scripts/dev-frontend.ps1` remains the two-line launcher that changes to `frontend` and runs `npm run dev`. Its behavior and frontend runtime are unchanged.

### Documentation

Update the root README, `docs/developer-setup.md`, `scripts/README.md`, and the backend README so the normal workflow shows exactly two commands and explains that the backend script supervises both API and Transformer processes. Keep the specialized `run-fresh-backend.ps1` documentation and proof behavior unchanged.

## Error handling and safety

- Stop before starting children if the backend directory, Python executable, or target-root setup is invalid.
- Stop before starting children if Alembic fails.
- Do not enable shell execution or change the production command-execution boundary.
- Do not delete the target root, database, source root, or migration workspaces from the development launcher.
- Do not expose secrets in launcher output; print paths, ports, and process IDs only.
- If a child exits, report its exit code and clean up the sibling process.

## Verification

Focused verification will cover:

- PowerShell parser validation for the changed launcher.
- A launcher contract/integration check that starts the backend script with a temporary target root, observes the API health endpoint, confirms a Transformer worker process is running, and cleans up all descendants.
- Existing backend tests for the worker and affected runtime contracts.
- Documentation and Git diff checks.

The verification must distinguish the API process, the Uvicorn reload process tree, and the Transformer worker; an API-only startup is not sufficient evidence for the requested two-script workflow.

## Out of scope

- Merging the Transformer implementation into FastAPI.
- Changing workflow state, command authorization, worker lease behavior, or database schema.
- Removing or rewriting `run-fresh-backend.ps1`.
- Changing frontend code or its development server behavior.
