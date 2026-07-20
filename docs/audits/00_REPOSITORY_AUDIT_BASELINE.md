# Repository Audit Baseline

This reusable baseline is a derived repository map for later, issue-scoped audits. It is not a requirements source, implementation assessment, or completion report. The previous `PASS` verdict is invalidated by the independent architectural review; this document records the corrected map and a fresh report-integrity review.

## 1. Baseline Metadata

| Identifier | Value | Evidence |
|---|---|---|
| Branch | `hermes/02-stage-workspace-bootstrap` | `git branch --show-current` |
| HEAD | `81ba08c5741afcc121d93c051f3b2715f399ced4` | `git rev-parse HEAD` |
| Upstream | `origin/hermes/02-stage-workspace-bootstrap` | upstream query |
| Ahead / behind | `0 / 0` | `git rev-list --left-right --count 'HEAD...@{u}'` output `0 0` |
| Sprint hash | `4c9a17670ce6d988bdcad48d43e805dbf9a0c53e` | `git hash-object docs/sprint.md` |
| Baseline source HEAD | `b2d18c5e033f91dd0890edeac30419ae364b8e64` | correction input |
| Worktree at preflight | `?? docs/audits/00_REPOSITORY_AUDIT_BASELINE.md` | `git status --porcelain=v1 -uall` |
| Root instruction authority | `AGENTS.md` only | `git ls-files AGENT.md AGENTS.md` output `AGENTS.md` |

Mandatory preflight commands all exited `0`. Exact observed output, with command labels, was:

```text
git branch --show-current
hermes/02-stage-workspace-bootstrap
git status --porcelain=v1 -uall
?? docs/audits/00_REPOSITORY_AUDIT_BASELINE.md
git rev-parse HEAD
81ba08c5741afcc121d93c051f3b2715f399ced4
git rev-parse --abbrev-ref --symbolic-full-name '@{u}'
origin/hermes/02-stage-workspace-bootstrap
git rev-list --left-right --count 'HEAD...@{u}'
0 0
git log -1 --decorate --oneline
81ba08c (HEAD -> hermes/02-stage-workspace-bootstrap, origin/hermes/02-stage-workspace-bootstrap) docs: standardize AGENTS instructions and add sprint scope snapshot
git hash-object docs/sprint.md
4c9a17670ce6d988bdcad48d43e805dbf9a0c53e
git ls-files AGENT.md AGENTS.md
AGENTS.md
```

The only pre-existing untracked path was the report itself. No staged, modified, or deleted paths were present. `AGENT.md` is not tracked, `AGENTS.md` is tracked, and no more-specific `AGENTS.md` was found under inspected paths. `AGENTS.md` was read completely before inspection; `AGENT.md` was not read.

## 2. Scope and Non-Completion Disclaimer

This correction changes only this report. It does not assess completion of AMFA-144, AMFA-145, AMFA-170, AMFA-171, AMFA-172, AMFA-173, AMFA-174, AMFA-175, AMFA-176, or AMFA-177, and it does not audit AMFA-110 or AMFA-143 for completion. Existing names, tests, records, endpoints, commits, evidence, and statuses are navigation evidence only, never proof of requirement completion.

## 3. Source Precedence

The authority order is: `docs/sprint.md` for the functional requirements snapshot; `AGENTS.md` for operating rules; actual code, migrations, APIs, events, persistence, evidence, frontend state, and tests for implementation reality; this baseline as a derived map; and other implementation documentation as supporting context. The baseline never replaces `docs/sprint.md` as the requirements source of truth. The sprint source-of-truth rule is at `docs/sprint.md:14-28`; its non-interpretation rule is at `docs/sprint.md:606-632`.

## 4. Repository Instructions Read

- Complete root instruction file read: `AGENTS.md:1-410`.
- `git ls-files AGENT.md AGENTS.md` proved that `AGENTS.md` is the sole tracked root authority. `AGENT.md` is neither tracked nor present in the reported worktree state and was not read.
- No more-specific `AGENTS.md` exists in the repository file list.
- Complete sprint snapshot read once: `docs/sprint.md:1-632`.
- Global sections read: `Document Metadata` (`docs/sprint.md:3-12`), `Source-of-truth rule` (`docs/sprint.md:14-28`), `Delivery Dependency Order` (`docs/sprint.md:577-602`), and `Non-Interpretation Rule` (`docs/sprint.md:606-632`).
- Architecture and implementation paths re-inspected only for this correction include planning, G06, stage preparation, G07, command execution, state transitions, persistence, APIs, artifacts, frontend scripts, and validation scripts.

