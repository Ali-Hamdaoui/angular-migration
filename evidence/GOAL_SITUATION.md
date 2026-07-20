# G02 — Stage Workspace, G07, and Bootstrap: Current Situation

## 1. Goal Identity

| Field | Value |
|---|---|
| Goal ID | G02 |
| Goal name | Stage Workspace, G07, and Bootstrap |
| Sprint | Sprint 3 (features S3-F05, S3-F06) |
| Worktree | `/home/ubuntu/amfa-worktrees/02-stage-workspace-bootstrap` |
| Branch | `hermes/02-stage-workspace-bootstrap` |
| Base SHA | `d759861290c1e76e26c4f2b27bbee9a77a12f0b5` |
| Current HEAD SHA | `82ffc60765cd0dc6975bad643f59ea7a106117fa` |
| Remote branch | `origin/hermes/02-stage-workspace-bootstrap` (present, matches HEAD) |
| Last audited date | 2026-07-20 |

## 2. Executive Situation

G02 prepares a run-scoped stage sandbox, runs the G07 gate decision, and is responsible for the authorized stage bootstrap clean install (`npm ci`). S3-F05 (stage workspace + G07) is genuinely implemented, wired into the dashboard, and unit-tested (40 tests pass), but not runtime-verified. S3-F06 (bootstrap install) is **partial/blocked**: the start path queues an `npm ci` `CommandExecutionModel` but never executes it and never emits `COMPLETED`/`FAILED`; it also bypasses the required G01 `CommandExecutor`. The branch is **not ready**. Evidence is stale (`completion.json` head SHA predates the dashboard-wiring commit), manual validation was never executed, and 5 of 8 task-result JSONs are missing while `completion.json` claims all PASS. The downstream `stage_sandbox_ready` contract has no producer in this branch.

## 3. Goal Objective

- **Business:** Provide the run-scoped stage sandbox and the G07 human-approval gate, then run the authorized clean `npm ci` install that downstream G03 consumes — without mutating the external source.
- **Technical:** FastAPI `StagePreparationApplicationService` / `StageBootstrapApplicationService`, SQLAlchemy models, Alembic migration, durable events via `StateTransitionService`, immutable artifacts via `LocalFilesystemArtifactStore`, Next.js panels.
- **Upstream inputs:** G01 `CommandExecutor` (required for real install execution); S2-F07 approved plan (plan membership).
- **Downstream outputs:** `stage_sandbox_ready.schema.json` consumed by G03 (depends_on G02).

## 4. Related Jira Features

| Sprint | Feature | Jira ID | Expected capability | Current status |
|---|---|---|---|---|
| S3 | Dedicated run-scoped stage sandbox + G07 decision | AMFA-144 | Sandbox copy, G07 approval gate, events, UI | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| S3 | Stage bootstrap clean install (`npm ci`) | AMFA-145 | Authorized install execution + COMPLETED/FAILED evidence | BLOCKED_BY_EXTERNAL_DEPENDENCY |

## 5. Related Jira Tasks and Subtasks

