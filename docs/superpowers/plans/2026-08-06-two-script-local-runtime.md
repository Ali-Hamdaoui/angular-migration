# Two-Script Local Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the normal local workflow use `dev-frontend.ps1` for the frontend and `dev-backend.ps1` as the single launcher for both the FastAPI API and the separate Transformer worker.

**Architecture:** Keep Uvicorn and `app.orchestration.transformer_worker` as separate Python child processes. The backend PowerShell script owns shared environment setup, Alembic startup, child-process monitoring, descendant cleanup, and environment restoration; it does not move command execution into FastAPI. The frontend launcher remains unchanged.

**Tech Stack:** Windows PowerShell, Pester 3.4, Python virtual environment, Alembic, Uvicorn, FastAPI Transformer worker.

## Global Constraints

- The default target root is `C:\Users\hamdaoui.ali\Downloads\MSA-COMMON-STG1`.
- `ALLOWED_TARGET_ROOTS` must be set before either backend child process starts.
- The backend must use `backend\.venv\Scripts\python.exe` for Alembic, Uvicorn, and the Transformer worker.
- The API and Transformer remain separate operating-system processes.
- The normal development launcher must not delete the target root, database, source root, or migration workspaces.
- The existing `run-fresh-backend.ps1` proof launcher is out of scope.

---

### Task 1: Add a failing backend-launcher contract test

**Files:**
- Create: `scripts/dev-backend.Tests.ps1`

**Interfaces:**
- Consumes: the source text of `scripts/dev-backend.ps1`.
- Produces: a Pester contract that fails until the backend launcher exposes the approved parameters and starts both backend processes.

- [ ] **Step 1: Write the failing test**

```powershell
$repoRoot = Split-Path -Parent $PSScriptRoot
$launcherPath = Join-Path $repoRoot "scripts\dev-backend.ps1"

Describe "dev-backend launcher" {
    BeforeAll {
        $scriptText = Get-Content -Raw -LiteralPath $launcherPath
    }

    It "accepts the requested target root and port parameters" {
        $scriptText | Should -Match '\[string\]\$TargetRoot\s*=\s*"C:\\Users\\hamdaoui\.ali\\Downloads\\MSA-COMMON-STG1"'
        $scriptText | Should -Match '\[ValidateRange\(1,\s*65535\)\]\s*\[int\]\$Port\s*=\s*8000'
    }

    It "starts the Transformer worker with the same Python executable as Uvicorn" {
        $scriptText | Should -Match '\$transformerArguments\s*=|app\.orchestration\.transformer_worker'
        $scriptText | Should -Match 'Start-Process'
        $scriptText | Should -Match '\$python'
    }

    It "configures the target root before starting child processes" {
        $environmentIndex = $scriptText.IndexOf('$env:ALLOWED_TARGET_ROOTS')
        $startProcessIndex = $scriptText.IndexOf('Start-Process')

        $environmentIndex | Should -BeGreaterThan -1
        $startProcessIndex | Should -BeGreaterThan -1
        $environmentIndex | Should -BeLessThan $startProcessIndex
    }

    It "cleans up child process trees in a finally block" {
        $scriptText | Should -Match 'function\s+Stop-ProcessTree'
        $scriptText | Should -Match 'finally\s*\{'
        $scriptText | Should -Match 'Stop-ProcessTree'
    }
}
```

- [ ] **Step 2: Run the test to verify it fails for the missing behavior**

Run:

```powershell
Invoke-Pester -Path .\scripts\dev-backend.Tests.ps1 -Output Detailed
```

Expected: FAIL because the current launcher has no `TargetRoot`/`Port` parameter block, does not start `app.orchestration.transformer_worker`, and has no process-tree cleanup function.

- [ ] **Step 3: Commit the failing test**

```powershell
git add -- scripts/dev-backend.Tests.ps1
git commit -m "test(runtime): define two-script launcher contract"
```

### Task 2: Make `dev-backend.ps1` supervise API and Transformer

**Files:**
- Modify: `scripts/dev-backend.ps1`

**Interfaces:**
- Consumes: optional `-TargetRoot` and `-Port` parameters.
- Produces: one operator command that runs Alembic, Uvicorn, and `app.orchestration.transformer_worker` with shared environment and cleanup.

- [ ] **Step 1: Add parameters and resolve the backend runtime**

Add the parameter block at the top of the script:

```powershell
[CmdletBinding()]
param(
    [string]$TargetRoot = "C:\Users\hamdaoui.ali\Downloads\MSA-COMMON-STG1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)
```

Resolve `$repoRoot`, `$backendRoot`, and `$python` from `$PSScriptRoot`; require `backend\.venv\Scripts\python.exe` before running Alembic or starting children.

- [ ] **Step 2: Add safe target-root and process-tree helpers**

Create the target directory without deleting anything, set `$env:ALLOWED_TARGET_ROOTS`, and add `Stop-ProcessTree` that recursively finds descendants with `Win32_Process`, stops descendants before their parent, and ignores already-exited processes.

