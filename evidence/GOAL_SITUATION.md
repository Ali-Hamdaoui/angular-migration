# G01 — Governed Command Runtime: Current Situation

## 1. Goal Identity

| Field | Value |
|---|---|
| Goal ID | G01 |
| Goal name | Governed Command Runtime |
| Sprint | Sprint 3 (features S3-F01..S3-F04) |
| Worktree | `/home/ubuntu/amfa-worktrees/01-command-runtime` |
| Branch | `hermes/01-command-runtime` |
| Base SHA | `d759861290c1e76e26c4f2b27bbee9a77a12f0b5` |
| Current HEAD SHA | `7c8264e309a92b1cc9b4e9cc36d882090e0db8c5` |
| Remote branch | `origin/hermes/01-command-runtime` (present, matches HEAD) |
| Last audited date | 2026-07-20 |

## 2. Executive Situation

G01 is the sole governed external-process execution path for the Angular 18→21 control tower. The backend is substantially implemented and unit-tested: a command registry + policy engine, `CommandExecutorService`, `CommandLogService`, and `JobSupervisorService` exist, with 12 API endpoints wired and all required events emitted. However the branch is **not ready to merge/push as complete**. Concrete runtime defects exist: (a) `GET /runs/{id}/commands` returns 500 because the route calls `executor.list_command_executions(...)` while the service method is `get_list_command_executions`; (b) `JobSupervisorService.acquire_lease` has no callers so worker leases are never created; (c) the cancellation path cannot terminate a live OS process and `RUN_CANCELLED` is never emitted; (d) the frontend execute/log/cancel surfaces (AMFA-160/164/168) are absent; (e) manual runtime validation was never executed; (f) `completion.json`/audit/task-results are stale relative to HEAD `7c8264e` and contain false claims (notably a non-existent `IMPORTANT.md`). Biggest current risk: S3-F04 cancellation is non-functional at runtime and would fail the first real integration/manual test despite synthetic "cancellation proof" tests.

## 3. Goal Objective

- **Business:** Provide the only sanctioned path to run external commands (npm/ng build steps) for the migration, replacing arbitrary shell with a registered, policy-validated, evidence-bound runtime with durable events and live logs.
- **Technical:** FastAPI/SQLAlchemy backend; Next.js projection. Sits between upstream S2-F07 (approved stage plan membership) and all downstream G02–G10 capabilities that consume command execution.
- **Upstream inputs:** S2-F07 approved `StageExecutionPlanModel` (AMFA-140 Task 1 now rejects when authoritative plan data is absent or mismatched).
- **Downstream outputs:** `command_authorization`, `command_execution_record`, `command_log_event`, `worker_lease` frozen schemas; command events surfaced via the generic run SSE (`backend/app/api/routes/runs.py`).

## 4. Related Jira Features

| Sprint | Feature | Jira ID | Expected capability | Current status |
|---|---|---|---|---|
| S3 | Register structured commands & reject arbitrary shell | AMFA-140 | Registry + policy engine + `/operator/command-templates` + `/operator/command-policy/validate` + authz events + audit records | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| S3 | Execute one approved command + authoritative evidence | AMFA-141 | `queue_command`, `/runs/{id}/commands`, COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED, artifact/checksum persistence | PARTIALLY_IMPLEMENTED |
| S3 | Stream live logs + reconnect | AMFA-142 | `CommandLogService`, `/commands/{id}/logs`, SSE stream w/ cursor, COMMAND_OUTPUT_AVAILABLE | PARTIALLY_IMPLEMENTED |
| S3 | JobSupervisor leases/timeout/cancel | AMFA-143 | `JobSupervisorService`, `/cancel`, `/active-command`, `/active-lease`, RUN_CANCEL_REQUESTED/COMMAND_CANCELLED | PARTIALLY_IMPLEMENTED |

## 5. Related Jira Tasks and Subtasks

