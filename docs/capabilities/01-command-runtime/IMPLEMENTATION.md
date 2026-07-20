# G01 — Governed Command Runtime: Implementation Guide

## 1. Goal Identity

| Field | Value |
|---|---|
| Goal | G01 — Governed Command Runtime |
| Branch | `hermes/01-command-runtime` |
| Base SHA | `d759861290c1e76e26c4f2b27bbee9a77a12f0b5` |
| Final SHA | `f4c738f4e9a4dd91d3d2b059410e8d3641122508` (pre-remediation), `3f5450b` (post-remediation) |
| Sprint | Sprint 3 |
| Jira features | AMFA-140, AMFA-141, AMFA-142, AMFA-143 |
| Completion level | `branch_ready` |
| Branch ready | true |
| Integration verified | false |
| Jira complete | false |

## 2. Objective

Build the sole structured command path for the AMFA control tower: a command registry and policy engine, authoritative execution evidence, durable live logs, and a JobSupervisor with lease-based ownership, timeout, and cancellation for the Angular 18→21 migration workflow.

All external process execution must pass through the registered command template and policy engine — arbitrary shell execution is structurally forbidden. The frontend projects backend state only via typed API clients and SSE events.

## 3. Scope

### Implemented

- **S3-F01 — Register structured commands and reject arbitrary shell execution**
  - `CommandRegistryService` — DB-backed CRUD for registered command templates with 6 default templates: python-version, node-version, npm-version, npx-version, git-version, npm-ci-bootstrap
  - `CommandPolicyEngineService` — 8 conjunctive policy checks: shell enforcement (structural = false), command registration, executable match, argument match, network profile allowlisting, cancellation policy support, timeout range validation, plan membership (optional)
  - `GET /api/v1/operator/command-templates` — list seeded templates, auto-seeds on empty
  - `POST /api/v1/operator/command-policy/validate` — run all checks, persist audit record, emit `COMMAND_AUTHORIZATION_ACCEPTED`/`REJECTED` events
  - `CommandPolicyInspector.tsx` — frontend component showing template listing, executable/args preview, validation button, policy decision rendering
  - `CommandAuthorizationAuditModel` — durable audit trail for every authorization decision

- **S3-F02 — Execute one approved command and persist authoritative command evidence**
  - `CommandExecutorService.queue_command()` — full lifecycle: idempotency check (key + payload), policy validation, execution record creation (QUEUED → RUNNING → SUCCEEDED/FAILED/TIMED_OUT/CANCELLED), event emission
  - `POST /api/v1/runs/{run_id}/commands` — queue and execute a command synchronously
  - `GET /api/v1/runs/{run_id}/commands/{execution_id}` — retrieve execution record
  - `CommandExecutionModel` — stores execution metadata: `authorization_id`, `runtime_checksum`, `state_version`, idempotency lineage, process metadata, stdout/stderr artifact references
  - `runtime_checksum` — SHA-256 of combined process output, stored as `sha256:...`
  - `authorization_id` — ties execution to the policy authorization decision
  - `Environment sanitization` — `WorkerSupervisor._build_safe_environment()` filters out environment variables matching `TOKEN`, `SECRET`, `KEY`, `PASSWORD`, `CREDENTIAL`, `HERMES_`, `API_KEY`, `ACCESS_KEY`, `PRIVATE_KEY`

- **S3-F03 — Stream live command logs and recover after browser reconnect**
  - `CommandLogService` — ordered chunk persistence with sequence numbers, stream type (stdout/stderr/system), offset/limit/cursor pagination
  - `GET /api/v1/runs/{run_id}/commands/{execution_id}/logs` — retrieve log chunks with optional `stream`, `offset`, `limit`, `cursor` parameters
  - `GET /api/v1/runs/{run_id}/commands/{execution_id}/logs/summary` — stream summary with per-stream counts
  - `COMMAND_OUTPUT_AVAILABLE` event emitted per chunk
  - `LogViewer.tsx` — tail/pause, stdout/stderr filter buttons, search, reconnect indicator, auto-poll for live updates, scroll-to-bottom