## 5. Technology and Build Map

| Area | Observed implementation | Evidence |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Alembic | `backend/pyproject.toml`, `backend/app/main.py`, `backend/alembic` |
| Frontend | Next.js, React, TypeScript, Vitest | `frontend/package.json`, `frontend/src` |
| Persistence | SQLite and SQLAlchemy; Alembic migrations | `backend/app/repositories`, `backend/alembic/versions` |
| Workflow authority | Transition Service and durable workflow records | `backend/app/state/transition_service.py`, `backend/app/repositories/models/workflow.py` |
| Command boundary | Registered structured commands, shell disabled, bounded artifacts | `backend/app/command_execution/worker.py` |
| Events | Durable workflow events and SSE projection | `backend/app/domain/contracts.py`, `backend/app/events`, `frontend/src/hooks/useMigrationEvents.ts` |
| Artifacts | Local filesystem bytes plus SQLite metadata/checksums | `backend/app/artifact_store/local_store.py`, `backend/app/repositories/models/workflow.py` |

## 6. Repository Structure Map

- Domain contracts: `backend/app/domain/`, including `planning.py`, `planning_review.py`, `stage_workspace.py`, and `contracts.py`.
- Application services: `backend/app/services/`, including `planning_application_service.py`, `planning_review_application_service.py`, `planning_review_evidence_application_service.py`, `stage_preparation_service.py`, and `stage_bootstrap_service.py`.
- State and events: `backend/app/state/transition_service.py`, `backend/app/events/`, and `backend/app/repositories/models/workflow.py`.
- Planning persistence: `backend/app/repositories/planning_models.py` and `backend/app/repositories/planning_review_models.py`.
- Stage persistence: `backend/app/repositories/stage_workspace_models.py`.
- APIs: `backend/app/api/routes/plans.py`, `planning_review.py`, `stages.py`, `migrations.py`, and corresponding contract modules.
- Command and process boundary: `backend/app/command_execution/worker.py`.
- Frontend projection and clients: `frontend/src/api`, `frontend/src/hooks`, `frontend/src/components`, and generated API types.
- Validation: `scripts/`, `backend/tests/`, `frontend/src/**/__tests__`, and feature verification documents.

## 7. Authority and Ownership Map

| Concern | Authoritative or observed symbol | Persistence / projection | Boundary and uncertainty |
|---|---|---|---|
| Workflow transitions | `StateTransitionService.apply_transition` | `MigrationRunModel`, `WorkflowEventModel` | Transition Service is the observed mutation authority; orchestration is coordination. |
| Plan generation | `PlanningApplicationService.generate` and `StageExecutionPlan` | `MigrationPlanModel`, `StageExecutionPlanModel`, `ActivePlanVersionModel` | Deterministic service owns generated facts; active selection consumption must remain explicit. |
| Plan review | `PlanningReviewApplicationService`; `PlanningReviewEvidenceApplicationService` | revision, review, stale-approval, and G06 models | Reviewer records decisions; no completion conclusion is made here. |
| Stage preparation | `StagePreparationApplicationService` | `MigrationStageModel`, `StageWorkspaceModel`, `G07ApprovalModel` | Current implementation has a separate request-derived stage-plan construction path; this is an uncertainty for dependency binding. |
| Command execution | `ExecutionWorker` through `CommandPolicy` and `CommandRegistry` | `CommandExecutionModel` and artifacts | `WorkerSupervisor` owns subprocess handling; no `JobSupervisor` or `ProcessController` symbol was found. |
| Cancellation | `StateTransitionService.request_cancel` and `acknowledge_cancel`; process cancellation callback | run/command rows and workflow events | Transition Service is the durable authority; completion race semantics and API coverage remain uncertain. |
| Frontend state | `useAuthoritativeRun`, `useMigrationEvents`, `applyEventToRun` | backend snapshots/events | Projection only; clicks do not establish authoritative state. |

## 8. S2-F07 / AMFA-110 Dependency Contract Map

This is a contract map only. It does not audit AMFA-110 for completion.

