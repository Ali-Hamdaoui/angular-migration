# Architecture Audit Report: G01 Command Runtime Branch

**Branch:** `hermes/01-command-runtime`
**Worktree:** `/home/ubuntu/amfa-worktrees/01-command-runtime`
**Head SHA:** `bff54c0c2e2a876671765ba92a256e02bebc5917`
**Audit Date:** 2026-07-19
**Auditor:** Architecture/Contract/Security Auditor

---

## Severity Legend

| Severity | Definition |
|----------|------------|
| **🔴 BLOCKER** | Must fix before push. Violates core architecture rule; creates security or authority boundary breach. |
| **🟠 CRITICAL** | Must fix before push. Violates contract or correctness invariant; will cause data loss or wrong behavior. |
| **🟡 MAJOR** | Should fix before push. Violates AGENT.md rule, best practice, or security hardening; risk in edge cases. |
| **🔵 MINOR** | Fix at convenience. Code quality, naming, or technical debt. |
| **⚪ INFO** | Observation only. No action required. |

---

## 1. Sole Execution Authority

**Rule:** `CommandExecutor is the SOLE external-process execution path`. Only `command_execution/worker.py` may call `subprocess.Popen`.

### 1.1 All subprocess calls in backend/ 🔴 BLOCKER

| File | Line | Call | Status |
|------|------|------|--------|
| `backend/app/command_execution/worker.py` | 320 | `subprocess.Popen(...)` | **OK** — sole authorized Popen, shell=False |
| `backend/app/command_execution/worker.py` | 388 | `process.send_signal(...)`, `os.killpg(...)` | **OK** — process control, not process creation |
| `backend/tests/test_source_snapshot_security_s1_f07.py` | 117 | `subprocess.run(...)` | **OK** — test file |

**Verdict:** PASS — only `worker.py` calls `subprocess.Popen`. No `os.system`, `os.popen`, or `subprocess.run`/`call` in production code.

### 1.2 Duplicate execution authority via CommandExecutorService 🟠 CRITICAL

`CommandExecutorService.queue_command()` (command_executor_service.py) bypasses the G01 `CommandPolicyEngineService.validate()` and creates a `CommandRequestDto` + uses `WorkerSupervisor.run()` directly. It only calls `CommandRegistry().find()` (Sprint 0 registry) for the command definition, which is a weaker check — it doesn't verify executable aliases, arguments, network profile, or plan membership.

**Evidence:** Lines 197-215 of command_executor_service.py:
```python
registry = CommandRegistry()           # Sprint 0 registry, NOT G1 policy engine
definition = registry.find(command_id)  # only checks command_id exists
...
structured = StructuredCommandRequest(...)  # directly builds request
supervised = self._supervisor.run(structured)  # bypasses policy engine
```

The `_policy_engine` attribute is initialized (line 91) but **never called** in `queue_command()`.

**Impact:** An adversary (or bug) calling `/api/v1/runs/{id}/commands` with a valid command_id from the registry can bypass plan-membership checks, network profile enforcement, and cancellation policy validation. The `/operator/command-policy/validate` endpoint is advisory only.

**Fix:** Call `self._policy_engine.validate(session, dto)` at the start of `queue_command()` before creating the execution record.

---

## 2. Shell=False Enforcement

**Rule:** Commands must have `shell=false` at every layer.

### 2.1 DTO layer 🔵 MINOR

`CommandRequestDto` has `shell: bool = False` as a default — correct.
`CommandExecuteRequestDto` (the API input DTO) does **NOT** expose a `shell` field — the value is always implicitly `False`.

This is acceptable but fragile: the field exists on the underlying model, and someone could set it via a raw ORM call. A defensive `model_validator` rejecting `shell=True` would be stronger.

### 2.2 Policy layer ✅ PASS

`CommandPolicy.validate()` (worker.py, line 141) rejects `shell=True` explicitly:
```python
if request.shell is not False:
    raise CommandPolicyViolation("Shell execution is forbidden in Sprint 0")
```

### 2.3 Supervisor layer ✅ PASS

`subprocess.Popen(... shell=False)` (worker.py, line 326) — hard-coded `shell=False`.

### 2.4 G01 Policy engine 🟠 CRITICAL