| Jira ID | Parent feature | Task description | Expected deliverable | Actual implementation | Status |
|---|---|---|---|---|---|
| AMFA-154 | AMFA-140 | S3-F01-I01 backend domain | Registry + policy engine domain | `backend/app/domain/command.py` (`CommandTemplate`, `DEFAULT_COMMAND_TEMPLATES`); `backend/app/services/command_registry_service.py` (`CommandRegistryService`, `CommandPolicyEngineService.validate`) | IMPLEMENTED_NOT_RUNTIME_VERIFIED; fail-closed Task 1 covered by focused tests |
| AMFA-155 | AMFA-140 | S3-F01-I02 db/api/events/artifacts | Templates/audit models, API, events | `backend/app/api/routes/commands.py`; `CommandTemplateModel`, `CommandAuthorizationAuditModel`; migration `20260719_07`; COMMAND_AUTHORIZATION_ACCEPTED/REJECTED | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-156 | AMFA-140 | S3-F01-I03 frontend | Policy inspector UI | `frontend/src/components/CommandPolicyInspector.tsx` (wired `AuthoritativeRunDashboard.tsx:69`); `frontend/src/api/commands.ts` | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-157 | AMFA-140 | S3-F01-I04 tests/security/docs | Tests + docs | `backend/tests/test_command_registry_service.py` (22 tests); `docs/capabilities/01-command-runtime/`; `docs/adr/0003-structured-command-authority.md` | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-158 | AMFA-141 | S3-F02-I01 backend domain | Command executor service | `CommandExecutorService.queue_authorized_command`/`dispatch_execution` rehydrate accepted authorization, profile, run-owned workspace, and execute through `ExecutionWorker` in a process-owned worker; execution attribution is now derived from the authenticated run actor | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-159 | AMFA-141 | S3-F02-I02 db/api/events/artifacts | Execute API + events | `backend/app/api/routes/run_commands.py` accepts authenticated actor context, authorizes every run-scoped command execution/retrieval route, accepts authorization ID + expected state version, returns 202, dispatches after commit, and uses the correct list method; legacy baseline retrieval delegates S3-F02 records to the authoritative response | IMPLEMENTED_AND_API_VERIFIED |
| AMFA-160 | AMFA-141 | S3-F02-I03 frontend | Command detail drawer | `commands.ts` exposes typed execute/list/get/artifact-metadata calls; `CommandExecutionPanel` renders authoritative executable, exact argv, working directory, timestamps, exit status, lifecycle details, artifact type/path/checksum metadata, and artifact links with loading/error states. | IMPLEMENTED_AND_VERIFIED |
| AMFA-161 | AMFA-141 | S3-F02-I04 tests/security/docs | Tests + docs | `backend/tests/test_command_executor_services.py` (queue/idempotency/cancel); `backend/tests/test_command_route_authorization.py` (owner, missing-run, spoofed actor, cross-actor retrieval negatives); `backend/tests/test_s3_f02_api_integration.py` (real API, subprocess worker, SQLite persistence, events, immutable artifacts, failure, stale state, authorization, replay) | IMPLEMENTED_AND_API_VERIFIED |
| AMFA-162 | AMFA-142 | S3-F03-I01 backend domain | Log streaming service | `backend/app/services/command_log_service.py:CommandLogService` (append_chunk/get_logs/get_stream_summary); COMMAND_OUTPUT_AVAILABLE | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-163 | AMFA-142 | S3-F03-I02 db/api/events/artifacts | Log API + migration | `backend/app/api/routes/run_commands.py` (run-scoped logs/summary, standard-ID SSE replay, Last-Event-ID precedence, heartbeat, completion); `CommandLogChunkModel`; migrations `20260719_08`, `20260720_14` | IMPLEMENTED_NOT_RUNTIME_VERIFIED; focused pytest blocked by missing SQLAlchemy |
| AMFA-164 | AMFA-142 | S3-F03-I03 frontend | Live log viewer w/ reconnect | `frontend/src/components/LogViewer.tsx` exists but only consumed by `ArtifactPreviewPanel` (mismatched `content` prop); not wired to command log SSE/API | PARTIALLY_IMPLEMENTED |
| AMFA-165 | AMFA-142 | S3-F03-I04 tests/security/docs | Tests | `test_command_executor_services.py` (logs/stream/summary/append) | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-166 | AMFA-143 | S3-F04-I01 backend domain | JobSupervisor + leases | `backend/app/services/job_supervisor_service.py:JobSupervisorService` — **`acquire_lease` has zero callers; leases never created; `get_active_lease` always None** | PARTIALLY_IMPLEMENTED |
| AMFA-167 | AMFA-143 | S3-F04-I02 db/api/events/artifacts | Cancel/active API + events | `run_commands.py` cancel/get_active_command/get_active_lease; RUN_CANCEL_REQUESTED/COMMAND_CANCELLED — **cancel HTTP builds a new `CommandExecutorService`, so live process is never terminated; RUN_CANCELLED not emitted** | PARTIALLY_IMPLEMENTED |
| AMFA-168 | AMFA-143 | S3-F04-I03 frontend | Cancel action UI | No cancel UI component; `commands.ts` lacks cancel client (only `CancelCommandRequestDto` type present) | PARTIALLY_IMPLEMENTED |
| AMFA-169 | AMFA-143 | S3-F04-I04 tests/security/docs | Tests | `test_command_executor_services.py` (cancel/replay) — inject `_cancel_events` manually, no live-process kill proof | IMPLEMENTED_NOT_RUNTIME_VERIFIED |

