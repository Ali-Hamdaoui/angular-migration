# Two-Command Development Runtime Design

## Objective

Start the complete local solution from two PowerShell commands: one frontend
launcher and one backend launcher. The backend launcher must own the local
startup experience for both FastAPI and the durable Transformer worker without
merging those runtime responsibilities into one Python process.

## Architecture

`scripts/dev-frontend.ps1` remains the Next.js launcher.
`scripts/dev-backend.ps1` becomes a small Windows development supervisor. It
sets the allowed target root, applies database migrations, and starts two child
processes with the repository virtual environment:

1. Uvicorn/FastAPI with reload enabled.
2. `app.orchestration.transformer_worker` without reload.

The API continues to queue durable work. The Transformer worker continues to
claim continuations and commands independently. This preserves the production
boundary that prevents the API request process from executing migration
subprocesses.

## Launcher interface

The backend command is:

```powershell
.\scripts\dev-backend.ps1 `
  -TargetRoot "C:\Users\hamdaoui.ali\Downloads\MSA-COMMON-STG1"
```

`TargetRoot` defaults to the current user's Downloads directory with the
`MSA-COMMON-STG1` suffix. The launcher creates the directory when absent,
resolves it to an absolute path, and exports it as `ALLOWED_TARGET_ROOTS` before
starting either child process. `Port` defaults to `8000`.

The launcher fails before startup when `backend/.venv/Scripts/python.exe` is
missing or database migration fails.

## Supervision and shutdown

Both children share the current console. The supervisor monitors them once per
second. If either child exits, the launcher reports its exit code, stops the
other runtime tree, and exits unsuccessfully.

On normal interruption or `Ctrl+C`, cleanup targets only descendants of the
two process IDs created by the launcher. This includes Uvicorn's reload child
and any worker-owned migration subprocess. Unrelated Python and Node processes
must not be selected by name or port.

## Testing

Focused Pester tests will dot-source the launcher and verify:

- the target root is created, resolved, and exported;
- both child commands use the repository virtual-environment Python;
- API and worker arguments remain separate;
- descendant discovery is rooted in the launched process IDs;
- startup documentation exposes exactly the two developer commands.

Existing backend tests continue to prove that API routes queue work without
dispatching migration commands and that the worker claims durable executions.