| Contract | Authoritative service | Coordinator | Persistence representation | API representation | Event / evidence representation | Unresolved uncertainty |
|---|---|---|---|---|---|---|
| Immutable plan revisions | `PlanningReviewApplicationService` and `PlanningReviewEvidenceApplicationService` | planning review routes | `PlanRevisionModel` with previous/new IDs, version, diff checksum, artifacts | revision contracts and planning-review routes | revision artifacts and planning events | Whether every consumer resolves only the latest approved revision is not proven. |
| Active plan pointer | planning evidence service writes the active record | routes call application service | `ActivePlanVersionModel` with run/scope, migration plan, optional stage plan, version, state version | plan/review DTOs expose plan and stage-plan values | plan-created/revised events and artifacts | Exact read path used by stage preparation is not proven. |
| Active `StageExecutionPlan` | `PlanningApplicationService` creates the domain `StageExecutionPlan`; persistence service stores it | planning routes | `StageExecutionPlanModel.stage_plan`, `version`, `checksum` | planning contracts contain structured stage plan | stage-plan artifact and `STAGE_PLAN_CREATED` | `stage_preparation_service.py` builds a local dict from request values instead of demonstrating an active-pointer read. |
| Stage-plan selection | planning service creates first-stage plan; active pointer scopes it | LangGraph/orchestration may coordinate only | `ActivePlanVersionModel.stage_plan_id` | `StageExecutionPlan` DTO/contract | plan evidence | Later-stage exact selection and lock are not proven. |
| Plan version | deterministic planning/review services | transition calls carry state version | version columns and G06 `plan_version` | `plan_version` in review contracts | event payloads and evidence metadata | Stage workspace model stores `policy_version` as a string, not the planning version. |
| Plan checksum | checksum helpers in `planning.py` and review services | API routes | `checksum` columns and G06 bindings | `plan_checksum` fields | plan package/artifact checksums | Cross-service checksum recomputation is not demonstrated. |
| Exact source binding | `MigrationPlan` / `StageExecutionPlan` validation | planning service | JSON plan and stage-plan rows | `source_exact` and `source_family` fields | package and plan artifacts | Stage preparation source values are request-dependent. |
| Exact target binding | `StageExecutionPlan` validation | planning service | JSON stage plan | `target_exact`, `target_cli_exact` | plan artifacts | Stage preparation does not prove read-through to active plan. |
| Toolchain-profile binding | `StageExecutionPlan.execution_profile_id` and command references | planning service | JSON stage plan | planning contracts and generated API types | package/profile artifacts | Profile resolution at stage start is unresolved. |
| Approved-command binding | `CommandTemplateReference`, `CommandRegistry`, `CommandPolicy` | `ExecutionWorker` | command execution row and command log artifacts | command request/result DTOs | command events and logs | Bootstrap service currently constructs `npm ci` directly; active-plan command authorization is unresolved. |
| G06 persistence | `PlanningReviewEvidenceApplicationService` | planning-review route | `G06ApprovalModel` | `POST /api/v1/runs/{run_id}/approvals/G06/decisions` and response contracts | `G06_CREATED`, approval/rejection/modification/stale events; package artifacts | no completion assessment. |
| G06 decision state | `G06Decision`, `G06Gate`, service binding checks | route maps DTOs | status, decision, gate version, state version, checksums | `G06DecisionApiRequest` and `G06DecisionResponse` | decision event and evidence | Expiry is not represented in `G06Gate` enum; stale behavior is represented. |
| G06 staleness and invalidation | review/revision service marks stale approvals | transition/state version coordination | `PlanApprovalStaleModel`, G06 stale reason/status | stale status in contracts | `G06_STALE` and stale records | Exact invalidation on every binding change needs runtime verification. |
| Stage-start block for missing/rejected/expired/stale G06 | no single proven stage-start authority | `StagePreparationApplicationService` and stage route | G07/workspace rows, not a demonstrated G06 read | stage APIs | stage events/evidence | The inspected stage path checks G07, not a proven active G06 binding; record as dependency uncertainty. |
| Related services and repositories | planning and review application services; repository models | API routes | planning and review tables | plan/review contract modules | planning/G06 events and artifacts | No claim that these contracts satisfy AMFA-110. |

Concrete symbols: `backend/app/domain/planning.py:92-139`, `backend/app/domain/planning_review.py:21-150`, `backend/app/repositories/planning_models.py:10-109`, `backend/app/repositories/planning_review_models.py:10-123`, `backend/app/services/planning_application_service.py`, `backend/app/services/planning_review_application_service.py`, `backend/app/services/planning_review_evidence_application_service.py`, `backend/app/api/routes/planning_review.py`, `backend/app/api/routes/plans.py`, and `backend/alembic/versions/20260719_06_planning_review_evidence.py`.