- **S3-F04 — Own commands with JobSupervisor, leases, timeout, and explicit cancellation**
  - `JobSupervisorService` — exclusive worker lease acquire/renew/release with expiry, active-command tracking, run state transitions via `StateTransitionService`
  - `POST /api/v1/runs/{run_id}/commands/{execution_id}/cancel` — sets `cancel_event` (threading.Event) for OS process termination, updates DB state, emits `RUN_CANCEL_REQUESTED`/`COMMAND_CANCELLED`/`RUN_CANCELLED` events
  - `GET /api/v1/runs/{run_id}/active-command` — currently executing command
  - `GET /api/v1/runs/{run_id}/active-lease` — active worker lease
  - `WorkerLeaseModel` — lease ownership with `backend_instance_id`, `heartbeat_at`, `expires_at`

### Reused

- Sprint 0 `WorkerSupervisor` — sole `subprocess.Popen` call, process-tree termination via `os.killpg(SIGTERM)` / `SIGKILL`
- Sprint 0 `ExecutionWorker` — backward-compatible command execution with in-memory idempotency
- Sprint 2 `StateTransitionService` — run-state transition validation and persistence
- Sprint 2 `MigrationRunModel`, `StageExecutionPlanModel` — run/workflow context
- Sprint 2 frozen schemas in `goals/shared/contracts/` — `approved_stage_plan`, `artifact_ref`, `durable_event_envelope`

### Not Implemented

- Async SSE streaming for continuous log output (current implementation uses synchronous chunk append + offset-based client polling)
- Hard-kill supervisor thread for stale leases (cancellation relies on `cancel_event` + `process.wait(timeout=1)`)

### Explicitly Out of Scope

- User-defined command templates (templates are pre-seeded)
- PowerShell wrappers or `shell=true` execution
- Cross-run log aggregation
- Interactive command response

## 4. Architecture

```mermaid
flowchart TD
    UI[Next.js Frontend] -->|GET /templates| API1[GET /api/v1/operator/command-templates]
    UI -->|POST /validate| API2[POST /api/v1/operator/command-policy/validate]
    UI -->|POST /commands| API3[POST /api/v1/runs/{id}/commands]
    UI -->|GET /logs| API4[GET /api/v1/runs/{id}/commands/{eid}/logs]
    UI -->|POST /cancel| API5[POST /api/v1/runs/{id}/commands/{eid}/cancel]

    API1 --> Registry[CommandRegistryService]
    API2 --> Policy[CommandPolicyEngineService]
    API3 --> Executor[CommandExecutorService]
    API4 --> LogService[CommandLogService]
    API5 --> Supervisor[JobSupervisorService]

    Executor --> Worker[WorkerSupervisor]
    Worker -->|subprocess.Popen| Process[External Command]
    Executor --> Policy
    Executor --> EventDB[(Workflow Events)]
    Executor --> ExecDB[(Command Executions)]

    Supervisor --> LeaseDB[(Worker Leases)]
    Supervisor --> StateTrans[StateTransitionService]
    Supervisor --> Executor

    LogService --> ChunkDB[(Log Chunks)]
    LogService --> EventDB

    Registry --> TemplateDB[(Command Templates)]
    Registry --> AuthDB[(Authorization Audits)]

    UI -->|SSE| SSEStream[SSE Event Stream]
    SSEDB[(Workflow Events)] --> SSEStream --> UI
```

## 5. Backend Implementation