`CommandPolicyEngineService._check_shell_enforcement()` (command_registry_service.py, line 266-269):

```python
def _check_shell_enforcement(self, request):
    # The DTO has no shell field — shell=false is always enforced
    return AuthorizationCheckResult(passed=True, rule_name="shell_enforcement")
```

This is a **tautological pass**. The DTO (`CommandPolicyValidateRequestDto`) has **no shell field**, so the check always passes without actually inspecting anything. If a future change adds a `shell` field to the DTO, this check will silently continue passing.

**Fix:** Add a `shell` field to `CommandPolicyValidateRequestDto` and check it explicitly in `_check_shell_enforcement()`.

---

## 3. Idempotency Correctness

**Rule:** Mutations require expected state version and idempotency key; **replay verifies payload identity**.

### 3.1 CommandExecutorService — payload not verified on replay 🔴 BLOCKER

`CommandExecutorService.queue_command()` (lines 122-128):
```python
existing = session.scalar(
    select(CommandExecutionModel)
    .where(CommandExecutionModel.run_id == run_id)
    .where(CommandExecutionModel.idempotency_key == idempotency_key)
)
if existing is not None:
    return self._response_from_model(existing, idempotent_replay=True)
```

The idempotency check matches on `(run_id, idempotency_key)` **only** — it does NOT verify that the new request's payload (executable, arguments, timeout, network_profile, etc.) matches the original request's payload. An attacker could replay the same key with different parameters and get the stale result without executing.

**Impact:** Violates "replay verifies payload identity" from AGENT.md §7.

**Fix:** Compare the incoming request's payload fields against the stored execution record. If they differ, raise an error (e.g., `IDEMPOTENCY_MISMATCH`).

### 3.2 CommandLogService — idempotency via execution_id + sequence ✅ PASS

`CommandLogService.append_chunk()` generates idempotency key as `f"log-{execution_id}-{next_seq}"` — chained to a deterministic sequence, so replay produces the same key. OK.

### 3.3 JobSupervisorService cancel — idempotency via key only 🟡 MAJOR

`cancel_command()` (line 169-175) checks `WorkflowEventModel` by `(run_id, idempotency_key)`. Same key → idempotent replay. But does **not** verify the execution_id matches. If someone sends the same idempotency_key for a different execution_id, they get a false replay.

### 3.4 TransitionService — idempotency on key only, payload not verified 🔵 MINOR

`StateTransitionService.apply_transition()` checks `(run_id, idempotency_key)` but does not verify that the transition request parameters match. Replaying `CANCELLING` with a different `expected_state_version` returns the old result without checking.

---

## 4. State Version Tracking

**Rule:** Mutations require expected state version; states version-gated.

### 4.1 CommandExecutionModel.state_version initialized but never incremented 🟠 CRITICAL

The model has `state_version` (default=1) and `event_sequence` (default=1), but:
- They are set once during creation (line 153).
- They are **never incremented** when status transitions from PENDING → RUNNING → SUCCEEDED/FAILED.
- The `_response_from_model()` always returns whatever value was in the model (lines 328-329).

**Impact:** Any consumer relying on `state_version` to detect execution changes gets stale data. Optimistic concurrency is effectively absent for command execution records.

### 4.2 Authorization audit has hardcoded state_version 🟡 MAJOR

`commands.py` route handler (line 109): `state_version=1` — always hardcoded to 1, never reads the run's actual state version.

### 4.3 TransitionService versioning is correct ✅ PASS

`StateTransitionService.apply_transition()` properly checks `run.state_version != request.expected_state_version` and increments on success.

---

## 5. Policy Engine Coverage

**Required checks (AGENT.md §7):** shell, plan membership, network, cancellation, timeout, executable, arguments.

### 5.1 G01 CommandPolicyEngineService checks

| Check | Present | Details |
|-------|---------|---------|
| Shell enforcement | ❌ | Tautological pass (no `shell` field in DTO) |
| Command registered | ✅ | Looks up by `command_id` |
| Executable matches template | ✅ | Compares against `allowed_executables` |
| Arguments match template | ✅ | Exact match |
| Network profile allowed | ✅ | Checked against `NetworkProfile` enum |
| Cancellation policy | ✅ | Checked against `CancellationPolicy` enum |
| Timeout within range | ✅ | >0 and <=3600 |
| Plan membership | ✅ | Checks approved stage plan |