## 9. S3-F04 / AMFA-143 Dependency Contract Map

AMFA-143 / S3-F04 is `Own commands with JobSupervisor, leases, timeout, and explicit cancellation`. This map does not audit AMFA-143 for completion. The repository uses the observed equivalent names below; absent names are not silently substituted.

| Contract | Existing file and symbol | Observed representation | Uncertainty / dependency for AMFA-170 and AMFA-174 |
|---|---|---|---|
| Command ownership | `backend/app/command_execution/worker.py`: `ExecutionWorker`, `CommandRegistry`, `CommandPolicy` | registered structured request, no shell, workspace/profile/network checks | AMFA-174 must consume locked-plan command references; direct bootstrap command construction is a mismatch to resolve upstream. |
| Supervisor | `worker.py`: `WorkerSupervisor.run` | subprocess ownership and output collection | `JobSupervisor` is absent; AMFA-170 and AMFA-174 must not invent a second authority without an approved upstream contract. |
| WorkerLease acquisition | `backend/app/state/transition_service.py`: `acquire_lease` | `WorkerLeaseModel` row with run, worker, owner, expiry | Lease is run-scoped in this symbol; command execution binding is not fully proven. |
| Heartbeat and renewal | `renew_lease`; migration adds `heartbeat_at` | expiry extension and heartbeat column | No periodic supervisor heartbeat symbol was found. |
| Expiry and conflict | `_has_current_lease`, `LeaseRequiredError` | expiry check blocks completion | acquisition conflict and takeover semantics are not fully expressed. |
| Timeout | `WorkerSupervisor.run`; `StructuredCommandRequest.dto.timeout_seconds` | monotonic deadline; returns timeout-style result | no distinct timeout event or durable timeout classification was found in the inspected path. |
| Process termination | `WorkerSupervisor.terminate_process_tree` | Windows taskkill / POSIX process-group fallback | `ProcessController` is absent. Graceful-versus-forced phases are implementation details in this method, not a named contract. |
| Graceful and forced termination | `terminate_process_tree` | terminate, wait, kill, wait | evidence of which phase occurred is not separately persisted. |
| Idempotent cancellation | `StateTransitionService.request_cancel` / `acknowledge_cancel`; `ExecutionWorker._find_idempotent_result` | idempotency keys and replayed command results | completion-versus-cancellation race ordering is unresolved. |
| Recovery classification | `CommandExecutionResult` and baseline/stage service fields | `cancelled`, `timed_out`, `reconstruction_required` fields exist in related models | mutation-category policy and authoritative classification for bootstrap are not proven. |
| Transition Service cancellation authority | `StateTransitionService` | durable request and acknowledgement transitions | route coverage and worker coordination are not proven. |
| Partial stdout and stderr | `CommandLogWriter.write` | bounded `stdout`/`stderr` artifacts and truncation flags | partial evidence on process interruption depends on caller finalization. |
| Process-termination evidence | command log result fields | cancellation and return code recorded | no dedicated termination artifact/event symbol was found. |
| Workspace trust/recovery | `CommandPolicy._resolve_working_directory`; stage workspace fingerprint services | approved aliases and fingerprints | recovery classification after interrupted mutation remains an upstream dependency. |
| Active-command API | stage/bootstrap status route and command DTOs | `GET /api/v1/runs/{run_id}/stages/{stage_id}/steps/bootstrap-install` | no generic active-command endpoint was found. |
| Cancellation API | `backend/app/api/routes/migrations.py` has migration cancellation; frontend `frontend/src/api/migrations.ts` | run-level cancel client | no verified command-specific cancellation route for stage bootstrap. |
| Cancellation/interrupted events | `WorkflowEventType.COMMAND_CANCELLED`, `COMMAND_INTERRUPTED` | event vocabulary exists | emission and durable ordering from the stage bootstrap path are unresolved. |

Expected dependency consumption is separated by authority. From S3-F04, AMFA-170 is expected to consume lease-conflict checks, applicable transition and cancellation authority, and existing worker/process ownership contracts where relevant. Within AMFA-144 and AMFA-170, the stage-preparation scope owns or consumes G07 construction and decision handling, dedicated workspace creation, source-safety controls, and workspace fingerprints.

