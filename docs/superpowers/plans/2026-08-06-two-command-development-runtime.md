# Two-Command Development Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the complete local frontend/API/Transformer solution start from one frontend command and one backend command.

**Architecture:** Keep FastAPI and the durable Transformer worker as separate Python processes. Extend the existing PowerShell backend launcher into a fail-fast supervisor that configures the target root, migrates the database, starts both children inside one Windows kill-on-close Job Object, and monitors them.

**Tech Stack:** Windows PowerShell, Pester 3.4, Python virtual environment, Alembic, Uvicorn, FastAPI.

## Global Constraints

- The API must never execute migration commands in its request process.
- The Transformer worker remains a separate Python child process.
- `backend/.venv/Scripts/python.exe` is the only Python executable used by the launcher.
- `ALLOWED_TARGET_ROOTS` is set before either child starts.
- Each backend process is assigned to the launcher's Job Object before it runs.
- Uvicorn uses port `8000` by default and retains `--reload` for development.

---

### Task 1: Backend development supervisor

**Files:**
- Modify: `scripts/dev-backend.ps1`
- Create: `scripts/tests/dev-backend.Tests.ps1`

**Interfaces:**
- Consumes: `backend/.venv/Scripts/python.exe`, `ALLOWED_TARGET_ROOTS`, Alembic configuration.
- Produces: `Invoke-BackendDevelopmentRuntime`, `Start-BackendRuntimeProcesses`, and a native Windows Job Object helper available when the script is dot-sourced for testing.

- [ ] **Step 1: Write failing Pester tests**

Add tests that require target-root initialization, two distinct child process
commands, virtual-environment Python selection, Job Object assignment, and live
descendant termination when the job closes.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
Invoke-Pester .\scripts\tests\dev-backend.Tests.ps1 -PassThru
```

Expected: failures because the supervisor functions do not exist.

- [ ] **Step 3: Implement the minimal supervisor**

Refactor `dev-backend.ps1` into dot-sourceable functions plus a guarded main
entry point. Apply migrations synchronously, then create Uvicorn and the
Transformer worker suspended, assign each to the same kill-on-close Job Object,
resume them, and poll both. Dispose the job in `finally`.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
Invoke-Pester .\scripts\tests\dev-backend.Tests.ps1 -PassThru
```

Expected: all launcher tests pass.

### Task 2: Developer startup documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/developer-setup.md`
- Modify: `scripts/README.md`

**Interfaces:**
- Consumes: the `dev-backend.ps1 -TargetRoot <path> [-Port <port>]` interface from Task 1.
- Produces: one authoritative two-command local startup procedure.

- [ ] **Step 1: Add a failing documentation assertion**

Extend the Pester file to require the backend documentation to identify both
the API and Transformer worker and show the `-TargetRoot` parameter.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
Invoke-Pester .\scripts\tests\dev-backend.Tests.ps1 -PassThru
```

Expected: the documentation assertion fails against the current text.

- [ ] **Step 3: Update the three startup guides**

Document the two commands, the default target root, the optional explicit
target root, and the fact that the backend launcher supervises two child
processes while preserving API/worker isolation.

- [ ] **Step 4: Run focused and regression verification**

Run:

```powershell
Invoke-Pester .\scripts\tests\dev-backend.Tests.ps1 -PassThru
cd backend
.\.venv\Scripts\python.exe -m pytest tests\test_command_route_authorization.py tests\test_transformer_worker_wake.py -q
```

Expected: all focused tests pass.

### Task 3: Final static and repository checks

**Files:**
- Inspect: all files changed by Tasks 1 and 2.

**Interfaces:**
- Consumes: completed launcher and documentation.
- Produces: verification evidence and a clean implementation handoff.

- [ ] **Step 1: Parse the launcher without starting services**

Run PowerShell's parser against `scripts/dev-backend.ps1` and require zero
syntax errors.

- [ ] **Step 2: Run repository checks**

Run `git diff --check`, `git status --short`, and `git diff --stat`.

- [ ] **Step 3: Review scope and safety**

Confirm that cleanup closes only the launcher-owned Job Object, no API code was
changed, no secrets or generated runtime files were added, and no unrelated
files changed.