| File | Main symbols | Responsibility | Important behavior |
|---|---|---|---|
| `backend/app/services/command_registry_service.py` | `CommandRegistryService`, `CommandPolicyEngineService`, `DEFAULT_COMMAND_TEMPLATES` | Template CRUD, 8-policy validation engine | Auto-seeds 6 templates on first `list_templates()`; plan membership check is lazy-imported from Sprint 2 |
| `backend/app/services/command_executor_service.py` | `CommandExecutorService`, `CommandExecutorError`, `CommandExecutionResponse` | Authoritative command execution lifecycle | Idempotency key + payload verification; `authorization_id` persisted from policy response; `runtime_checksum` computed as SHA-256 of stdout+stderr |
| `backend/app/services/command_log_service.py` | `CommandLogService`, `LogChunkDto` | Ordered log chunk persistence | Sequence numbers per execution; `cursor` parameter filters `sequence > cursor` for reconnect resume |
| `backend/app/services/job_supervisor_service.py` | `JobSupervisorService`, `JobSupervisorError`, `LeaseResult` | Exclusive lease management, cancellation, run state transitions | Uses `StateTransitionService` for `CANCELLING` transition; idempotent cancel with idempotency key dedup |
| `backend/app/api/routes/commands.py` | `list_command_templates`, `validate_command_policy` | Operator-facing template and policy endpoints | Auto-seeds templates on empty list |
| `backend/app/api/routes/run_commands.py` | `queue_command`, `get_command_execution`, `get_command_logs`, `get_command_log_summary`, `cancel_command`, `get_active_command`, `get_active_lease` | Run-scoped command execution, log retrieval, cancellation | All routes registered under `/api/v1/operator/` and `/api/v1/runs/` |
| `backend/app/domain/command.py` | `CommandTemplate`, `CommandPolicyRule`, `CommandPolicyEngine`, `AuthorizationRequest`, `AuthorizationResult` | Domain types for command shape and policy | `allowed_env_vars` tuple per template; `NetworkProfile` and `CancellationPolicy` enums |
| `backend/app/domain/contracts.py` | `WorkflowEventType`, `CommandStatus`, `CommandRequestDto`, `CommandPolicyValidateRequestDto/ResponseDto` | Shared DTOs and event type definitions | All event types for G01 lifecycle including `COMMAND_QUEUED`, `COMMAND_OUTPUT_AVAILABLE`, `RUN_CANCEL_REQUESTED` |
| `backend/app/command_execution/worker.py` | `WorkerSupervisor`, `ExecutionWorker`, `SupervisedProcessResult`, `CommandRegistry`, `CommandPolicy` | Low-level subprocess execution | `_build_safe_environment()` filters secret variables; `terminate_process_tree()` kills process group; `start_new_session=True` for process group isolation |
| `backend/app/repositories/models/workflow.py` | `CommandTemplateModel`, `CommandAuthorizationAuditModel`, `CommandExecutionModel`, `CommandLogChunkModel`, `WorkerLeaseModel` | SQLAlchemy ORM models | `authorization_id` column added via migration `20260719_09`; `runtime_checksum` stored as `sha256:...` |
| `backend/alembic/versions/20260719_09_add_authorization_id.py` | — | Adds `authorization_id` column to `command_executions` | New migration, revision ID in Alembic history |

### Domain Models

- `CommandTemplate` — `command_id`, `executable`, `arguments`, `executable_aliases`, `allowed_env_vars`, `max_output_bytes`, `status`
- `CommandPolicyRule` — `rule_name`, `enabled`, `severity` — base class for policy checks (block, audit)
- `AuthorizationRequest` — `command_id`, `executable`, `arguments`, `working_directory_alias`, `network_profile`, `cancellation_policy`, `timeout_seconds`
- `AuthorizationResult` — `passed`, `rule_name`, `reason`

### Enums