**Verdict:** 7/8 policy functions exist; shell enforcement is the missing substantive check.

### 5.2 Plan membership edge case 🟡 MAJOR

When no stage plan exists, `_check_plan_membership()` returns `passed=True` with reason "no stage plan found; plan membership not enforced". This is a **soft pass** — commands can execute without a plan. The design may be intentional for diagnostic commands, but it weakens the guarantee.

---

## 6. Authorization Audit Persistence

### 6.1 Audit records are persisted ✅ PASS

`commands.py` route creates both `CommandAuthorizationAuditModel` and a `WorkflowEventModel` for every authorization decision.

### 6.2 Audit has no authorization_id in execution record 🔵 MINOR

`CommandExecutionModel` has no `authorization_id` foreign key or reference. The execution record created by `CommandExecutorService` doesn't link back to the authorization that allowed it. The frozen schema `command_execution_record.schema.json` requires `authorization_id` as mandatory.

---

## 7. Event Emission

### 7.1 State transitions with events

| Transition | Event(s) Emitted | Status |
|------------|------------------|--------|
| QUEUED | `COMMAND_QUEUED` | ✅ |
| RUNNING | `COMMAND_STARTED` | ✅ |
| SUCCEEDED | `COMMAND_SUCCEEDED` | ✅ |
| FAILED | `COMMAND_FAILED` | ✅ |
| Cancelled | `COMMAND_INTERRUPTED` | ✅ |
| Log chunk | `COMMAND_OUTPUT_AVAILABLE` | ✅ |
| Authorization accepted | `COMMAND_AUTHORIZATION_ACCEPTED` | ✅ |
| Authorization rejected | `COMMAND_AUTHORIZATION_REJECTED` | ✅ |
| Cancel requested | `RUN_CANCEL_REQUESTED` + `COMMAND_CANCELLED` | ✅ |

**Verdict:** All required transitions emit events. However, see §10 for cancellation event concerns.

### 7.2 Event sequencing maintained ✅ PASS

`_append_event` queries the latest sequence and increments by 1. `WorkflowEventModel` has `UniqueConstraint("run_id", "idempotency_key")`, preventing duplicate events.

### 7.3 Duplicate events on cancel 🟡 MAJOR

`JobSupervisorService.cancel_command()` emits TWO events: `RUN_CANCEL_REQUESTED` and `COMMAND_CANCELLED`. `COMMAND_CANCELLED` implies the cancellation has completed, but the actual process may not have been stopped yet — the cancel only sets a DB flag. There's no mechanism to confirm the process actually terminated.

---

## 8. Lease Pattern

### 8.1 Lease acquisition ✅ PASS

`acquire_lease()` checks for existing non-expired leases, enforces exclusivity per run.

### 8.2 Lease renewal ✅ PASS

`renew_lease()` verifies ownership and expiry before extending.

### 8.3 Lease release ✅ PASS

`release_lease()` verifies ownership before deleting.

### 8.4 Lease expiry boundary 🟡 MAJOR

`WorkerLeaseModel.expires_at` has no database-level enforcement (no `CHECK` constraint, no TTL). Expired leases are filtered by the application layer (`expires_at > now`). A buggy query could miss the filter. Consider a cleanup job or DB-level TTL.

### 8.5 Hardcoded backend_instance_id 🔵 MINOR

`JobSupervisorService.acquire_lease()` line 93: `backend_instance_id="hermes-worktree-01"` is hardcoded instead of being configurable.

---

## 9. Cancellation Flow

### 9.1 Cancel sets DB flag but doesn't kill process 🔴 BLOCKER

`JobSupervisorService.cancel_command()` (lines 187-191) sets `cancelled=True`, `cancel_requested_at`, and `cancel_requested_by` on the execution record. However, there is **no integration** with the `cancel_event` threading.Event that the `WorkerSupervisor` supports.

Looking at `WorkerSupervisor.run()` (worker.py, line 351):
```python
if cancel_event is not None and cancel_event.is_set() and process.poll() is None:
    cancelled = True
    self.terminate_process_tree(process)
```