AMFA-174 is expected to consume the locked stage plan, approved command references, G07 and workspace readiness, the existing command registry and policy, execution-worker ownership, artifact and event contracts, fingerprints, and applicable recovery contracts. Missing `JobSupervisor`, `ProcessController`, an explicit lease-heartbeat loop, command-active/cancellation endpoints, termination evidence, and race/recovery contracts remain dependency uncertainties or future blockers only. They are not implemented by this baseline.

### Neutral upstream compatibility and execution-profile contract

Compatibility and profile findings are upstream contracts, not AMFA-143 findings. The relevant paths are `backend/app/services/compatibility_application_service.py`, `backend/app/repositories/compatibility_models.py`, `backend/app/services/execution_profile_application_service.py`, `backend/app/repositories/execution_profiles.py`, `backend/app/api/compatibility_contracts.py`, and `backend/app/api/execution_profile_contracts.py`. The stage path must demonstrate exact profile/source/target resolution and checksum binding before AMFA-170 or AMFA-174 can safely consume it; this report records the dependency only.

## 10. Persistence and Migration Map

- Workflow tables and command/lease rows: `backend/app/repositories/models/workflow.py`.
- Planning tables and active pointer: `backend/app/repositories/planning_models.py`.
- Review, stale approval, and G06 tables: `backend/app/repositories/planning_review_models.py`.
- Stage workspace and G07 tables: `backend/app/repositories/stage_workspace_models.py`.
- Current migration head includes `20260720_01_stage_workspace_g07` after `20260719_06_planning_review_evidence`; ancestry was inspected, not executed.
- Artifact bytes are written by `LocalFilesystemArtifactStore`; metadata/checksums are persisted in SQLite.
- Repository-defined upgrade command is `scripts/migrate-db.ps1`, which changes to `backend` and runs `alembic upgrade head`. No migration or rollback was run.

## 11. API, Event, Artifact, and Evidence Map

- Planning/review routes: `backend/app/api/routes/plans.py` and `backend/app/api/routes/planning_review.py`; G06 decision route is `POST /api/v1/runs/{run_id}/approvals/G06/decisions`.
- Stage routes: `backend/app/api/routes/stages.py` exposes prepare, sandbox, G07 inspection/decision, and bootstrap-install/status routes.
- Event vocabulary: `backend/app/domain/contracts.py` includes plan, G06, G07, command, cancellation, interruption, and stage events; durable appending is in `StateTransitionService._append_event`.
- SSE projection: `backend/app/events/README.md`, run routes, `frontend/src/hooks/useMigrationEvents.ts`, and `frontend/src/hooks/applyEventToRun.ts`.
- Evidence: `backend/app/artifact_store/local_store.py` writes immutable artifacts and checksum metadata; stage and command services register artifact references. Evidence files in `evidence/` are inputs to be verified, not proof by themselves.

## 12. Frontend Architecture and State Map

- API clients: `frontend/src/api/stages.ts`, `frontend/src/api/migrations.ts`, and planning clients.
- Stage UI: `frontend/src/components/StagePreparationPanel.tsx`, `BootstrapInstallPanel.tsx`, and `StageCards.tsx`.
- Authoritative projection: `frontend/src/hooks/useAuthoritativeRun.ts`, `useMigrationEvents.ts`, and `applyEventToRun.ts`.
- `frontend/package.json` defines `test`, `typecheck`, `lint`, and `build`; no frontend command was executed for this report correction.

## 13. Test and Fixture Map

- Focused backend files include `backend/tests/test_stage_workspace.py`, `test_command_execution.py`, `test_state_transition_service.py`, planning review tests, and artifact tests.
- Backend fixture contract: `backend/tests/fixture_generators/angular_fixture.py` and `backend/tests/test_angular18_fixture.py`.
- Frontend tests are under `frontend/src/**/__tests__`; event tests cover `applyEventToRun`, `useAuthoritativeRun`, and `useMigrationEvents`.
- Manual/SSE support: `scripts/mock-workflow.ps1`, `scripts/sse-replay-test.ps1`, and feature verification/manual scenario documents. No stage-specific manual script was found.
- No broad test, migration, build, service, OpenAPI generation, or manual scenario was executed.

## 14. Validation Command Matrix

Commands below use repository-relative forward-slash paths. `Repository-defined` means the cited script proves the command; `Framework-inferred` means package/configuration or an existing test path supports it; `Not found` means no repository command or documented procedure was found. None of these rows was executed unless explicitly marked otherwise.