Capture the prior process-scoped `ALLOWED_TARGET_ROOTS` value so `finally` can restore it or remove it when the launcher exits.

- [ ] **Step 3: Start both backend processes with the same Python executable**

After `Set-Location $backendRoot` and successful migrations, start:

```powershell
$uvicornArguments = @(
    "-m", "uvicorn", "app.main:app", "--reload",
    "--host", "127.0.0.1", "--port", $Port.ToString()
)
$transformerArguments = @("-m", "app.orchestration.transformer_worker")

$uvicornProcess = Start-Process `
    -FilePath $python `
    -ArgumentList $uvicornArguments `
    -WorkingDirectory $backendRoot `
    -NoNewWindow `
    -PassThru

$transformerProcess = Start-Process `
    -FilePath $python `
    -ArgumentList $transformerArguments `
    -WorkingDirectory $backendRoot `
    -NoNewWindow `
    -PassThru
```

Print the target root, API URL, and both process IDs. Child output remains available in the launcher terminal.

- [ ] **Step 4: Monitor exit state and clean up in all termination paths**

Refresh both process objects once per second. If either exits, throw with its exit code; the `finally` block must call `Stop-ProcessTree` for both processes and restore the environment variable. Ctrl+C must not leave a Transformer worker or Uvicorn reload child running.

- [ ] **Step 5: Run the contract test to verify the launcher contract passes**

Run:

```powershell
Invoke-Pester -Path .\scripts\dev-backend.Tests.ps1 -Output Detailed
```

Expected: all launcher contract examples PASS.

- [ ] **Step 6: Commit the launcher implementation**

```powershell
git add -- scripts/dev-backend.ps1 scripts/dev-backend.Tests.ps1
git commit -m "feat(runtime): launch transformer with backend"
```

### Task 3: Document the two-command workflow

**Files:**
- Modify: `README.md`
- Modify: `docs/developer-setup.md`
- Modify: `scripts/README.md`
- Modify: `backend/README.md`

**Interfaces:**
- Consumes: the `scripts/dev-frontend.ps1` and `scripts/dev-backend.ps1` entrypoints.
- Produces: consistent developer instructions that no longer require a separate Transformer terminal for normal local development.

- [ ] **Step 1: Update the root and setup guides**

Show exactly these two commands under local startup:

```powershell
.\scripts\dev-backend.ps1
```

```powershell
.\scripts\dev-frontend.ps1
```

Explain that the backend launcher applies migrations, sets `ALLOWED_TARGET_ROOTS`, and supervises both the API and Transformer worker.

- [ ] **Step 2: Update script and backend READMEs**

Change the script inventory so `dev-backend.ps1` is described as starting FastAPI and the Transformer/command worker. Replace the backend README’s normal-development two-terminal API/worker commands with the single repository-root backend command; retain the separate Python commands only as an explicit advanced/debugging option if needed.

- [ ] **Step 3: Check documentation consistency**

Run:

```powershell
rg -n "dev-backend|transformer_worker|separate terminals|three terminals" README.md docs\developer-setup.md scripts\README.md backend\README.md
```

Expected: normal startup references both canonical scripts, and no normal-startup section instructs the user to launch the Transformer separately.

- [ ] **Step 4: Commit the documentation update**

```powershell
git add -- README.md docs/developer-setup.md scripts/README.md backend/README.md
git commit -m "docs(runtime): document two-script startup"
```

### Task 4: Verify live startup and repository integrity

**Files:**
- Inspect: `scripts/dev-frontend.ps1`
- Inspect: `scripts/dev-backend.ps1`
- Inspect: `scripts/dev-backend.Tests.ps1`

**Interfaces:**
- Consumes: the two launchers and the local backend virtual environment.
- Produces: fresh evidence that the API and Transformer run together and that shutdown removes their process trees.

- [ ] **Step 1: Validate PowerShell parsing**

Run:

```powershell
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path .\scripts\dev-backend.ps1),
    [ref]$null,
    [ref]$errors
) | Out-Null
if ($errors.Count -gt 0) { throw ($errors | Out-String) }
```

Expected: no parser errors.

- [ ] **Step 2: Run focused Pester coverage**

Run:

```powershell
Invoke-Pester -Path .\scripts\dev-backend.Tests.ps1 -Output Detailed
```

Expected: all tests pass with zero failures.

- [ ] **Step 3: Run the live launcher smoke test**

Start the backend in a dedicated PowerShell process with a temporary target root and isolated temporary database environment. Poll `http://127.0.0.1:<port>/health` until it returns HTTP 200, inspect process command lines to confirm `app.orchestration.transformer_worker` is running, then stop the launcher and verify no repository Uvicorn or Transformer process remains.

- [ ] **Step 4: Run affected backend regression tests**

Run:

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m pytest -q tests\test_transformer_worker_wake.py tests\test_database_startup.py tests\test_config.py
```

Expected: exit code 0 with zero failed tests.

- [ ] **Step 5: Run final repository checks**

Run:

```powershell
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors, only the approved launcher/test/documentation changes are present, and the final diff is reviewable.