`CommandExecutorService.queue_command()` calls `self._supervisor.run(structured)` **without** passing a `cancel_event`. The `cancel_event` parameter defaults to `None`. So even after the cancel flag is set, the running OS process continues until it times out or completes.

**Impact:** Cancel is a no-op for running processes. The process continues executing with terminal/disk/network access.

**Fix:** Wire a shared `cancel_event` from `CommandExecutorService` (or `JobSupervisorService`) through to `WorkerSupervisor.run()` so that cancel actually terminates the process.

### 9.2 Cancel emits COMMAND_CANCELLED before actual termination 🟠 CRITICAL

`cancel_command()` emits `COMMAND_CANCELLED` event immediately after setting the DB flag, but the process may still be running. Downstream consumers see the event and assume the command has stopped when it hasn't.

**Fix:** Only emit `COMMAND_CANCELLED` after confirmation that `terminate_process_tree()` was called, or wire through the cancel mechanism so cancellation is synchronous.

---

## 10. Contract/Frozen Schema Compliance

### 10.1 command_authorization.schema.json 🟠 CRITICAL

The frozen schema requires these fields as **required**:
- `cwd_alias` (string, minLength 1)
- `plan_id` (string or null)
- `execution_profile_id` (string, minLength 1)

The `CommandPolicyValidateResponseDto` is **missing** these fields:
- `cwd_alias` — not present
- `plan_id` — not present
- `execution_profile_id` — present as field but the schema value maps differently (DTO has `execution_profile_id` not separate)

### 10.2 command_execution_record.schema.json 🟠 CRITICAL

Frozen schema requires:
- `authorization_id` (required, string)
- `runtime_checksum` (required, pattern `^sha256:[0-9a-f]{64}$`)

`CommandExecutionModel` has:
- No `authorization_id` field at all
- `runtime_checksum` is nullable, not required, and never generated

### 10.3 worker_lease.schema.json 🟡 MAJOR

Frozen schema requires `status` and `heartbeat_at` as required:
- `WorkerLeaseModel` has no `status` column — status is inferred from `expires_at > now`
- `heartbeat_at` is nullable in the model but required in the schema

---

## 11. Secret Leakage

### 11.1 Environment variables not scoped in subprocess.Popen 🟡 MAJOR

`WorkerSupervisor.run()` (worker.py) calls `subprocess.Popen(command, ...)` **without** passing an `env` parameter. This means the subprocess inherits the **full parent environment**, including:
- `AZURE_OPENAI_API_KEY` (if loaded from `.env`)
- Any other secrets in the environment

The `CommandTemplate.allowed_env_vars` field exists (e.g., `NODE_OPTIONS`, `NPM_CONFIG_CACHE`) but is **never used** to filter the subprocess environment.

**Fix:** At minimum, pass `env=os.environ.copy()` filtered to only `allowed_env_vars`. Better: pass only the minimum required variables.

### 11.2 CommandRequestDto logs idempotency_key to artifacts 🔵 MINOR

The `CommandLogWriter.write()` method (worker.py, line 237) writes the `idempotency_key` into the command log artifact (JSON file on disk). If `idempotency_key` is sensitive, this leaks it.

---

## 12. Additional Findings

### 12.1 Unused import in command_executor_service.py 🔵 MINOR

```python
import subprocess   # line 12 — imported but never used
```

All subprocess operations are delegated to `WorkerSupervisor`.

### 12.2 Missing authorization_id reference 🟡 MAJOR

`CommandExecutorService` creates execution records without linking them to an authorization. The execution flow is:
1. API receives `CommandExecuteRequestDto` (no authz_id)
2. Skips policy engine
3. Creates `CommandExecutionModel` with no `authorization_id`

The audit trail is broken: you can't trace an execution back to its authorization decision.

### 12.3 test_command_executor_services.py has no tests for queue_command() 🔵 MINOR

The test file tests `CommandLogService`, `JobSupervisorService`, but has no tests that call `CommandExecutorService.queue_command()` — the main execution path is untested.

---

## Summary Table