| Purpose | Exact command | Working directory | Proof | Prerequisites / environment | Read-only safety, outputs, external services | Executed |
|---|---|---|---|---|---|---|
| Focused backend pytest syntax | `python -m pytest tests/test_stage_workspace.py` | `backend` | `backend/pyproject.toml`, test file | Python dependencies; optional `AMF_PYTEST_BASETEMP` | Test cache/temp DB possible; no external service required | No |
| Complete backend tests | `& ./scripts/test-backend.ps1` | repository root | `scripts/test-backend.ps1` | Python dependencies; optional `AMF_PYTEST_BASETEMP` | Broad tests and caches/temp state; may use fixtures | No |
| Frontend tests | `& ./scripts/test-frontend.ps1` | repository root | `scripts/test-frontend.ps1` | frontend dependencies | Vitest cache/output; no service required | No |
| Frontend typecheck | `npm run typecheck` | `frontend` | `frontend/package.json` | npm dependencies | Normally non-mutating, tool caches possible | No |
| Frontend lint | `npm run lint` | `frontend` | `frontend/package.json` | npm dependencies | Normally non-mutating, tool caches possible | No |
| Frontend build | `npm run build` | `frontend` | `frontend/package.json` | npm dependencies | Writes `frontend/.next`; no service required | No |
| Migration upgrade | `& ./scripts/migrate-db.ps1` | repository root | `scripts/migrate-db.ps1` | backend environment and configured database | Not read-only; mutates configured database | No |
| Migration rollback | `alembic downgrade -1` | `backend` | framework command only; no repository rollback script or documented procedure found | Alembic and configured database | Not read-only; mutates database | No |
| Backend static check | `& ./scripts/backend-static-check.ps1` | repository root | `scripts/backend-static-check.ps1` | Python | Writes `__pycache__`; otherwise local | No |
| Architecture check | `& ./scripts/architecture-check.ps1` | repository root | `scripts/architecture-check.ps1` | `rg` | Read-only scan; no external service | No |
| Artifact integrity | `& ./scripts/artifact-integrity-test.ps1` | repository root | `scripts/artifact-integrity-test.ps1` | Python dependencies; optional `AMF_PYTEST_BASETEMP` | Tests/temp artifacts and caches | No |
| Fixture contract | `& ./scripts/fixture-contract-test.ps1` | repository root | `scripts/fixture-contract-test.ps1` | Python dependencies; optional `AMF_PYTEST_BASETEMP` | Tests/temp fixtures and caches | No |
| OpenAPI generation | `& ./scripts/generate-openapi-client.ps1` | repository root | `scripts/generate-openapi-client.ps1` | backend dependencies | Writes `shared/openapi.json`; not read-only | No |
| Aggregate quality | `& ./scripts/quality.ps1` | repository root | `scripts/quality.ps1` | Python/npm dependencies | Runs generation, tests, typecheck, build; writes generated/build/cache outputs | No |
| Manual mock workflow | `& ./scripts/mock-workflow.ps1` | repository root | `scripts/mock-workflow.ps1` | running backend, URL/auth settings, database | Mutates runtime state and starts no service itself | No |
| SSE replay | `& ./scripts/sse-replay-test.ps1` | repository root | `scripts/sse-replay-test.ps1` | running backend, `BaseUrl`, `RunId` parameters | Network request; requires external running service | No |
| Manual stage scenarios | no repository-defined stage script | not applicable | `docs/features/s2-f05/manual-scenario-2026-07-19.md`, `docs/features/s2-f06/manual-scenario-2026-07-19.md` | running authenticated backend/frontend and browser | External/runtime state; manual evidence | No |
| Git whitespace check | `git diff --check` | repository root | Git command; no script needed | Git | Read-only diff check; does not validate an entirely untracked report | Yes, final check |

The scripts were read directly: `scripts/test-backend.ps1`, `scripts/test-frontend.ps1`, `scripts/migrate-db.ps1`, `scripts/backend-static-check.ps1`, `scripts/architecture-check.ps1`, `scripts/artifact-integrity-test.ps1`, `scripts/fixture-contract-test.ps1`, `scripts/generate-openapi-client.ps1`, and `scripts/quality.ps1`. No guessed script names are used.

## 15. Potential Duplicate or Bypass Authorities