Closeout tasks (from `evidence/task-results/`):
- C90 (capability-contract integration tests): BLOCKED_BY_EXTERNAL_DEPENDENCY (needs G02–G05).
- C91 (independent manual runtime validation): BLOCKED_BY_EXTERNAL_DEPENDENCY (PENDING, not executed).
- C92 (as-built docs): IMPLEMENTED_AND_VERIFIED (docs present; caveat: references a stale gap map).
- C93 (final audits/completion/push): IMPLEMENTED_NOT_RUNTIME_VERIFIED (push done but evidence stale).

## 6. Acceptance Criteria Status

| Acceptance criterion | Expected behavior | Current evidence | Status | Gap |
|---|---|---|---|---|
| S3-F01 register + COMMAND_AUTHORIZATION_* | Authz persisted + events + UI | `command_registry_service.py:291` emits; `commands.py:70` validates | Verified (backend) | Frontend only inspector, not full run |
| S3-F01 invalid input | Stable error | policy engine rejects (18 reject tests) | Verified | — |
| S3-F01 stale state (STALE_STATE_VERSION) | Reject old state version | `CommandPolicyEngineService.validate` loads `MigrationRunModel.state_version` before policy side effects | VERIFIED (backend tests) | HTTP/manual runtime validation remains pending |
| S3-F01 persistence (versioned template + authz audit) | Records with version/lineage | `CommandTemplateModel`, `CommandAuthorizationAuditModel` | Verified | — |
| S3-F01 evidence (sanitized decision artifact) | SHA-256 registered | authorization manifest is finalized through `LocalFilesystemArtifactStore`, registered in `artifact_metadata`, and referenced by audit/event | VERIFIED (backend tests) | HTTP/manual runtime validation remains pending |
| S3-F01 frontend states | Distinct UI states | CommandPolicyInspector renders | PARTIAL | only S3-F01 surface |
| S3-F01 backend failure | correlation id, legal state | error codes returned | PARTIAL | no correlation-id propagation to UI |
| S3-F01 execution authority (shell=false, reject pre-process) | Reject bypass | policy `_check_shell_enforcement` structural; `WorkerSupervisor` hard `shell=False` | PARTIAL | DTO `shell` not explicitly validated |
| S3-F02 happy path + events | Exec + persist + events + UI | `command_executor_service.py` emits; `run_commands.py:40` | Verified (backend) | no frontend execution surface |
| S3-F02 invalid input | Stable error | POLICY_REJECTED | Verified | API only 422/409, no STALE handling |
| S3-F02 stale state | STALE_STATE_VERSION | authorization-ID execute request validates run and authorization state versions | VERIFIED (backend) | HTTP/manual runtime validation remains pending |
| S3-F02 persistence (idempotency/state/checksum/artifacts) | Records present | queued execution is persisted before worker dispatch; worker updates lifecycle and artifact IDs | VERIFIED (backend) | HTTP/manual runtime validation remains pending |
| S3-F02 evidence (manifest/stdout/stderr/report) | SHA-256 registered | worker uses Sprint-0 `CommandLogWriter` and stores command/stdout/stderr artifact references | VERIFIED (backend) | HTTP/manual runtime validation remains pending |
| S3-F02 frontend behavior | States | command detail drawer plus authoritative event/reconnect/gap recovery | VERIFIED | AMFA-160 UI and event recovery tests pass; manual browser validation remains pending |
| S3-F02 execution authority | reject before process | policy engine called at queue | Verified | — |
| S3-F03 happy path + COMMAND_OUTPUT_AVAILABLE | logs + event + UI | `CommandLogService.append_chunk`; `run_commands.py:138/185` | Verified (backend) | no command-log frontend |
| S3-F03 invalid input | stable error | empty on bad id | PARTIAL | — |
| S3-F03 stale state | STALE_STATE_VERSION | read-only | NOT_APPLICABLE | — |
| S3-F03 persistence (event metadata) | `command_log_chunks` | `CommandLogChunkModel` + migration 08 | Verified | — |
| S3-F03 evidence (immutable logs) | SHA-256 | chunks in DB; no artifact SHA | PARTIAL | not finalized as artifact |
| S3-F03 frontend behavior | reconnect states | LogViewer not wired to command stream | MISSING | AMFA-164 unimplemented |
| S3-F04 happy path + RUN_CANCEL_REQUESTED | cancel + events + UI | `cancel_command` emits RUN_CANCEL_REQUESTED; `request_cancel` sets cancel_event | Verified (backend) | COMMAND_CANCELLED emitted before termination; no frontend |
| S3-F04 invalid input | stable error | JobSupervisorError | Verified | — |
| S3-F04 stale state | STALE_STATE_VERSION | not implemented | MISSING | — |
| S3-F04 persistence (leases, cancel, states) | records | WorkerLeaseModel, cancel cols | Verified | lease never acquired |
| S3-F04 evidence (termination report, summary) | SHA-256 | not produced | MISSING | no cancellation summary artifact |
| S3-F04 frontend behavior | cancel states | no cancel UI | MISSING | AMFA-168 unimplemented |
| S3-F04 execution authority | reject bypass | cancel_event wired | Verified | live process not terminated |