| # | Finding | Severity | File(s) |
|---|---------|----------|---------|
| 1.1 | Sole execution authority maintained | ✅ PASS | `worker.py` |
| 1.2 | CommandExecutorService bypasses G01 policy engine | 🔴 **BLOCKER** | `command_executor_service.py` L197-215 |
| 2.4 | Shell enforcement is tautological pass | 🟠 **CRITICAL** | `command_registry_service.py` L266-269 |
| 3.1 | Idempotency replay doesn't verify payload identity | 🔴 **BLOCKER** | `command_executor_service.py` L122-128 |
| 4.1 | state_version never incremented on execution record | 🟠 **CRITICAL** | `command_executor_service.py` |
| 4.2 | Authorization audit state_version hardcoded to 1 | 🟡 MAJOR | `commands.py` L109 |
| 5.2 | Plan membership soft-passes when no plan exists | 🟡 MAJOR | `command_registry_service.py` L321-327 |
| 6.2 | No authorization_id in execution record | 🔵 MINOR | `command_executor_service.py` |
| 7.3 | Duplicate cancel events, COMMAND_CANCELLED before termination | 🟡 MAJOR | `job_supervisor_service.py` L194-204 |
| 8.4 | Lease expiry only enforced at application layer | 🟡 MAJOR | `job_supervisor_service.py` |
| 8.5 | backend_instance_id hardcoded | 🔵 MINOR | `job_supervisor_service.py` L93 |
| 9.1 | Cancel does not terminate running process (no cancel_event wired) | 🔴 **BLOCKER** | `command_executor_service.py` L215, `job_supervisor_service.py` |
| 9.2 | COMMAND_CANCELLED emitted before actual termination | 🟠 **CRITICAL** | `job_supervisor_service.py` L200-204 |
| 10.1 | Authorization schema: missing cwd_alias, plan_id in DTO | 🟠 **CRITICAL** | `contracts.py`, `command_authorization.schema.json` |
| 10.2 | Execution record schema: missing authorization_id, runtime_checksum | 🟠 **CRITICAL** | `workflow.py`, `command_execution_record.schema.json` |
| 10.3 | Lease schema: missing status, heartbeat_at required but nullable | 🟡 MAJOR | `workflow.py`, `worker_lease.schema.json` |
| 11.1 | Subprocess inherits full environment; allowed_env_vars unused | 🟡 MAJOR | `worker.py` L320-329 |
| 11.2 | idempotency_key persisted in artifacts | 🔵 MINOR | `worker.py` L237 |
| 12.1 | Unused import subprocess in command_executor_service | 🔵 MINOR | `command_executor_service.py` L12 |
| 12.2 | No authorization trail from execution to authorization | 🟡 MAJOR | `command_executor_service.py` |
| 12.3 | queue_command() has no tests | 🔵 MINOR | `test_command_executor_services.py` |

### Count by Severity

| Severity | Count |
|----------|-------|
| ✅ PASS (OK findings) | 7 |
| 🔴 BLOCKER | 3 |
| 🟠 CRITICAL | 5 |
| 🟡 MAJOR | 7 |
| 🔵 MINOR | 6 |

---

## Criticality-Ordered Action Items

### 🔴 BLOCKER (Fix before push)
1. **Wire G01 policy engine** into `CommandExecutorService.queue_command()` before execution.
2. **Verify payload identity on idempotency replay** — compare incoming payload against stored record.
3. **Wire cancel_event** from cancellation flow into `WorkerSupervisor.run()` so cancel kills the process.

### 🟠 CRITICAL (Fix before push)
4. **Fix shell enforcement** in `CommandPolicyEngineService` — add `shell` field to DTO and check it.
5. **Increment state_version** on `CommandExecutionModel` during status transitions.
6. **Only emit COMMAND_CANCELLED after actual termination**, not when cancel is merely requested.
7. **Add `cwd_alias` and `plan_id`** to `CommandPolicyValidateResponseDto`.
8. **Add `authorization_id` and `runtime_checksum`** to `CommandExecutionModel` to match frozen schemas.

### 🟡 MAJOR (Fix before push)
9. Scope environment variables passed to `subprocess.Popen` using `allowed_env_vars`.
10. Add `state_version` reading from run model instead of hardcoding `1` in authorization audit.
11. Consider whether plan membership should hard-reject when no plan exists, not soft-pass.
12. Add authorization_id reference to CommandExecutionModel for audit trail.
13. Add DB-level or periodic lease expiry enforcement.
14. Add `status` and non-nullable `heartbeat_at` to `WorkerLeaseModel`.