- `backend/app/orchestration/mock_nodes.py` contains mock workflow behavior; it must not become production workflow truth.
- `StagePreparationApplicationService.prepare_stage` builds a local stage-plan dictionary from request values; the active planning pointer is a separate contract and is recorded as an unresolved binding.
- `StageBootstrapApplicationService.run_bootstrap_install` checks G07/workspace and constructs an `npm ci` command request; active-plan command authorization and cancellation wiring remain dependencies.
- `WorkerSupervisor` and `ExecutionWorker` are the observed process path. No second production command runner was introduced by this correction.

## 16. Documentation Conflicts and Missing Documentation

- The prior baseline had stale HEAD/preflight claims and Markdown corruption; those are corrected here.
- The sprint snapshot declares S2-F07 as a dependency of AMFA-144. The inspected S2-F07 repository contract includes G06-related behavior, but the stage path visibly checks G07 and does not prove consumption of the current G06 binding; this is recorded as uncertainty, not reconciled by inference.
- No repository-defined rollback script or stage-specific manual scenario script was found.
- No `JobSupervisor`, `ProcessController`, explicit command-active endpoint, or dedicated process-termination evidence contract was found by symbol search.

## 17. Freshness and Incremental-Reinspection Protocol

The delta from `b2d18c5e033f91dd0890edeac30419ae364b8e64` to HEAD was documentation-only:

```text
git diff --name-status b2d18c5e033f91dd0890edeac30419ae364b8e64..HEAD
R100  AGENT.md  AGENTS.md
A     docs/sprint.md

git log --oneline b2d18c5e033f91dd0890edeac30419ae364b8e64..HEAD
81ba08c docs: standardize AGENTS instructions and add sprint scope snapshot
```

Freshness classification: reuse the existing source-code and architecture map; re-inspect only the files required by the review corrections. No implementation, migration, API, event, test, script, configuration, dependency, or architectural-contract delta was found.

Future targeted sprint-read protocol: do not reread all of `docs/sprint.md`. Read only (1) the global source-of-truth rule, (2) the global non-interpretation rule, (3) the relevant parent feature section, (4) the exact current subtask section, (5) explicitly required dependency sections, and (6) this baseline requirements index. Every future audit must run `git hash-object docs/sprint.md`. If it differs from `4c9a17670ce6d988bdcad48d43e805dbf9a0c53e`, stop and request a requirements-baseline refresh.

## 18. Files and Symbols Index

| Area | Files / symbols |
|---|---|
| Instructions and requirements | `AGENTS.md`; `docs/sprint.md`; this report |
| Planning | `backend/app/domain/planning.py:MigrationPlan`, `StageExecutionPlan`; `backend/app/services/planning_application_service.py`; `backend/app/repositories/planning_models.py` |
| Review and G06 | `backend/app/domain/planning_review.py:G06Gate`, `G06Decision`; `backend/app/services/planning_review_evidence_application_service.py`; `backend/app/repositories/planning_review_models.py` |
| Stage/G07 | `backend/app/services/stage_preparation_service.py:StagePreparationApplicationService`; `backend/app/repositories/stage_workspace_models.py`; `backend/app/api/routes/stages.py` |
| Bootstrap | `backend/app/services/stage_bootstrap_service.py:StageBootstrapApplicationService`; `backend/app/api/routes/stages.py` |
| Commands | `backend/app/command_execution/worker.py:CommandRegistry`, `CommandPolicy`, `WorkerSupervisor`, `ExecutionWorker`, `CommandLogWriter` |
| State/leases | `backend/app/state/transition_service.py:StateTransitionService`; `backend/app/repositories/models/workflow.py:WorkerLeaseModel`, `CommandExecutionModel`, `WorkflowEventModel` |
| Artifacts/events | `backend/app/artifact_store/local_store.py`; `backend/app/domain/contracts.py:WorkflowEventType`; `backend/app/events` |
| Frontend | `frontend/src/hooks/useAuthoritativeRun.ts`, `useMigrationEvents.ts`, `applyEventToRun.ts`; `frontend/src/api/stages.ts`, `migrations.ts` |
| Validation | `scripts/test-backend.ps1`, `test-frontend.ps1`, `migrate-db.ps1`, `backend-static-check.ps1`, `architecture-check.ps1`, `artifact-integrity-test.ps1`, `fixture-contract-test.ps1`, `generate-openapi-client.ps1`, `quality.ps1` |

## 19. Environment Limitations