## 7. Actual Backend Implementation

| File | Symbols | Responsibility | Jira task | Verification |
|---|---|---|---|---|
| `backend/app/domain/command.py` | `CommandTemplate`, `CommandPolicyEngine` dataclasses, `DEFAULT_COMMAND_TEMPLATES` (6) | Registry/policy domain | AMFA-154 | Unit tests |
| `backend/app/services/command_registry_service.py` | `CommandRegistryService`, `CommandPolicyEngineService.validate` | Template CRUD/seed + 8 policy checks + audit+event persistence | AMFA-154/155 | 22 tests |
| `backend/app/api/routes/commands.py` | list/get template, validate_command_policy | S3-F01 API | AMFA-155 | registered router.py:56; no HTTP test |
| `backend/app/services/command_executor_service.py` | `queue_authorized_command`/`dispatch_execution`/`_run_execution` | S3-F02 orchestration | AMFA-158/159 | focused worker/service tests pass; HTTP/manual runtime validation pending |
| `backend/app/api/routes/run_commands.py` | queue/get/list/logs/summary/stream(SSE)/cancel/active | S3-F02/03/04 API | AMFA-159/163/167 | registered; queue is 202 authorization-bound; list method corrected |
| `backend/app/services/command_log_service.py` | `CommandLogService` | S3-F03 log store + event | AMFA-162/163 | tests present |
| `backend/app/services/job_supervisor_service.py` | `JobSupervisorService` | S3-F04 leases + cancel | AMFA-166/167 | tests present; acquire_lease unused |
| `backend/app/command_execution/worker.py` | `WorkerSupervisor.run`, `CommandLogWriter`, `CommandRegistry`, `ExecutionWorker` | Sole `subprocess.Popen` authority (Sprint 0 reuse) | upstream | tests present |

## 8. Actual Frontend Implementation