| Jira ID | Parent feature | Task description | Expected deliverable | Actual implementation | Status |
|---|---|---|---|---|---|
| AMFA-170 | AMFA-144 | S3-F05-I01 backend/domain | App contract for stage prep + G07 | `backend/app/domain/stage_workspace.py` (`G07ApprovalService`, `StageWorkspaceService`); `services/stage_preparation_service.py`; `api/stage_contracts.py`; `api/routes/stages.py` | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-171 | AMFA-144 | S3-F05-I02 persistence/events/artifacts | Evidence contracts | `repositories/stage_workspace_models.py` (`G07ApprovalModel`, `StageWorkspaceModel`); migration `20260720_01_stage_workspace_g07.py`; events STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY/G07_*; `workspace_copy_report.json` artifact | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-172 | AMFA-144 | S3-F05-I03 frontend | Stage-start UI | `frontend/src/components/StagePreparationPanel.tsx` (calls prepareStage/createSandbox/decideG07/getG07Status), wired `AuthoritativeRunDashboard.tsx:70` | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-173 | AMFA-144 | S3-F05-I04 tests/security/docs | Tests, docs | `backend/tests/test_stage_workspace.py`; `docs/capabilities/02-stage-workspace-bootstrap/README.md` | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-174 | AMFA-145 | S3-F06-I01 backend/domain | Bootstrap install app contract | `services/stage_bootstrap_service.py:StageBootstrapApplicationService.run_bootstrap_install` builds `CommandExecutionModel(status=QUEUED)` + StageStepModel, NO dispatch, NO COMPLETED/FAILED, returns QUEUED | PARTIALLY_IMPLEMENTED |
| AMFA-175 | AMFA-145 | S3-F06-I02 persistence/events/artifacts | Evidence contracts | Emits `STAGE_BOOTSTRAP_INSTALL_STARTED` only; `BootstrapInstallResult` imported but unused; no install artifacts | PARTIALLY_IMPLEMENTED |
| AMFA-176 | AMFA-145 | S3-F06-I03 frontend | Bootstrap UI | `frontend/src/components/BootstrapInstallPanel.tsx` (runBootstrapInstall/getBootstrapInstallStatus), wired `AuthoritativeRunDashboard.tsx:71` | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-177 | AMFA-145 | S3-F06-I04 tests/security/docs | Tests, docs | Service-layer start-path + status tests; no completion-path test; docs written | IMPLEMENTED_NOT_RUNTIME_VERIFIED |

Closeout tasks (from `evidence/task-results/`):
- C90: BLOCKED_BY_EXTERNAL_DEPENDENCY (needs G01/G03).
- C91: BLOCKED_BY_EXTERNAL_DEPENDENCY (manual validation not executed).
- C92: IMPLEMENTED_AND_VERIFIED (as-built README present).
- C93: IMPLEMENTED_NOT_RUNTIME_VERIFIED (stale).

## 6. Acceptance Criteria Status

| Acceptance criterion | Expected behavior | Current evidence | Status | Gap |
|---|---|---|---|---|
| S3-F05 Happy path | PREPARE + persist + 5 events + UI | `stage_preparation_service.py:105-466` emits events; panel wired | Met (code) | not runtime-verified |
| S3-F05 Invalid input | stable error | `StageApplicationError` → 422/404/409 (`routes/stages.py:34-43`) | Met (code) | not runtime-verified |
| S3-F05 Stale state | no dup | checks `run.state_version` (`stage_preparation_service.py:75,142,330`) | Met (code) | not runtime-verified |
| S3-F05 Persistence | workspace/plan/gate/fingerprint records | `StageWorkspaceModel`, `G07ApprovalModel`, migration `20260720_01` | Met | — |
| S3-F05 Evidence | SHA-256 artifacts | `workspace_copy_report.json` via `LocalFilesystemArtifactStore` | Partial | `stage_sandbox_ready` schema artifact NOT produced |
| S3-F05 Frontend behavior | distinct states | `StagePreparationPanel.tsx` | Met (code) | not runtime-verified |
| S3-F05 Backend failure | correlation id | no explicit correlation_id in stage errors | Partial | — |
| S3-F05 Missing approval | transition rejects | `run_bootstrap_install` checks `G07_REQUIRED` | Met (code) | — |
| S3-F05 Approval binding | bound to checksum/version/fingerprint | `G07ApprovalPackage` binds; idempotency; G07_STALE emitted | Met (code) | not runtime-verified |
| S3-F05 Technical truth | failed check blocks approval | G07ApprovalService present; no mandatory technical-check gate wired | Partial | — |
| S3-F05 Source safety | original source fingerprint == approved | `create_sandbox` copies but does NOT re-verify source fingerprint | Missing | no source-integrity re-check |
| S3-F06 Happy path | authorized op + STARTED/COMPLETED/FAILED | STARTED only; COMPLETED/FAILED NEVER emitted; npm ci never runs | Partial | bootstrap never executes/completes |
| S3-F06 Invalid input | stable error | `StageApplicationError` (`routes/stages.py:73`) | Met (code) | — |
| S3-F06 Stale state | STALE_STATE_VERSION | check present (`stage_bootstrap_service.py:54`) | Met (code) | — |
| S3-F06 Persistence | step state, command exec, fingerprints | StageStepModel + CommandExecutionModel(QUEUED) + pre_fingerprint | Partial | command never leaves QUEUED |
| S3-F06 Evidence | install logs, pre/post fingerprints, pkg-mgr debug | `BootstrapInstallResult` unused; no artifacts | Missing | no install evidence |
| S3-F06 Frontend behavior | distinct states | `BootstrapInstallPanel.tsx` | Met (code) | not runtime-verified |
| S3-F06 Backend failure | partial evidence, correlation | not implemented | Missing | no failure handling/evidence |
| S3-F06 Execution authority | reject bypass template/profile/shell=false | built with shell=False, npm ci, isolated profile BUT never dispatched via CommandExecutor | Partial | bypasses CommandExecutor |

