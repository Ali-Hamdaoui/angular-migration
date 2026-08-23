# G01 — Governed Command Runtime

## Overview

The Governed Command Runtime implements Sprint 3 of the AMFA control tower,
providing the sole structured command path with registry and policy,
authoritative execution evidence, durable live logs, and JobSupervisor
ownership with leases, timeout, and cancellation.

## Features

| Feature | Jira | Status |
|---------|------|--------|
| S3-F01 — Register structured commands and reject arbitrary shell execution | AMFA-140 | ✅ Complete |
| S3-F02 — Execute one approved command and persist authoritative evidence | AMFA-141 | ✅ Complete |
| S3-F03 — Stream live command logs and recover after browser reconnect | AMFA-142 | ✅ Complete |
| S3-F04 — Own commands with JobSupervisor, leases, timeout, cancellation | AMFA-143 | ✅ Complete |

## Architecture

### Backend

- **Domain layer:** `backend/app/domain/command.py` — CommandTemplate, CommandPolicyRule,
  AuthorizationRequest/Result aggregates. Database-backed with 6 default templates.
- **Services:**
  - `backend/app/services/command_registry_service.py` — CommandRegistryService (CRUD),
    CommandPolicyEngineService (8 policy checks)
  - `backend/app/services/command_executor_service.py` — CommandExecutorService wraps
    Sprint 0 WorkerSupervisor with lifecycle management
  - `backend/app/services/command_log_service.py` — CommandLogService with ordered
    chunk appending and stream-filtered retrieval
  - `backend/app/services/job_supervisor_service.py` — JobSupervisorService with
    WorkerLease acquire/renew/release, command cancellation, run state transitions
- **API routes:**
  - `GET/POST /api/v1/operator/command-templates` — Template listing
  - `POST /api/v1/operator/command-policy/validate` — Policy validation
  - `POST /api/v1/runs/{id}/commands` — Command execution
  - `GET /api/v1/runs/{id}/commands/{execId}/logs` — Log retrieval
  - `POST /api/v1/runs/{id}/commands/{execId}/cancel` — Cancellation
  - `GET /api/v1/runs/{id}/active-command` — Active command status
- **Events:** COMMAND_AUTHORIZATION_ACCEPTED/REJECTED, COMMAND_QUEUED/STARTED/SUCCEEDED/FAILED,
  COMMAND_OUTPUT_AVAILABLE, RUN_CANCEL_REQUESTED, COMMAND_CANCELLED/INTERRUPTED
- **Migrations:** 2 new Alembic migrations (command_templates + authorization, log chunks)

### Frontend

- `frontend/src/api/commands.ts` — Typed API client for command endpoints
- `frontend/src/components/CommandPolicyInspector.tsx` — Template inspector with
  policy validation UI
- Integrated into `AuthoritativeRunDashboard.tsx`

### Data Model

- `command_templates` — Registered structured command shapes (id, executable, args, aliases)
- `command_authorization_audits` — Every policy decision (accepted/rejected with reasons)
- `command_executions` — Execution lifecycle (queued → running → succeeded/failed/cancelled)
- `command_log_chunks` — Ordered stdout/stderr/system chunks per execution
- `worker_leases` — Run-scoped worker ownership with heartbeats and expiry

### Default Command Templates

| Template ID | Executable | Arguments | Purpose |
|-------------|-----------|-----------|---------|
| python-version | python | --version | Check Python runtime |
| node-version | node | --version | Check Node.js runtime |
| npm-version | npm | --version | Check npm version |
| npx-version | npx | --version | Check npx version |
| git-version | git | --version | Check Git version |
| npm-ci-bootstrap | npm | ci | Clean install dependencies |

## Test Results

- **54 automated tests passing** across 3 test files
- Test scope: registry service (10), policy engine (12), executor services (13),
  Sprint 0 backward-compatibility (19)

## Security

- Shell execution is structurally forbidden (no shell field in DTO)
- Executable/argument matching is exact against registered template
- Network profiles are restricted to allowlist
- Cancellation policies are restricted to supported values
- Authorization decisions are audited with full context
- Idempotency keys prevent duplicate execution

## Operations

- Backend runs on port 8301, frontend on 3301
- SQLite database at `/home/ubuntu/amfa-runtime/01-command-runtime/database/amfa.db`
- Artifact store at `/home/ubuntu/amfa-runtime/01-command-runtime/artifacts/`

## Known Limitations

1. CommandExecutor uses Sprint 0 WorkerSupervisor with in-memory idempotency
2. Live log streaming uses synchronous append — async SSE streaming for
   bounded chunks synchronously in short transactions and exposes them through asynchronous reconnectable SSE cursor replay
3. JobSupervisor cancellation is connected to the process-owned worker: the
   API records the request, signals the live worker, and the worker terminates
   the process tree before recording terminal evidence. A separate
   deployment-level reaper for a crashed backend instance remains an
   operational hardening item.
4. Cross-goal integration requires G02-G05 branches

## Audit

- **Architecture/contract/security:** PASS — No duplicate authorities, all
  execution passes through the structured path, policy versioning enforced
- **Runtime/product/frontend:** PASS — All routes registered, API contracts
  match frozen schemas, frontend components integrated

## V2.2 governed runtime and command evidence requirements (P2-0/P2-1)

New proven plans (`transformer-plan-v2.2-proven-1`) execute only through
authority-bound commands: discovery and migration run through an absolute,
checksummed Angular CLI entrypoint under the exact governed Node/npm/npx
descriptors of an `AngularCliToolchainAuthority`; child npm must resolve to the
bound npm descriptor. The V2-V6 combined updater templates and the npx-based
migrate commands remain registered solely as legacy replay history - they are
deprecated for new proven plans and are never selected as authoritative
mutation.

Every qualification row keeps its full immutable evidence chain (authorization,
toolchain authority, lock authority selection, npm-ci/npm-ls same-authority
proof, gate order, promotion, seal). Runtime qualification is separate from
production: PRODUCTION requires promoted certified profiles and can never use
qualification authorization.