| File | Component/API/type | Responsibility | Jira task | Wired into UI |
|---|---|---|---|---|
| `frontend/src/components/CommandPolicyInspector.tsx` | Component | S3-F01 template list + policy validate | AMFA-156 | YES |
| `frontend/src/api/commands.ts` | API client | list/get template + validate policy | AMFA-156 | YES |
| `frontend/src/types/generated/api.ts:39-46` | DTO types | command templates/policy/execute/cancel/log types | AMFA-156/160/164/168 | PARTIAL (execute/cancel types unused) |
| `frontend/src/components/LogViewer.tsx` | Component | generic text log viewer w/ SSE + cursor | AMFA-164 | PARTIAL-NO (only ArtifactPreviewPanel; not command stream) |
| `frontend/src/hooks/useAuthoritativeRun.ts` | SSE hook | projects command events via run SSE with duplicate, late-event, gap, and reconnect recovery | events | YES |
| (missing) command execute drawer | — | S3-F02 detail drawer | AMFA-160 | NO |
| (missing) cancel UI | — | S3-F04 cancel action | AMFA-168 | NO |

## 9. API and Event Coverage

### APIs

| Method | Path | Purpose | Jira task | Implemented | Tested |
|---|---|---|---|---|---|
| GET | `/api/v1/operator/command-templates` | List templates | AMFA-155 | Yes | Service tests |
| GET | `/api/v1/operator/command-templates/{id}` | Get template | AMFA-155 | Yes | Service tests |
| POST | `/api/v1/operator/command-policy/validate` | Policy validate + audit + event | AMFA-154/155 | Yes | Service tests |
| POST | `/api/v1/runs/{id}/commands` | Queue+execute command | AMFA-159 | Yes | Service tests |
| GET | `/api/v1/runs/{id}/commands/{eid}` | Get execution | AMFA-159 | Yes | Service tests |
| GET | `/api/v1/runs/{id}/commands` | List executions | AMFA-159 | Yes | Real API integration test |
| GET | `/api/v1/runs/{id}/commands/{eid}/logs` | Get log chunks | AMFA-163 | Yes | Service tests |
| GET | `/api/v1/runs/{id}/commands/{eid}/logs/summary` | Stream summary | AMFA-163 | Yes | Service tests |
| GET | `/api/v1/runs/{id}/commands/{eid}/logs/stream` | SSE log stream (sequence ID/cursor/Last-Event-ID) | AMFA-163 | Yes | Focused test added; runtime suite blocked by missing SQLAlchemy |
| POST | `/api/v1/runs/{id}/commands/{eid}/cancel` | Cancel command | AMFA-167 | Yes (cannot kill process) | Service tests |
| GET | `/api/v1/runs/{id}/active-command` | Active command | AMFA-167 | Yes | Service tests |
| GET | `/api/v1/runs/{id}/active-lease` | Active lease | AMFA-167 | Yes (always None) | Service tests |

### Events

| Event | Trigger | Jira task | Emitted | Payload verified |
|---|---|---|---|---|
| COMMAND_AUTHORIZATION_ACCEPTED/REJECTED | policy validate | AMFA-155 | Yes | Yes |
| COMMAND_QUEUED | queue_command after record | AMFA-159 | Yes | Yes |
| COMMAND_STARTED | status→RUNNING | AMFA-159 | Yes | Yes |
| COMMAND_SUCCEEDED/FAILED/INTERRUPTED | completion | AMFA-159 | Yes | Yes |
| COMMAND_OUTPUT_AVAILABLE | log append_chunk | AMFA-163 | Yes | Yes |
| RUN_CANCEL_REQUESTED | cancel_command | AMFA-167 | Yes | Yes |
| COMMAND_CANCELLED | cancel_command | AMFA-167 | Yes (before process terminated) | Yes |
| COMMAND_INTERRUPTED | timeout/cancel mapping | AMFA-159/167 | Yes | Yes |

## 10. Persistence and Migration Status

| Table/model | Migration | Purpose | Jira task | Status |
|---|---|---|---|---|
| `command_templates` | `20260719_07_command_templates_and_authorization.py` (rev 07, down 06) | Registry | AMFA-155 | Present |
| `command_authorization_audits` | `20260720_10_authorization_integrity.py` (rev 10, down 09) | Authz audit, authoritative version, payload hash, lineage, and artifact references | AMFA-155 / AMFA-140 Task 2 | Present |
| `command_log_chunks` | `20260719_08_command_log_chunks.py` (rev 08, down 07) | Log chunks | AMFA-163 | Present |
| `command_executions.authorization_id` | `20260719_09_add_authorization_id.py` (rev 09, down 08) | link exec→authz | AMFA-159 | Present (head) |
| `command_executions`, `worker_leases` | Sprint 0 (`initial_workflow_state`, `execution_supervision`) | exec + leases | AMFA-166/167 | Present |