## 7. Actual Backend Implementation

| File | Symbols | Responsibility | Jira task | Verification |
|---|---|---|---|---|
| `backend/app/domain/stage_workspace.py` | `G07ApprovalService`, `StageWorkspaceService`, `G07ApprovalPackageBuilder`, `G07Decision`, `StageStatus`, `StageExecutionPlan`, `StageFingerprint`, `StageSandboxVerification`, `BootstrapInstallResult` | Domain rules, checksums, G07 | AMFA-170 | Unit-tested |
| `backend/app/services/stage_preparation_service.py` | `StagePreparationApplicationService.prepare_stage/create_sandbox/get_g07/decide_g07` | S3-F05 orchestration, events, artifacts | AMFA-170/171 | Service tests |
| `backend/app/services/stage_bootstrap_service.py` | `StageBootstrapApplicationService.run_bootstrap_install/get_bootstrap_status` | S3-F06 orchestration | AMFA-174 | Partial (start path only) |
| `backend/app/api/stage_contracts.py` | *Request/*Response DTOs | Typed HTTP contracts | AMFA-170 | Imported by routes |
| `backend/app/api/routes/stages.py` | prepare/sandbox/inspect_g07/decide_g07/bootstrap_install/status | Thin routers | AMFA-170/174 | Registered (no HTTP test) |
| `backend/app/repositories/stage_workspace_models.py` | `G07ApprovalModel`, `StageWorkspaceModel` | ORM persistence | AMFA-171 | Migrated |
| `backend/app/domain/contracts.py` | WorkflowEventType additions (357-371) | Durable event enums | AMFA-170/171 | Present |

## 8. Actual Frontend Implementation

| File | Component/API/type | Responsibility | Jira task | Wired into UI |
|---|---|---|---|---|
| `frontend/src/api/stages.ts` | prepareStage/createSandbox/getG07Status/decideG07/runBootstrapInstall/getBootstrapInstallStatus | Typed API client | AMFA-172/176 | YES |
| `frontend/src/components/StagePreparationPanel.tsx` | StagePreparationPanel | S3-F05 UI | AMFA-172 | YES (`AuthoritativeRunDashboard.tsx:70`) |
| `frontend/src/components/BootstrapInstallPanel.tsx` | BootstrapInstallPanel | S3-F06 UI | AMFA-176 | YES (`AuthoritativeRunDashboard.tsx:71`) |
| `frontend/src/components/*module.css` | styles | styling | AMFA-172/176 | YES |

## 9. API and Event Coverage

### APIs

| Method | Path | Purpose | Jira task | Implemented | Tested |
|---|---|---|---|---|---|
| POST | `/runs/{run_id}/stages/prepare` | Prepare stage + lock plan | AMFA-170 | Yes | Service-layer only |
| POST | `/runs/{run_id}/stages/{stage_id}/sandbox` | Create sandbox copy | AMFA-171 | Yes | Service-layer only |
| GET | `/runs/{run_id}/approvals/G07` | Inspect G07 | AMFA-171 | Yes | Service-layer only |
| POST | `/runs/{run_id}/approvals/G07/decisions` | Decide G07 gate | AMFA-171 | Yes | Service-layer only |
| POST | `/runs/{run_id}/stages/{stage_id}/bootstrap-install` | Bootstrap install (start) | AMFA-174 | Yes (start only) | Service-layer only |
| GET | `/runs/{run_id}/stages/{stage_id}/steps/bootstrap-install` | Bootstrap status | AMFA-175 | Yes | Service-layer only |

### Events

| Event | Trigger | Jira task | Emitted | Payload verified |
|---|---|---|---|---|
| STAGE_CREATED | prepare_stage | AMFA-170 | Yes | Code only |
| STAGE_PREPARING | prepare_stage | AMFA-170 | Yes | Code only |
| STAGE_PLAN_LOCKED | create_sandbox | AMFA-171 | Yes | Code only |
| STAGE_WAITING_APPROVAL | create_sandbox | AMFA-171 | Yes | Code only |
| STAGE_SANDBOX_READY | decide_g07 (approved) | AMFA-171 | Yes | Code only |
| G07_CREATED/APPROVED/REJECTED/STALE | decide_g07 | AMFA-171 | Yes | Code only |
| STAGE_BOOTSTRAP_INSTALL_STARTED | run_bootstrap_install | AMFA-174 | Yes | Code only |
| STAGE_BOOTSTRAP_INSTALL_COMPLETED | (none) | AMFA-175 | **NO** | — |
| STAGE_BOOTSTRAP_INSTALL_FAILED | (none) | AMFA-175 | **NO** | — |

## 10. Persistence and Migration Status

| Table/model | Migration | Purpose | Jira task | Status |
|---|---|---|---|---|
| `g07_approvals` | `20260720_01_stage_workspace_g07.py` (rev 01, down 20260719_06) | G07 approvals | AMFA-171 | Present |
| `stage_workspaces` | same | sandbox metadata | AMFA-171 | Present |
| `migration_stages`, `migration_runs`, `stage_steps`, `command_executions`, `artifact_metadata` | pre-existing | reused | AMFA-171/174 | Present |

- Alembic head = `20260720_01` (single head, no conflicts). Downgrade reversible. Not executed in audit.
- Indexes: `ix_g07_approvals_run_id/stage_id/status`; `ix_stage_workspaces_run_id/stage_id`. Idempotency: `uq_g07_approvals_run_idempotency`, `uq_stage_workspaces_run_stage`.
- Gap: `stage_workspaces.copy_status` default "completed" while `file_count`/`total_size_bytes` always 0; no `stage_sandbox_ready` artifact produced.

## 11. Automated Test Situation

| Test file | Scope | Collected tests | Passing | Failing | Jira coverage |
|---|---|---|---|---|---|
| `backend/tests/test_stage_workspace.py` | domain G07, stage prep, bootstrap start | 40 | 40 (ran by reviewer) | 0 | AMFA-170/171/173/174/175/176/177 |

Executed command:
- `cd /home/ubuntu/amfa-worktrees/02-stage-workspace-bootstrap && python -m pytest backend/tests/test_stage_workspace.py` → **40 passed in 22.70s** (reviewer).
- No frontend component tests, no HTTP/API-layer tests, no Alembic upgrade/downgrade tests, no security tests. `completion.json` claim of 39/40 unit tests is inaccurate (actual 40). Counts for the broader suite are treated as **NOT EXECUTED DURING THIS AUDIT** beyond this single file.

## 12. Manual Test Situation

| Manual scenario | Documented | Executed | Result | Evidence |
| --------------- | ---------- | -------- | ------ | -------- |
| MT-001 S3-F05 authoritative | Yes | No | — | `evidence/manual-test-evidence.md` is a template/plan, not runtime results |
| MT-002 S3-F06 authoritative | Yes | No | — | same |
| MT-900 integrated happy path | Yes (stub) | No | — | same |
| MT-910 stale/idempotency/reconnect | Yes (stub) | No | — | same |
| MT-920 security/a11y/observability | Yes (stub) | No | — | same |

Manual runtime validation was **never executed** (C91 PENDING). Code inspection ≠ runtime validation.

## 13. Evidence Situation

| Evidence file | Purpose | Current | Accurate | Notes |
| ------------- | ------- | ------- | -------- | ----- |
| `evidence/completion.json` | Completion summary | head_sha `b6116df` | STALE/INACCURATE | Actual HEAD `82ffc60`; predates dashboard wiring; `branch_ready:true` over-optimistic; `unit_tests_passing:39` wrong (40); claims all 8 subtasks PASS |
| `evidence/current-state-gap-map.json` | pre-impl snapshot | all MISSING/PARTIAL | STALE | pre-implementation; not updated post-build; misleading if read as current |
| `evidence/dependency-status.json` | dep availability | S2-F07/S3-F04 PRESENT | PARTIAL | **G01 CommandExecutor omitted** — hides the real blocker |
| `evidence/shared-file-changes.json` | shared edits | matches diff | Yes | contracts.py/router.py/models/__init__.py |
| `evidence/manual-test-evidence.md` | runtime proof | template only | Partial | not executed |
| `evidence/task-results/01,02,05*.json` | 3 of 8 subtask results | present (PASS) | Partial | self-reported; no independent artifact |
| `evidence/task-results/03,04,06,07,08*.json` | 5 of 8 subtask results | **MISSING** | — | completion.json claims PASS for all 8 |

## 14. Dependency Situation

### Upstream dependencies

| Goal/feature | Required capability | Current availability | Impact |
| ------------ | ------------------- | -------------------- | ------ |
| G01 (`CommandExecutor`) | Execute queued npm-ci command | **NOT present on branch/goal**; bootstrap builds CommandExecutionModel but never dispatches it | Bootstrap install structurally impossible until G01 lands |
| S2-F07 (planning review) | Approved plan payload | PRESENT (frozen contract consumed) | G07 binds plan_version/checksum |
| S3-F04 | listed in gap map as S3-F05 dep; absent from GOAL.md | unverified | discrepancy |

### Downstream consumers

| Goal/feature | Capability consumed | Contract provided | Readiness |
| ------------ | ------------------- | ----------------- | --------- |
| G03 (depends_on G02) | `stage_sandbox_ready.schema.json` | schema defined in `goals/shared/contracts/` but **G02 produces NO conforming artifact** (no `sandbox_id`, no `stage_sandbox_ready` event/artifact) | Contract defined, producer MISSING |

## 15. Known Issues and Gaps

| ID | Severity | Description | Jira impact | Owner | Required action |
| -- | -------- | ----------- | ----------- | ----- | --------------- |
| K1 | BLOCKER | Bootstrap install never executes (`npm ci`) nor emits COMPLETED/FAILED; `BootstrapInstallResult` unused; command stuck QUEUED | AMFA-145/174/175/177 | G02 | Wire to CommandExecutor (post-G01); emit terminal events; produce install evidence |
| K2 | MAJOR | `stage_sandbox_ready.schema.json` contract has no producer in G02 | downstream G03 | G02 | Emit conforming artifact on sandbox ready |
| K3 | MAJOR | No source-safety fingerprint re-check after sandbox copy | AMFA-144 | G02 | Re-verify original source fingerprint == approved pre-op |
| K4 | MAJOR | Manual runtime validation not executed; `manual-test-evidence.md` is template only | all | G02 | Run MT-001..920 vs live stack |
| K5 | MAJOR | `completion.json` head_sha stale (`b6116df` vs `82ffc60`); 5/8 task-results missing; `unit_tests_passing:39` wrong | closeout | G02 | Regenerate completion.json; add missing task-results |
| K6 | CRITICAL | Bootstrap bypasses CommandExecutor (execution authority) | AMFA-145 | G02 | Route via registered command runtime after G01 lands |
| K7 | MINOR | `decide_g07` error lacks explicit correlation_id; no bootstrap failure/evidence path | AMFA-144/145 | G02 | Add correlation IDs; failure handling |
| K8 | MINOR | No HTTP/API/SSE/Alembic/security tests exist | AMFA-173/177 | G02 | Add coverage |

## 16. Goal Completion Matrix

| Dimension                     | Status | Evidence |
| ----------------------------- | ------ | -------- |
| Backend implementation        | Partial | S3-F05 services present; S3-F06 execution incomplete (K1/K6) |
| Frontend implementation       | Implemented | panels wired, no local advance |
| API contracts                 | Implemented | 6 routes registered, typed; no HTTP tests |
| Persistence                   | Implemented | migration `20260720_01`, single head, indexes present |
| Events                        | Partial | COMPLETED/FAILED gap (K1) |
| Automated tests               | Partial | 1 file / 40 tests pass; no coverage gaps |
| Manual runtime tests          | Missing | not executed (K4) |
| Security controls             | Partial | shell=false set; no CommandExecutor; no correlation IDs |
| Documentation                 | Implemented | as-built README present |
| Evidence                      | Partial | completion.json stale; 5/8 task-results missing (K5) |
| Upstream integration          | Partial | G01 CommandExecutor not used (K6); S2-F07 assumed |
| Downstream contract readiness | Missing | `stage_sandbox_ready` producer absent (K2) |

## 17. Jira Completion Summary

| Category                | Total | Complete | Partial | Blocked | Missing |
| ----------------------- | ----: | -------: | ------: | ------: | ------: |
| Features                |     2 |        0 |       1 |       1 |       0 |
| Implementation subtasks |     8 |        4 |       4 |       0 |       0 |
| Closeout tasks          |     4 |        1 |       1 |       2 |       0 |
| Acceptance criteria     |    20 |        0 |       9 |       0 |      11 |

(Feature AMFA-144 = Partial/implemented-not-runtime-verified (counted Partial); AMFA-145 = Blocked. Subtasks: AMFA-170/171/172/173/176/177 = verified-not-runtime; AMFA-174/175 = Partial. Closeout: C92 Complete; C90/C91 Blocked; C93 Partial.)

## 18. Final Status

| Field                  | Value |
| ---------------------- | ----- |
| `branch_ready`         | false |
| `harness_ready`        | false |
| `integration_verified` | false |
| `jira_complete`        | false |
| Reviewer verdict       | Genuinely implemented, wired, unit-tested stage-sandbox prep + G07 gate, but bootstrap "clean install" only queues an npm-ci command and never runs it because upstream G01 is absent and unrecorded as a dependency; completion.json stale and overstates PASS |
| Pushed                 | true |
| Remote SHA             | `82ffc60765cd0dc6975bad643f59ea7a106117fa` |

## 19. Recommended Next Actions

1. G02 / AMFA-145 — after G01 lands, dispatch the queued `npm ci` via `CommandExecutor`; emit `STAGE_BOOTSTRAP_INSTALL_COMPLETED`/`_FAILED`; produce install artifacts.
2. G02 / evidence — regenerate `completion.json` at HEAD `82ffc60`; add the 5 missing task-result JSONs; correct `unit_tests_passing`.
3. G02 / dependency-status — record G01 `CommandExecutor` as the real upstream blocker (currently omitted).
4. G02 / AMFA-144 — emit a `stage_sandbox_ready` conforming artifact for downstream G03.
5. G02 / all — execute MANUAL_TEST_PLAN (C91) against live stack.
6. G02 / AMFA-144 — add source-fingerprint re-verification after sandbox copy.

## 20. Audit Sources

- Git: `git log`, `git status`, `git rev-parse HEAD`, `git branch --show-current`, `git diff --stat d759861..HEAD`, `git merge-base` (G01/goal checks)
- Root: `AGENT.md`
- Goal: `goals/02-stage-workspace-bootstrap/{GOAL,TASK_INDEX,JIRA,ACCEPTANCE,CURRENT_CODE_MAP,CROSS_GOAL_CONTRACTS,OWNERSHIP,REFERENCES,MANUAL_TEST_PLAN}.md`, `tasks/T01..T08,C90..C93`, `manual-tests/MT-*`
- Backend: `domain/stage_workspace.py`, `domain/contracts.py`, `services/stage_preparation_service.py`, `services/stage_bootstrap_service.py`, `api/stage_contracts.py`, `api/routes/stages.py`, `api/router.py`, `repositories/stage_workspace_models.py`, `alembic/versions/20260720_01_stage_workspace_g07.py`, `tests/test_stage_workspace.py`
- Frontend: `frontend/src/api/stages.ts`, `components/StagePreparationPanel.tsx`, `BootstrapInstallPanel.tsx`, `AuthoritativeRunDashboard.tsx`
- Evidence: `completion.json`, `dependency-status.json`, `current-state-gap-map.json`, `shared-file-changes.json`, `manual-test-evidence.md`, `task-results/*`
- Shared: `goals/shared/contracts/stage_sandbox_ready.schema.json`, `goals/GOAL_INDEX.yaml`
- Docs: `docs/capabilities/02-stage-workspace-bootstrap/README.md`