This correction was report-only. Dependency installation, broad tests, migrations, builds, OpenAPI generation, services, and manual scenarios were not run. Runtime claims are therefore limited to code and configuration inspection. `git diff --check` was run as a Git integrity check, but because this report was entirely untracked during the check, direct file validation below is the authoritative Markdown check.

## 20. Baseline Reviewer Verdict

Fresh adversarial self-review: `PASS`.

Verified: all ten required Jira issue sections and all four required global sprint sections were read; pinned HEAD/upstream metadata and sprint identity match; `AGENTS.md` is sole root authority; S2-F07 and S3-F04 maps distinguish authorities, coordinators, persistence, APIs, events/evidence, and uncertainty; validation commands are repository-defined or explicitly classified as inferred/not found; direct Markdown validation passes; final integrity outputs are recorded; no Jira completion claim was introduced; and only this report changed.

### Requirements index

| Issue key | Exact issue heading | Parent | Section start | End boundary | Primary technical domain | Declared dependencies |
|---|---|---|---|---|---|---|
| AMFA-144 | `S3-F05 — Prepare a dedicated stage sandbox and decide G07 stage start` | — | `docs/sprint.md:32-34` | before `# AMFA-170` at line 105 | stage preparation, G07, sandbox | `S2-F07`, `S3-F04` |
| AMFA-170 | `S3-F05-I01 — Backend: Implement stage preparation, G07, and sandbox creation` | AMFA-144 | `docs/sprint.md:105-107` | before `# AMFA-171` at line 154 | backend stage preparation | `S2-F07`, `S3-F04` |
| AMFA-171 | `S3-F05-I02 — API/Evidence: Persist stage-start, G07, and sandbox evidence` | AMFA-144 | `docs/sprint.md:154-156` | before `# AMFA-172` at line 201 | persistence, API, evidence | `S3-F05-I01` |
| AMFA-172 | `S3-F05-I03 — Frontend: Build G07 stage-start and sandbox review page` | AMFA-144 | `docs/sprint.md:201-203` | before `# AMFA-173` at line 245 | frontend stage review | `S3-F05-I02` |
| AMFA-173 | `S3-F05-I04 — Testing/Security/Docs: Validate G07 and sandbox isolation` | AMFA-144 | `docs/sprint.md:245-247` | before `# AMFA-145` at line 303 | testing, security, documentation | `S3-F05-I03` |
| AMFA-145 | `S3-F06 — Run the stage bootstrap clean install` | — | `docs/sprint.md:303-305` | before `# AMFA-174` at line 373 | bootstrap install | `S3-F05` |
| AMFA-174 | `S3-F06-I01 — Backend: Implement stage bootstrap clean install` | AMFA-145 | `docs/sprint.md:373-375` | before `# AMFA-175` at line 414 | backend command execution | `S3-F05` |
| AMFA-175 | `S3-F06-I02 — API/Evidence: Persist bootstrap-install execution and fingerprints` | AMFA-145 | `docs/sprint.md:414-416` | before `# AMFA-176` at line 462 | persistence, API, evidence | `S3-F06-I01` |
| AMFA-176 | `S3-F06-I03 — Frontend: Build bootstrap-install pipeline step` | AMFA-145 | `docs/sprint.md:462-464` | before `# AMFA-177` at line 519 | frontend pipeline state | `S3-F06-I02` |
| AMFA-177 | `S3-F06-I04 — Testing/Security/Docs: Validate bootstrap clean install` | AMFA-145 | `docs/sprint.md:519-521` | before `# Delivery Dependency Order` at line 577 | testing, security, documentation | `S3-F06-I03` |

### Final integrity record

The following values are the actual final command outputs. The direct Markdown validation corrected 17 identified defects from the prior report, including malformed backticks/paths, corrupted script names, tabs, and control characters. `git diff --check` does not validate an entirely untracked file, so direct file validation is recorded separately.

```text
git status --porcelain=v1 -uall
?? docs/audits/00_REPOSITORY_AUDIT_BASELINE.md

git diff --check

exit code: 0; no output. This does not validate an entirely untracked file.

git hash-object docs/sprint.md
4c9a17670ce6d988bdcad48d43e805dbf9a0c53e

git hash-object docs/audits/00_REPOSITORY_AUDIT_BASELINE.md
The actual output is recorded in the final handoff because embedding a self-hash would change the file identity.
```

Direct validation command exit code: `0`. Exact output: `PASS: baseline Markdown integrity`.