- Alembic chain linear `…06 → 07 → 08 → 09`; **current head = `20260719_09`**. No conflicts/divergent heads.
- Indexes: `uq_command_templates_command_id`, `uq_cmd_auth_audit_run_idempotency`, `ix_cmd_log_chunks_exec_seq`, `uq_command_executions_run_idempotency`, `ix_worker_leases_run_owner`. Idempotency persistence present.
- Authorization audit now persists the authoritative run version, expected version, canonical request hash, correlation ID, binding identifiers, and artifact reference.
- `runtime_checksum` (sha256) computed — satisfies `command_execution_record.schema.json`.
- Note: C93.json falsely states "Alembic current at 20260719_08" — head is actually 09.

## 11. Automated Test Situation

| Test file | Scope | Collected tests | Passing | Failing | Jira coverage |
|---|---|---|---|---|---|
| `backend/tests/test_command_registry_service.py` | registry + policy engine, stale state, idempotency, artifact evidence | 41 | 41 (focused run) | 0 | AMFA-140 Task 2 / AMFA-154/155/157 |
| `backend/tests/test_command_executor_services.py` | log/lease/cancel/queue/idempotency/events | 26 | 26 (ran by reviewer) | 0 | AMFA-158/161/162/165/166/169 |
| `backend/tests/test_command_execution.py` | Sprint-0 WorkerSupervisor | 14 | N/E | N/E | upstream reuse |

Executed commands:
- `cd /home/ubuntu/amfa-worktrees/01-command-runtime && python -m pytest backend/tests/test_command_executor_services.py` → **26 passed** (reviewer).
- Full backend suite could NOT be collected in this worktree: `ModuleNotFoundError: langgraph` in `test_mock_agents.py`/`test_mock_orchestrator.py` (env gap, not a branch defect; app boots fine).
- `completion.json`/C93 claim "54/54 pass" — unverifiable here; only the G01 command files (48 tests) were independently confirmed green. Counts are treated as **NOT EXECUTED DURILY THIS AUDIT** for the full suite.

## 12. Manual Test Situation

| Manual scenario | Documented | Executed | Result | Evidence |
| --------------- | ---------- | -------- | ------ | -------- |
| MT-001 S3-F01 authoritative | Yes | No | — | C91.json: "Manual runtime validation not yet executed" |
| MT-002 S3-F02 | Yes | No | — | C91 PENDING |
| MT-003 S3-F03 | Yes | No | — | C91 PENDING |
| MT-004 S3-F04 | Yes | No | — | C91 PENDING |
| MT-900 capability integrated | Yes | No | — | C90 BLOCKED (needs G02–G05) |
| MT-910 stale/idempotency/reconnect | Yes | No | — | C91 PENDING |
| MT-920 security/a11y/observability | Yes | No | — | C91 PENDING |

Manual runtime validation was **never executed** against a live backend/frontend/DB. Code inspection ≠ runtime validation.

## 13. Evidence Situation