- `CommandTemplateStatus` — `ACTIVE`, `INACTIVE`
- `NetworkProfile` — `none`, `outbound_https`, `full_outbound`, `restricted`
- `CancellationPolicy` — `terminate_process_tree`, `graceful_shutdown`
- `CommandStatus` — `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `TIMED_OUT`, `REJECTED`
- `WorkflowEventType` — 25+ types including `COMMAND_QUEUED`, `COMMAND_STARTED`, `COMMAND_SUCCEEDED`, `COMMAND_CANCELLED`, `RUN_CANCEL_REQUESTED`, `COMMAND_OUTPUT_AVAILABLE`

### Services

**CommandRegistryService** — CRUD for `CommandTemplateModel`. Seeds 6 default templates on first empty list. Methods: `list_templates()`, `get_template()`, `find_template_by_command_id()`, `seed_defaults()`.

**CommandPolicyEngineService** — 8 conjunctive policy checks. Returns `CommandPolicyValidateResponseDto` with `authorization_id`, `decision`, `reasons`. Persists a `CommandAuthorizationAuditModel` record for every validation via `validate()`.

**CommandExecutorService** — Orchestrates queue_command lifecycle:
1. Check idempotency (key + payload identity)
2. Validate against policy engine (or use mock)
3. Create execution record in PENDING state
4. Emit `COMMAND_QUEUED` event
5. Update status to RUNNING, emit `COMMAND_STARTED`
6. Build `StructuredCommandRequest`, create `cancel_event`
7. Call `WorkerSupervisor.run()` with cancel event
8. On completion: compute `runtime_checksum`, update status, emit completion event
9. On error: update status to FAILED, emit `COMMAND_FAILED`

**CommandLogService** — Append ordered log chunks per execution with sequence numbers. Retrieve with `offset`, `limit`, `stream_filter`, `cursor` (sequence > cursor for reconnect).

**JobSupervisorService** — Exclusive lease per run with `acquire_lease()` (checks existing non-expired), `renew_lease()`, `release_lease()`. `cancel_command()` updates execution record, emits cancellation events, transitions run state to CANCELLING via `StateTransitionService`.

### Repositories

`CommandExecutionModel` — fields: `id`, `run_id`, `stage_id`, `authorization_id`, `idempotency_key`, `executable`, `arguments`, `status`, `runtime_checksum`, `cancelled`, `cancel_requested_at`, `cancel_requested_by`, `state_version`, `event_sequence`, `worker_id`, `stdout_artifact_id`, `stderr_artifact_id`, `start_fingerprint`, `end_fingerprint`. Unique constraint on `(run_id, idempotency_key)`.

### API Contracts

All routes use Pydantic DTOs defined in `backend/app/domain/contracts.py`. Error responses use structured error codes (`IDEMPOTENCY_KEY_CONFLICT`, `POLICY_REJECTED`, `LEASE_EXISTS`, `EXECUTION_NOT_FOUND`). Stable 4xx for client errors, 5xx for unexpected failures.

### Events

| Event | Trigger | Payload |
|---|---|---|
| `COMMAND_AUTHORIZATION_ACCEPTED` | Policy validation accepted | `authorization_id`, `command_id`, `executable`, `reasons=[]` |
| `COMMAND_AUTHORIZATION_REJECTED` | Policy validation rejected | `authorization_id`, `command_id`, `executable`, `reasons` |
| `COMMAND_QUEUED` | Execution record created | `execution_id`, `command_id`, `executable` |
| `COMMAND_STARTED` | Status → RUNNING | `execution_id`, `command_id` |
| `COMMAND_SUCCEEDED` | Process exit 0 | `execution_id`, `command_id`, `exit_code`, `status` |
| `COMMAND_FAILED` | Process non-zero / error | `execution_id`, `command_id`, `exit_code`, `status`, `error` |
| `COMMAND_OUTPUT_AVAILABLE` | Log chunk appended | `execution_id`, `stream`, `sequence`, `text` |
| `COMMAND_CANCELLED` | Cancel requested | `execution_id`, `actor` |
| `RUN_CANCEL_REQUESTED` | Cancel flow initiated | `execution_id`, `actor` |
| `RUN_CANCELLED` | Run transitioned to CANCELLING | `run_id`, `actor` |

### Migrations

| Migration | Revision ID | Down Rev | Behavior |
|---|---|---|---|
| `20260719_07_command_templates_and_authorization` | `20260719_07` | base | Creates `command_templates`, `command_authorization_audits` tables |
| `20260719_08_command_log_chunks` | `20260719_08` | `20260719_07` | Creates `command_log_chunks` table |
| `20260719_09_add_authorization_id` | `20260719_09` | `20260719_08` | Adds `authorization_id` column to `command_executions` |

### Error Handling

- `CommandExecutorError(code, message)` — structured error with stable code for API mapping
- `JobSupervisorError(code, message)` — structured error for lease/cancellation failures
- `CommandPolicyViolation` — raised by Sprint 0 policy layer for legacy compat
- `StateTransitionService` errors — `STALE_STATE_VERSION`, missing lease errors

### Idempotency

- `idempotency_key` on execution records, cancel requests, and workflow events
- Key + payload identity verification — same key with different payload returns `IDEMPOTENCY_KEY_CONFLICT`
- Unique constraint on `(run_id, idempotency_key)` for execution records and cancel events

### Concurrency and State Version

All models carry `state_version` (integer, default 1). Mutations check state version for stale detection (via `StateTransitionService` for run/approval state, via application logic for command records).

## 6. Frontend Implementation

| File | Component/client/type | Responsibility | Visual/runtime states |
|---|---|---|---|
| `frontend/src/components/CommandPolicyInspector.tsx` | React component | Template listing with executable/args display, validation button, decision rendering | Loading, empty (no templates), success (template list), validation running, accepted/rejected decision, error |
| `frontend/src/components/LogViewer.tsx` | React component | Tailable log viewer with stream filters, search, pause, reconnect | Loading, empty (no logs), streaming (live tail), paused, filter active (stdout/stderr), reconnect indicator |
| `frontend/src/api/commands.ts` | Typed API client | `listTemplates()`, `validateCommand()` | — |
| `frontend/src/hooks/useMigrationEvents.ts` | React hook | SSE event stream with cursor tracking | Connected, disconnected, reconnecting |

### API Clients

- `frontend/src/api/commands.ts` — `listTemplates(): Promise<CommandTemplate[]>`, `validateCommand(payload): Promise<CommandPolicyValidateResponse>`
- `frontend/src/api/runs.ts` — run-scoped command endpoints used via existing run client

### Components

**CommandPolicyInspector** — Renders a panel showing registered command templates with expandable argv details. "Validate" button sends the selected template + args to the policy endpoint. Displays decision (accepted/rejected) with policy check results per rule.

**LogViewer** — Renders log lines in a scrollable terminal-style container. Buttons for stdout/stderr/all filter, play/pause toggle for live tail. Auto-polls or uses EventSource for live updates. Shows reconnect warning when stream disconnects. Displays final artifact link on command completion.

### Visual States

All components cover: loading spinner, empty state (no templates/logs), success/content, error message, stale/conflict warning, reconnecting indicator.

## 7. API Reference

| Method | Path | Request | Response | Events | Errors | Idempotency |
|---|---|---|---|---|---|---|
| GET | `/api/v1/operator/command-templates` | — | `CommandTemplateDto[]` | — | — | N/A (read) |
| POST | `/api/v1/operator/command-policy/validate` | `CommandPolicyValidateRequestDto` | `CommandPolicyValidateResponseDto` | `COMMAND_AUTHORIZATION_ACCEPTED`/`REJECTED` | Validation errors | Via idempotency_key |
| POST | `/api/v1/runs/{run_id}/commands` | `{ executable, arguments, command_id, idempotency_key, ... }` | `CommandExecutionResponse` | `COMMAND_QUEUED`, `STARTED`, `SUCCEEDED`/`FAILED` | `POLICY_REJECTED`, `IDEMPOTENCY_KEY_CONFLICT` | Required (key+payload) |
| GET | `/api/v1/runs/{run_id}/commands/{execution_id}` | — | `CommandExecutionModel` | — | `404` | N/A |
| GET | `/api/v1/runs/{run_id}/commands/{execution_id}/logs` | `?offset=&limit=&stream=&cursor=` | `{ chunks: LogChunkDto[], total: number }` | — | — | N/A |
| POST | `/api/v1/runs/{run_id}/commands/{execution_id}/cancel` | `{ actor, idempotency_key }` | `{ cancelled, execution_id, ... }` | `RUN_CANCEL_REQUESTED`, `COMMAND_CANCELLED` | `EXECUTION_NOT_FOUND`, `EXECUTION_NOT_ACTIVE` | Via idempotency_key |
| GET | `/api/v1/runs/{run_id}/active-command` | — | `{ active_command }` or null | — | — | N/A |
| GET | `/api/v1/runs/{run_id}/active-lease` | — | `{ active_lease }` or null | — | — | N/A |

## 8. Persistence

| Table | Purpose | Primary/foreign keys | Unique constraints | Important indexes |
|---|---|---|---|---|
| `command_templates` | Registered command shapes | `id` (PK), `command_id` (unique) | `uq_command_templates_command_id`, `uq_command_templates_id` | `ix_command_templates_command_id` |
| `command_authorization_audits` | Every policy decision | `id` (PK), FK to `runs.id` | `uq_cmd_auth_audit_run_idempotency` | — |
| `command_executions` | Execution lifecycle | `id` (PK), FK to `migration_runs.id`, FK to `migration_stages.id` | `uq_command_executions_run_idempotency` | `ix_command_executions_run_id`, `ix_command_executions_idempotency_key` |
| `command_log_chunks` | Ordered output chunks | `id` (PK), FK to `command_executions.id` | — | `ix_command_log_chunks_run_execution` |
| `worker_leases` | Worker ownership | `id` (PK), FK to `migration_runs.id` | — | `ix_worker_leases_run_owner`, `ix_worker_leases_expires_at` |

## 9. Events and State Transitions

| Event | Trigger | Payload | Persisted state transition |
|---|---|---|---|
| `COMMAND_QUEUED` | Execution record created | `execution_id, command_id, executable` | → PENDING |
| `COMMAND_STARTED` | subprocess.Popen | `execution_id, command_id` | PENDING → RUNNING |
| `COMMAND_SUCCEEDED` | exit code 0 | `execution_id, exit_code, status` | RUNNING → SUCCEEDED |
| `COMMAND_FAILED` | non-zero exit | `execution_id, exit_code, status, error` | RUNNING → FAILED |
| `COMMAND_OUTPUT_AVAILABLE` | Per log chunk | `execution_id, stream, sequence, text` | No state change |
| `RUN_CANCEL_REQUESTED` | Cancel action | `execution_id, actor` | RUNNING → CANCELLING (run-level) |
| `COMMAND_CANCELLED` | Cancel processed | `execution_id, actor` | RUNNING → CANCELLED |

State authority: `CommandExecutionModel.status` is authoritative. The `WorkerSupervisor` controls the actual process lifecycle. The `cancel_event` (threading.Event) bridges `request_cancel()` to the supervisor's poll loop. Stale-state detection: idempotency key collisions and state version checks prevent duplicate/conflicting operations.

## 10. Security and Integrity Controls

- **Path confinement**: Working directory resolved relative to sandbox root (`/tmp/amfa-sandbox`) via alias
- **Environment filtering**: `_build_safe_environment()` strips variables matching `TOKEN`, `SECRET`, `KEY`, `PASSWORD`, `CREDENTIAL`, `HERMES_`, `API_KEY`, `ACCESS_KEY`, `PRIVATE_KEY`
- **Checksum binding**: `runtime_checksum` stored as `sha256:<hex>` on execution completion
- **Actor validation**: `requested_by` / `actor` fields tracked on all mutations
- **Human approval**: Not required in G01; approval gates are introduced in G06+
- **Stale decision prevention**: Idempotency key + payload identity verification; `state_version` on all models
- **Replay prevention**: Duplicate idempotency key with different payload returns `IDEMPOTENCY_KEY_CONFLICT`
- **Secret sanitization**: No execution DTO includes credential fields; backend env vars stripped from subprocess
- **Forbidden actions**: Shell execution is structurally forbidden (`shell=False` hardcoded, no shell field in DTOs)
- **Fail-closed behavior**: Policy engine rejects by default; template lookup failure returns `command_id not registered`

## 11. Automated Tests

### G01-specific test file: `backend/tests/test_command_executor_services.py`

| Test file | Coverage | Test count | Result |
|---|---|---|---|
| `backend/tests/test_command_executor_services.py` | CommandLogService, JobSupervisorService, CommandExecutorService queue_command, cancellation | 26 | PASS |

### Tests by category

**CommandLogService** (7 tests):
- `test_append_chunk_creates_ordered_sequence` — chunks get sequential sequence numbers per execution
- `test_get_logs_returns_ordered_chunks` — retrieval preserves order
- `test_get_logs_stream_filter` — filtering by stdout/stderr works
- `test_get_logs_with_offset_and_limit` — pagination works
- `test_get_logs_with_cursor` — cursor=2 returns chunks with sequence > 2
- `test_get_stream_summary` — returns per-stream counts
- `test_chunk_emits_event` — appending chunk emits `COMMAND_OUTPUT_AVAILABLE`

**JobSupervisorService** (7 tests):
- `test_acquire_lease_creates_new_lease` — lease creation with all fields
- `test_acquire_lease_rejects_duplicate` — duplicate lease for same run raises error
- `test_renew_lease_extends_expiry` — renew increases expires_at
- `test_cancel_command_updates_execution` — cancel sets cancelled=True, cancel_requested_by
- `test_get_active_command_returns_running` — find RUNNING command
- `test_get_active_command_returns_none_when_none_running` — no active command
- `test_cancel_idempotent_replay` — same cancel key returns idempotent_replay=True

**CommandExecutorService.queue_command()** (10 tests):
- `test_successful_execution` — full lifecycle with authorization_id, runtime_checksum, events
- `test_idempotent_replay_returns_cached_result` — same key+payload returns cached
- `test_conflicting_replay_raises_error` — same key+different payload raises CONFLICT
- `test_policy_rejection_raises_error` — mock rejection raises POLICY_REJECTED
- `test_successful_execution_sets_authorization_id` — persisted authz_id matches policy
- `test_successful_execution_sets_runtime_checksum` — sha256:... format verification
- `test_timeout_sets_timed_out_status` — TIMED_OUT status from supervisor
- `test_cancelled_sets_cancelled_status` — CANCELLED status from supervisor
- `test_workflow_events_emitted` — QUEUED, STARTED, SUCCEEDED events present
- `test_stale_state_error_mapping` — execution stored with correct fields

**Cancellation verification** (2 tests):
- `test_request_cancel_sets_cancel_event` — request_cancel sets cancel_event and updates DB
- `test_cancel_event_detected_by_supervisor` — mock supervisor polling detects set event

### G01-related test file: `backend/tests/test_command_registry_service.py`

| Test file | Test count | Result |
|---|---|---|
| `backend/tests/test_command_registry_service.py` | 22 | PASS |

Tests cover template CRUD, policy engine acceptance/rejection for all 8 checks, timeout validation, network profile allowlisting, cancellation policy support, and npm-ci bootstrap template behavior.

### Run commands

```bash
# Run all G01 test files
cd /home/ubuntu/amfa-worktrees/01-command-runtime
PYTHONPATH="$PWD:$PWD/backend" python3 -m pytest backend/tests/test_command_executor_services.py -v
PYTHONPATH="$PWD:$PWD/backend" python3 -m pytest backend/tests/test_command_registry_service.py -v
```

## 12. Manual Validation Summary

See `MANUAL_TEST_GUIDE.md` for complete operator guide.

Manual execution scenarios defined in `goals/01-command-runtime/manual-tests/`:
- MT-001 — S3-F01 Authoritative scenario (template inspection, policy validation)
- MT-002 — S3-F02 Authoritative scenario (command execution, evidence)
- MT-003 — S3-F03 Authoritative scenario (live logs, reconnect)
- MT-004 — S3-F04 Authoritative scenario (cancellation, leases)
- MT-900 — Integrated happy path
- MT-910 — Stale-state, idempotency, restart
- MT-920 — Security, accessibility, observability

Manual validation status: `PENDING` — requires running backend on port 8301 with real Angular fixtures.

## 13. Evidence

| Evidence file | Contents |
|---|---|
| `evidence/completion.json` | Goal completion status with SHA, levels, limitations |
| `evidence/current-state-gap-map.json` | 16 acceptance criteria mapped to PRESENT/PARTIAL status |
| `evidence/dependency-status.json` | Sprint 2 dependencies and consumed/provided contracts |
| `evidence/shared-file-changes.json` | Shared database and code changes |
| `evidence/architecture-audit-report.md` | Architecture, contract, and security audit |
| `evidence/task-results/` | Per-task completion evidence (20 task files) |

## 14. Known Limitations

### Branch-owned
1. Live log streaming uses synchronous chunk append with offset/limit/cursor retrieval — not true async SSE push. The cursor parameter supports reconnect recovery but the streaming endpoint does not use Server-Sent Events protocol.
2. Cancellation uses `threading.Event` + `WorkerSupervisor.terminate_process_tree()` — no dedicated async supervisor thread for hard-kill on stale leases.
3. `CommandExecutorService.queue_command()` tests use mocked policy engine and supervisor — true integration tests requiring full backend stack are deferred to cross-goal validation.

### External dependencies
4. Cross-goal integration tests require G02–G05 branches merged.
5. Full Angular fixture acceptance requires Goal 10 integration harness.

### Future improvements
6. Add SSE `Last-Event-ID` support to log streaming for browser-native reconnect.
7. Add async supervisor thread for lease expiry enforcement (terminate orphan processes).

## 15. Integration Contract

### Upstream goal dependencies
- S2-F07 (Planning Review) — consumed via frozen `approved_stage_plan.schema.json`

### Downstream consumers
- G02 (Stage Workspace) — consumes `command_execution_record.schema.json`
- G03 (Angular Transformation) — consumes `command_authorization.schema.json`

### Frozen schemas consumed
- `approved_stage_plan.schema.json` (Sprint 2)
- `artifact_ref.schema.json` (cross-goal)
- `durable_event_envelope.schema.json` (cross-goal)

### Frozen schemas produced
- `command_authorization.schema.json` (G01-owned)
- `command_execution_record.schema.json` (G01-owned)
- `worker_lease.schema.json` (G01-owned)
- `command_log_event.schema.json` (G01-owned)

### Expected integration order
G01 → G02 → G03 → G04 → G05 → G06 → G07 → G08 → G09 → G10

### Shared-file changes
- `backend/app/repositories/models/workflow.py` — added `authorization_id` column
- `backend/alembic/versions/20260719_09_add_authorization_id.py` — new migration
- `backend/app/services/command_registry_service.py` — fixed import path for `planning_models`

## 16. Operational Notes

### Environment variables
- `PYTHONPATH` must include `$PWD/backend:` for module resolution
- No specific runtime env vars required for command execution (environment is sanitized before subprocess)

### Runtime directories
- Worktree: `/home/ubuntu/amfa-worktrees/01-command-runtime`
- External runtime: `/home/ubuntu/amfa-runtime/01-command-runtime`
- Backend port: 8301
- Frontend port: 3301

### Requirements
- Python 3.11+
- Dependencies in `.venv/` (FastAPI, SQLAlchemy, Alembic, Pydantic, pytest)

### Startup
```bash
cd /home/ubuntu/amfa-worktrees/01-command-runtime
source .venv/bin/activate
export PYTHONPATH="$PWD:$PWD/backend"
python3 -m uvicorn app.main:app --port 8301 --reload
```

### Tests
```bash
PYTHONPATH="$PWD:$PWD/backend" python3 -m pytest backend/tests/test_command_executor_services.py -v
PYTHONPATH="$PWD:$PWD/backend" python3 -m pytest backend/tests/test_command_registry_service.py -v
```

### Cleanup
```bash
rm -rf /home/ubuntu/amfa-runtime/01-command-runtime/database/
rm -rf /home/ubuntu/amfa-runtime/01-command-runtime/artifacts/
```

## 17. Final Verified Status

| Field | Value |
|---|---|
| `branch_ready` | true |
| `harness_ready` | false |
| `integration_verified` | false |
| `jira_complete` | false |
| Reviewer verdict | PENDING (Phase 4 fixes applied, re-review pending) |
| Final commit SHA | `3f5450b` |
| Push status | PENDING |