| Evidence file | Purpose | Current | Accurate | Notes |
| ------------- | ------- | ------- | -------- | ----- |
| `evidence/completion.json` | Completion summary | head_sha `7ee7133` | STALE/INACCURATE | Actual HEAD `7c8264e`; `branch_ready:true` not supported; claims `IMPORTANT.md` created (false) |
| `evidence/current-state-gap-map.json` | Per-criterion mapping | 16 criteria PRESENT/PARTIAL | PARTIAL/STALE | under-reports LogViewer capability; omits real defects (list 500, lease never acquired, cancel can't kill) |
| `evidence/architecture-audit-report.md` | Arch/contract/security audit | at `bff54c0` | STALE | found 3 BLOCKERs + 5 CRITICAL; not regenerated after fix commits |
| `evidence/dependency-status.json` | Upstream/contracts | S2-F07 AVAILABLE | OK (soft-pass) | plan-membership soft-pass weakens guarantee |
| `evidence/shared-file-changes.json` | Shared edits | planned list | PARTIAL | several edits not evidenced as done |
| `evidence/task-results/C90..C93.json` | Closeout results | at `bff54c0` | STALE | C91 PENDING; C90 BLOCKED; C93 push pending |

## 14. Dependency Situation

### Upstream dependencies

| Goal/feature | Required capability | Current availability | Impact |
| ------------ | ------------------- | -------------------- | ------ |
| S2-F07 (Sprint 2) | Approved stage plan membership | FROZEN CONTRACT consumed; `_check_plan_membership` soft-passes when absent | Does not block compilation; weakens execution-authority guarantee |

### Downstream consumers

| Goal/feature | Capability consumed | Contract provided | Readiness |
| ------------ | ------------------- | ----------------- | --------- |
| G02–G10 | Command execution + events | `command_authorization`, `command_execution_record`, `command_log_event`, `worker_lease` schemas (present/frozen) | Contract-ready; NOT integrated (C90 BLOCKED) |

## 15. Known Issues and Gaps

| ID | Severity | Description | Jira impact | Owner | Required action |
| -- | -------- | ----------- | ----------- | ----- | --------------- |
| K1 | RESOLVED | `GET /runs/{id}/commands` called a non-existent service method | AMFA-159 | G01 | Corrected route to `get_list_command_executions`; focused suite passes |
| K2 | BLOCKER | Cancellation cannot terminate a live OS process; `RUN_CANCELLED` never emitted (new `CommandExecutorService` per request) | AMFA-167/169 | G01 | Share executor instance / terminal cancel via worker |
| K3 | CRITICAL | `acquire_lease` never called; worker leases never created; `get_active_lease` always None | AMFA-166 | G01 | Wire lease acquisition into execution flow |
| K4 | RESOLVED_FOR_S3-F02 | Execute request now requires expected state version and validates accepted authorization freshness | S3-F02 | G01 | HTTP/manual runtime validation remains pending |
| K5 | RESOLVED_FOR_S3-F02 | Worker-owned execution now uses `CommandLogWriter` and persists artifact IDs/checksum | S3-F02 | G01 | HTTP/manual runtime validation remains pending |
| K6 | RESOLVED_FOR_S3-F01 | Authorization audit now reads and persists the authoritative run state version; command execution remains separately out of scope | S3-F01 | AMFA-140 Task 2 | Covered by focused authorization tests |
| K7 | MAJOR | Frontend live-log/cancel surfaces (AMFA-164/168) remain absent; AMFA-160 execution projection is implemented but not runtime/manual verified | AMFA-141/142/143 | G01 | Complete AMFA-142/143 separately and run AMFA-141 manual/runtime validation |
| K8 | MAJOR | Manual runtime validation never executed (C91 PENDING) | all acceptance | G01 | Execute MANUAL_TEST_PLAN vs live stack |
| K9 | MINOR | Evidence stale vs HEAD `7c8264e`; false `IMPORTANT.md` claim; C93 wrong Alembic head | evidence | G01 | Regenerate evidence at current HEAD |
| K10 | MINOR | Unused `subprocess` import in `command_executor_service.py:12` | — | G01 | Remove import |
| K11 | MAJOR | Shell enforcement structural only (DTO `shell` default False, no validator); frontend `CommandPolicyValidateResponseDto` missing `cwd_alias`/`plan_id`/`execution_profile_id` | S3-F01 | G01 | Add DTO `shell` validator; sync frontend types |

## 16. Goal Completion Matrix

| Dimension                     | Status | Evidence |
| ----------------------------- | ------ | -------- |
| Backend implementation        | Partial | services + routes exist; list endpoint 500, lease unused, cancel broken |
| Frontend implementation       | Partial | only CommandPolicyInspector wired |
| API contracts                 | Partial | 12 endpoints wired; list endpoint broken |
| Persistence                   | Implemented | 3 G01 migrations (07/08/09), head 09, indexes present |
| Events                        | Implemented | all required events emitted |
| Automated tests               | Partial | 48 G01 command tests pass; full suite not collectable; no HTTP tests |
| Manual runtime tests          | Missing | C91 PENDING |
| Security controls             | Partial | shell=False structural; env sanitization; audit linked; DTO not validated |
| Documentation                 | Implemented | docs/capabilities/01-command-runtime/*, ADR-0003 |
| Evidence                      | Stale | completion.json/audit/task-results predate HEAD 7c8264e |
| Upstream integration          | Frozen-contract only | S2-F07 consumed, not integrated |
| Downstream contract readiness | Contract-ready, not integrated | C90 BLOCKED |

## 17. Jira Completion Summary

| Category                | Total | Complete | Partial | Blocked | Missing |
| ----------------------- | ----: | -------: | ------: | ------: | ------: |
| Features                |     4 |        0 |       3 |       0 |       1 |
| Implementation subtasks |    16 |        3 |      10 |       0 |       3 |
| Closeout tasks          |     4 |        1 |       1 |       2 |       0 |
| Acceptance criteria     |    32 |       14 |      10 |       0 |       8 |

(Feature AMFA-140 counted Partial=implemented-not-runtime-verified; AMFA-141/142/143 Partial; none Complete. Subtask "Missing" = AMFA-160/164/168 unwired; "Partial" = AMFA-159/166/167 + 7 runtime-not-verified. Closeout: C92 Complete; C90/C91 Blocked; C93 Partial.)

## 18. Final Status

| Field                  | Value |
| ---------------------- | ----- |
| `branch_ready`         | false |
| `harness_ready`        | false |
| `integration_verified` | false |
| `jira_complete`        | false |
| Reviewer verdict       | Substantial backend scaffolding with passing unit tests, but real runtime-breaking defects (broken list endpoint, cancellation cannot kill process, leases never acquired) and stale/misleading evidence; not branch_ready |
| Pushed                 | true |
| Remote SHA             | `7c8264e309a92b1cc9b4e9cc36d882090e0db8c5` |

## 19. Recommended Next Actions

1. G01 / AMFA-159 — fix `list_command_executions` method-name mismatch in `run_commands.py`; validate via HTTP test.
2. G01 / AMFA-167 — make cancel terminate the live process (shared executor or worker signal); emit `RUN_CANCELLED` after confirmed termination.
3. G01 / AMFA-166 — call `acquire_lease` in execution flow so worker leases exist.
4. G01 / AMFA-160/164/168 — implement or explicitly mark frontend execute/log/cancel surfaces incomplete.
5. G01 / all — execute MANUAL_TEST_PLAN (C91) against live stack; regenerate completion.json/audit at HEAD `7c8264e`.
6. G01 / AMFA-141/142 — wire stdout/stderr artifact persistence and command-log frontend.

## 20. Audit Sources

- Git: `git log`, `git status`, `git rev-parse HEAD`, `git branch --show-current` (worktree `01-command-runtime`)
- Root: `AGENT.md`, `README.md`
- Goal: `goals/01-command-runtime/{GOAL,TASK_INDEX,JIRA,ACCEPTANCE,CURRENT_CODE_MAP,CROSS_GOAL_CONTRACTS,OWNERSHIP,REFERENCES}.md`, `MANUAL_TEST_PLAN.md`, `manual-tests/MT-*`
- Backend: `domain/command.py`, `services/command_registry_service.py`, `services/command_executor_service.py`, `services/command_log_service.py`, `services/job_supervisor_service.py`, `command_execution/worker.py`, `api/routes/commands.py`, `api/routes/run_commands.py`, `api/routes/runs.py`, `api/router.py`, `repositories/models/workflow.py`, `alembic/versions/20260719_0{7,8,9}*.py`
- Frontend: `components/CommandPolicyInspector.tsx`, `components/LogViewer.tsx`, `components/AuthoritativeRunDashboard.tsx`, `api/commands.ts`, `types/generated/api.ts`, `hooks/useAuthoritativeRun.ts`
- Tests: `backend/tests/test_command_registry_service.py`, `test_command_executor_services.py`, `test_command_execution.py`
- Evidence: `completion.json`, `current-state-gap-map.json`, `dependency-status.json`, `shared-file-changes.json`, `architecture-audit-report.md`, `task-results/C90..C93.json`
- Contracts: `goals/shared/contracts/{command_authorization,command_execution_record,worker_lease,command_log_event,goal_completion}.schema.json`
- Docs: `docs/capabilities/01-command-runtime/*`, `docs/adr/0003-structured-command-authority.md`
