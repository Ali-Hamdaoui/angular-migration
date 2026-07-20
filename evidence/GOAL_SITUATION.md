# G03 — Exact Angular Transformation and G08: Current Situation

## 1. Goal Identity

| Field | Value |
|---|---|
| Goal ID | G03 |
| Goal name | Exact Angular Transformation and G08 |
| Sprint | Sprint 3 (features S3-F07, S3-F08, S3-F09) |
| Worktree | `/home/ubuntu/amfa-worktrees/03-angular-transform-review` |
| Branch | `hermes/03-angular-transform-review` |
| Base SHA | `d759861290c1e76e26c4f2b27bbee9a77a12f0b5` |
| Current HEAD SHA | `7e742f1840cf152f65481b92ca84924aed119432` |
| Remote branch | `origin/hermes/03-angular-transform-review` (present, matches HEAD) |
| Last audited date | 2026-07-20 |

## 2. Executive Situation

G03 governs the exact Angular update execution + target-version verification (S3-F07), transformation diff/risk capture (S3-F08), and the human G08 acceptance gate (S3-F09). The backend domain, persistence (migration `20260719_07`), API routes, events, and S3-F08/S3-F09 application services are implemented and unit/API-tested (30 tests pass under Python 3.11). However the branch is **not ready**. Concrete gaps: (a) S3-F07 has **no execution path** (no `ng update` dispatch, `command_execution_id` always NULL) and **no API route to complete/verify** the update, so the happy path can never reach SUCCEEDED/VERIFIED; (b) all three G03 frontend components (`AngularUpdatePanel`, `TransformationEvidenceViewer`, `G08ReviewWorkspace`) are **orphaned** — never imported/rendered; (c) mandatory startup evidence files (`current-state-gap-map.json`, `dependency-status.json`, `shared-file-changes.json`, `manual-test-report.json`) are **missing**; (d) manual runtime validation was never executed; (e) `AS_BUILT.md` contains inaccuracies (7 vs 8 endpoints; phantom events). Biggest current risk: S3-F07 is a recording layer, not an executing one, giving a false impression of completeness.

## 3. Goal Objective

- **Business:** Governed execution of the exact approved Angular major update (18→target), proof of resolved target version, full transformation diff + changed-file risk classification, and enforcement of the human G08 acceptance gate.
- **Technical:** FastAPI services + REST endpoints + 3 SQLAlchemy models + Alembic migration; deterministic domain (`domain/transformation.py`); fail-closed G08 approval.
- **Upstream inputs:** G02 stage sandbox/workspace + frozen contracts (`approved_stage_plan`, `stage_sandbox_ready`, `command_execution_record`).
- **Downstream outputs:** `transformation_result.schema.json` consumed by G04 (depends_on G03).

## 4. Related Jira Features

| Sprint | Feature | Jira ID | Expected capability | Current status |
|---|---|---|---|---|
| S3 | Execute exact Angular update & verify target version | AMFA-146 | Update exec + target-version verify + events + UI | PARTIALLY_IMPLEMENTED |
| S3 | Capture transformation diffs & classify changed-file risk | AMFA-147 | Diff/risk capture + artifacts + UI | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| S3 | Review & decide G08 transformation acceptance | AMFA-148 | G08 gate + events + UI | IMPLEMENTED_NOT_RUNTIME_VERIFIED |

## 5. Related Jira Tasks and Subtasks

| Jira ID | Parent feature | Task description | Expected deliverable | Actual implementation | Status |
|---|---|---|---|---|---|
| AMFA-178 | AMFA-146 | S3-F07-I01 backend domain | Domain models for update + target version | `backend/app/domain/transformation.py` (`AngularUpdateCommand`, `AngularUpdateResult`, `TargetVersionEvidence`) | IMPLEMENTED_AND_VERIFIED |
| AMFA-179 | AMFA-146 | S3-F07-I02 db/api/events/artifacts | Persist/expose evidence; events | `repositories/transformation_models.py`, `routes/transformations.py`, migration `20260719_07`, events ANGULAR_UPDATE_*/TARGET_VERSION_* | PARTIALLY_IMPLEMENTED |
| AMFA-180 | AMFA-146 | S3-F07-I03 frontend | UI surface | `frontend/src/components/AngularUpdatePanel.tsx` (NOT imported/rendered) | PARTIALLY_IMPLEMENTED |
| AMFA-181 | AMFA-146 | S3-F07-I04 tests/security/docs | Tests + docs | `test_g03_domain.py`, `test_g03_api.py`, `AS_BUILT.md` (no frontend tests) | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-182 | AMFA-147 | S3-F08-I01 backend domain | Diff/risk domain | `transformation.py` (`DiffSummary`, `ChangedFileEntry`, `TransformationEvidenceResult`) | IMPLEMENTED_AND_VERIFIED |
| AMFA-183 | AMFA-147 | S3-F08-I02 db/api/events/artifacts | Persist/expose | `TransformationEvidenceModel`, POST `/transformation-evidence`, events TRANSFORMATION_EVIDENCE_* | IMPLEMENTED_AND_VERIFIED |
| AMFA-184 | AMFA-147 | S3-F08-I03 frontend | UI surface | `frontend/src/components/TransformationEvidenceViewer.tsx` (NOT imported/rendered) | PARTIALLY_IMPLEMENTED |
| AMFA-185 | AMFA-147 | S3-F08-I04 tests/security/docs | Tests + docs | domain/api tests, docs | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-186 | AMFA-148 | S3-F09-I01 backend domain | G08 domain | `transformation.py` (`G08EvidencePackage`, `G08ApprovalService`, `G08EvidencePackageBuilder`) | IMPLEMENTED_AND_VERIFIED |
| AMFA-187 | AMFA-148 | S3-F09-I02 db/api/events/artifacts | Persist/expose | `G08ApprovalModel`, GET/POST `/approvals/G08/...`, events G08_* | IMPLEMENTED_AND_VERIFIED |
| AMFA-188 | AMFA-148 | S3-F09-I03 frontend | UI surface | `frontend/src/components/G08ReviewWorkspace.tsx` (NOT imported/rendered) | PARTIALLY_IMPLEMENTED |
| AMFA-189 | AMFA-148 | S3-F09-I04 tests/security/docs | Tests + docs | domain/api tests, docs | IMPLEMENTED_NOT_RUNTIME_VERIFIED |

Closeout tasks (from `evidence/task-results/`):
- C90 (capability-contract integration tests): PARTIALLY_IMPLEMENTED (domain+API tests only; no cross-goal integration).
- C91 (independent manual runtime validation): MISSING (no manual-test report; blocked by G02).
- C92 (as-built docs): IMPLEMENTED (present; contains inaccuracies — 7 vs 8 endpoints, phantom events).
- C93 (final audits/completion/push): PARTIALLY_IMPLEMENTED (completion.json present, branch pushed, but mandated startup evidence missing).

## 6. Acceptance Criteria Status

| Acceptance criterion | Expected behavior | Current evidence | Status | Gap |
|---|---|---|---|---|
| S3-F07 Happy path | Execute update, persist, emit, show success | `start_update` persists + emits ANGULAR_UPDATE_STARTED; **no complete/verify endpoint; no real execution** | PARTIAL | no API path to SUCCEEDED/VERIFIED |
| S3-F07 Invalid input | stable error | `G03ApplicationError` → 422/404/409; tested | PASS | — |
| S3-F07 Stale state | no duplicate | `run.state_version != expected` → 409; tested | PASS | — |
| S3-F07 Persistence | step/command/version/state/events | `AngularUpdateRecordModel` with state_version; `command_execution_id` NULL | PASS | no command evidence |
| S3-F07 Evidence | update command/logs, target-version report | only domain model; no artifacts written | PARTIAL | no execution → no command/output evidence |
| S3-F07 Frontend behavior | distinct states | `AngularUpdatePanel` exists but **not mounted** | FAIL (UI) | not rendered |
| S3-F07 Backend failure | partial evidence, correlation id | error path returns code+message | PARTIAL | no correlation-id surfaced |
| S3-F07 Execution authority | reject bypass shell=false | modeled `shell=False`; never dispatched via CommandExecutor | FAIL | no execution path |
| S3-F08 Happy path | generate evidence, emit, success | `generate()` persists + emits COMPLETED/BLOCKED; tested | PASS | — |
| S3-F08 Invalid input | stable error | validated; `G03ApplicationError` | PASS | — |
| S3-F08 Stale state | STALE_STATE_VERSION | enforced | PASS | — |
| S3-F08 Persistence | summary/risk/artifact records | `TransformationEvidenceModel` | PASS | — |
| S3-F08 Evidence | diff/lockfile/migration/forbidden | artifacts written | PASS | TRANSFORMATION_EVIDENCE_STARTED not emitted |
| S3-F08 Frontend behavior | distinct states | viewer exists, **not mounted** | FAIL (UI) | not rendered |
| S3-F08 Backend failure | correlation id | error path | PARTIAL | no correlation id |
| S3-F09 Happy path | decision, emit gate created | `decide()` emits G08_CREATED/APPROVED; tested | PARTIAL | emits G08_CREATED not APPROVAL_GATE_CREATED (doc mismatch) |
| S3-F09 Invalid input | stable error | validated | PASS | — |
| S3-F09 Stale state | STALE_STATE_VERSION | enforced | PASS | — |
| S3-F09 Persistence | gate version/checksums/decisions | `G08ApprovalModel` | PASS | — |
| S3-F09 Evidence | G08 package referencing artifacts | `G08EvidencePackageBuilder` + index artifact | PASS | — |
| S3-F09 Frontend behavior | distinct states | `G08ReviewWorkspace` exists, **not mounted** | FAIL (UI) | not rendered |
| S3-F09 Missing approval | reject progression if G08 pending | gate recorded; transition integration not verified | PARTIAL | depends on G02 integration |
| S3-F09 Approval binding | stale on fingerprint/state/artifact change | only flags stale when `evidence_complete==False`; no drift check | FAIL | staleness under-implemented |
| S3-F09 Technical truth | failed check blocks approval | CRITICAL risk → rejected; incomplete → stale | PARTIAL | only risk+completeness checked |

## 7. Actual Backend Implementation

| File | Symbols | Responsibility | Jira task | Verification |
|---|---|---|---|---|
| `backend/app/domain/transformation.py` | `AngularUpdateCommand`, `AngularUpdateResult`, `TargetVersionEvidence`, `DiffSummary`, `ChangedFileEntry`, `TransformationEvidenceResult`, `ForbiddenChangeEntry`, `G08EvidencePackage`, `G08EvidencePackageBuilder`, `G08ApprovalService` | Pure domain + fail-closed decision | AMFA-178/182/186 | Unit-tested (21 fns) |
| `backend/app/api/transformation_contracts.py` | *Request/*Response DTOs | HTTP DTOs | AMFA-179/183/187 | Imported by routes |
| `backend/app/services/transformation_application_service.py` | `AngularUpdateApplicationService`, `TransformationEvidenceApplicationService`, `G08ApprovalApplicationService`, `G03ApplicationError` | Orchestration: persist, events, artifacts | AMFA-179/183/187 | API-tested |
| `backend/app/api/routes/transformations.py` | 8 routes under `/runs/{id}/stages/{sid}` | REST surface | AMFA-179/183/187 | Wired in router.py; API-tested |
| `backend/app/repositories/transformation_models.py` | `AngularUpdateRecordModel`, `TransformationEvidenceModel`, `G08ApprovalModel` | Persistence models | AMFA-179/183/187 | Registered in `models/__init__.py` |
| `backend/alembic/versions/20260719_07_*.py` | upgrade/downgrade | 3 tables + indexes | AMFA-179/183/187 | Single head `20260719_07` |

## 8. Actual Frontend Implementation

| File | Component/API/type | Responsibility | Jira task | Wired into UI |
|---|---|---|---|---|
| `frontend/src/api/transformations.ts` | API client (7 functions) | Calls G03 endpoints | AMFA-180/184/188 | YES (client exists) |
| `frontend/src/types/transformation.ts` | TS types | Typed contracts | AMFA-180/184/188 | YES (types defined) |
| `frontend/src/components/AngularUpdatePanel.tsx` | AngularUpdatePanel | S3-F07 UI | AMFA-180 | **NO** (not imported/rendered) |
| `frontend/src/components/TransformationEvidenceViewer.tsx` | TransformationEvidenceViewer | S3-F08 UI | AMFA-184 | **NO** (not imported/rendered) |
| `frontend/src/components/G08ReviewWorkspace.tsx` | G08ReviewWorkspace | S3-F09 UI | AMFA-188 | **NO** (not imported/rendered) |

Verification: grep across `frontend/src` shows these three components appear only in their own files; `AuthoritativeRunDashboard.tsx` imports no G03 panels.

## 9. API and Event Coverage

### APIs

| Method | Path | Purpose | Jira task | Implemented | Tested |
|---|---|---|---|---|---|
| POST | `/runs/{id}/stages/{sid}/angular-update` | Start update | AMFA-179 | Yes | Yes |
| GET | `/runs/{id}/stages/{sid}/angular-update` | Get update record | AMFA-179 | Yes | Yes |
| GET | `/runs/{id}/stages/{sid}/target-version` | Get target-version record | AMFA-179 | Yes (alias of get) | No dedicated test |
| POST | `/runs/{id}/stages/{sid}/transformation-evidence` | Generate evidence | AMFA-183 | Yes | Yes |
| GET | `/runs/{id}/stages/{sid}/transformation-evidence` | Get evidence | AMFA-183 | Yes | Yes |
| GET | `/runs/{id}/stages/{sid}/approvals/G08` | Inspect G08 | AMFA-187 | Yes | Yes |
| POST | `/runs/{id}/stages/{sid}/approvals/G08/decisions` | Decide G08 | AMFA-187 | Yes | Yes |
| POST | `/runs/{id}/stages/{sid}/approvals/G08/package` | Initialize G08 | AMFA-187 | Yes | No dedicated test |
| (MISSING) | POST `.../angular-update/complete` or `/verify-target-version` | Complete & verify update | AMFA-179 | **No** | N/A |

### Events

| Event | Trigger | Jira task | Emitted | Payload verified |
|---|---|---|---|---|
| ANGULAR_UPDATE_STARTED | start_update | AMFA-179 | Yes | via TransitionService |
| ANGULAR_UPDATE_COMPLETED/FAILED | complete_update | AMFA-179 | Defined, **no route calls it** | unreachable |
| TARGET_VERSION_VERIFIED/FAILED | verify_target_version | AMFA-179 | Defined, **no route calls it** | unreachable |
| TRANSFORMATION_EVIDENCE_COMPLETED/BLOCKED | generate | AMFA-183 | Yes | Yes |
| TRANSFORMATION_EVIDENCE_STARTED | (documented) | AMFA-183 | **NOT emitted** | doc mismatch |
| G08_CREATED/APPROVED/REJECTED/MODIFICATION_REQUESTED | decide | AMFA-187 | Yes | Yes |
| APPROVAL_GATE_CREATED | (documented) | AMFA-187 | **NOT emitted** (uses G08_CREATED) | doc mismatch |

## 10. Persistence and Migration Status

| Table/model | Migration | Purpose | Jira task | Status |
|---|---|---|---|---|
| `angular_update_records` | `20260719_07` (rev 07, down 06) | Angular update + version verification | AMFA-179 | OK |
| `transformation_evidence` | `20260719_07` | Diff/risk/forbidden records | AMFA-183 | OK |
| `g08_approvals` | `20260719_07` | G08 gate records | AMFA-187 | OK |

- Alembic head = `20260719_07` (single head, no conflicts). Downgrade drops in reverse order.
- Indexes: run_id/stage_id/status on each table. Idempotency: `UniqueConstraint(run_id, idempotency_key)` on all 3 tables; replay handled. OK.

## 11. Automated Test Situation

| Test file | Scope | Collected tests | Passing | Failing | Jira coverage |
|---|---|---|---|---|---|
| `backend/tests/test_g03_domain.py` | domain models, diff/risk, G08 decision | 21 | 21 | 0 | AMFA-178/182/186/189 |
| `backend/tests/test_g03_api.py` | API happy/stale/404/G08 flows | 9 | 9 | 0 | AMFA-179/183/187 |
| frontend `src/components/__tests__/*` | G03 component tests | **NONE** | N/A | N/A | AMFA-180/184/188 → MISSING |

Executed commands:
- `cd /home/ubuntu/amfa-worktrees/03-angular-transform-review && python3.11 -m pytest tests/test_g03_domain.py tests/test_g03_api.py` → **30 passed** (reviewer).
- NOTE: default `python3` (3.10) fails collection with `ImportError: cannot import name 'UTC'` (`datetime.UTC` requires 3.11); tests only pass under 3.11.
- `completion.json`/AS_BUILT claim "9 api integration tests" / "7 endpoints" — actual 9 API tests and 8 endpoints. Counts beyond the G03 files are treated as **NOT EXECUTED DURING THIS AUDIT** for the broader suite.

## 12. Manual Test Situation

| Manual scenario | Documented | Executed | Result | Evidence |
| --------------- | ---------- | -------- | ------ | -------- |
| MT-001 S3-F07 authoritative | Yes | No | — | No runtime evidence |
| MT-002 S3-F08 authoritative | Yes | No | — | No runtime evidence |
| MT-003 S3-F09 authoritative | Yes | No | — | No runtime evidence |
| MT-900 capability integrated happy path | Yes | No | — | No runtime evidence |
| MT-910 stale/idempotency/reconnect | Yes | No | — | No runtime evidence |
| MT-920 security/a11y/observability | Yes | No | — | No runtime evidence |

All scenarios documented in `goals/03-angular-transform-review/manual-tests/`; **none executed** against live runtime (no `manual-test-report.json`, no logs/screenshots). `completion.json` sets `jira_complete=false`, `integration_verified=false`.

## 13. Evidence Situation

| Evidence file | Purpose | Current | Accurate | Notes |
| ------------- | ------- | ------- | -------- | ----- |
| `evidence/completion.json` | V3 completion summary | present | Partial | `branch_ready:true` overstated (see K6); test counts unverified |
| `evidence/task-results/*.json` (12) | Per-task PASS records | present | Plausible | all show PASS; `commit_sha: null` |
| `evidence/current-state-gap-map.json` | Mandatory startup gap map | **MISSING** | N/A | required by AGENT.md §5, not created |
| `evidence/dependency-status.json` | Mandatory dependency map | **MISSING** | N/A | required, not created |
| `evidence/manual-test-report.json` | Manual runtime results | **MISSING** | N/A | expected per C91 |
| `evidence/shared-file-changes.json` | Shared-file edits record | **MISSING** | N/A | modified shared files not declared |
| `docs/capabilities/g03-angular-transform-review/AS_BUILT.md` | As-built docs | present | Inaccurate | claims 7 endpoints (actual 8); phantom events APPROVAL_GATE_CREATED/TRANSFORMATION_EVIDENCE_STARTED; "9 API tests" OK |

## 14. Dependency Situation

### Upstream dependencies

| Goal/feature | Required capability | Current availability | Impact |
| ------------ | ------------------- | -------------------- | ------ |
| G02 (`hermes/02-stage-workspace-bootstrap`) | stage sandbox/workspace + `stage_sandbox_ready` | consumed as **frozen/shared contracts** (PRESENT in `goals/shared/contracts/`) | end-to-end F07 blocked until G02 integrated; `blocked_integrated_criteria` = G02 |
| G01 (implicit) | real `ng update` execution via CommandExecutor | **not integrated; `command_execution_id` NULL** | F07 is a recording layer, no real execution |

### Downstream consumers

| Goal/feature | Capability consumed | Contract provided | Readiness |
| ------------ | ------------------- | ----------------- | --------- |
| G04 (depends_on G03) | `transformation_result.schema.json` | PROVIDED + registered in CONTRACT_REGISTRY | contract-ready; integration not verified |

## 15. Known Issues and Gaps

| ID | Severity | Description | Jira impact | Owner | Required action |
| -- | -------- | ----------- | ----------- | ----- | --------------- |
| K1 | MAJOR | G03 frontend components (`AngularUpdatePanel`, `TransformationEvidenceViewer`, `G08ReviewWorkspace`) not imported/rendered anywhere | AMFA-180/184/188 | G03 | Mount into dashboard/run page |
| K2 | MAJOR | S3-F07 has no API endpoint to complete/verify update (`complete_update`/`verify_target_version` unreachable) | AMFA-146/179 | G03 | Add POST complete/verify routes |
| K3 | MAJOR | No CommandExecutor execution path; `command_execution_id` always NULL; execution authority not satisfied | AMFA-146/179 | G03 | Dispatch via CommandExecutor |
| K4 | MAJOR | G08 approval-binding staleness only checks `evidence_complete`; no fingerprint/state/artifact drift detection | AMFA-148/187 | G03 | Implement drift detection |
| K5 | MINOR | Event name mismatch: ACCEPTANCE says APPROVAL_GATE_CREATED; code emits G08_CREATED; TRANSFORMATION_EVIDENCE_STARTED not emitted | AMFA-187/183 | G03 | Align to contract |
| K6 | MINOR | Mandatory startup evidence missing: gap-map, dependency-status, shared-file-changes, manual-test-report | All | G03 | Create per AGENT.md §5/§14 |
| K7 | MINOR | AS_BUILT.md inaccuracies (endpoints, phantom events, test count) | AMFA-181/185/189 | G03 | Correct docs |
| K8 | INFO | No frontend component tests for G03 | AMFA-180/184/188 | G03 | Add component tests |

## 16. Goal Completion Matrix

| Dimension                     | Status | Evidence |
| ----------------------------- | ------ | -------- |
| Backend implementation        | Partial | domain/service/models/routes present; S3-F07 execution incomplete (K2/K3) |
| Frontend implementation       | NO | components built but orphaned (K1) |
| API contracts                 | Partial | 8 endpoints wired & tested except complete/verify missing (K2) |
| Persistence                   | Implemented | 3 models + migration, single head, idempotent |
| Events                        | Partial | emitted; documented names mismatch; F07 verify unreachable (K5) |
| Automated tests               | Partial | 30 tests pass (3.11); no frontend tests |
| Manual runtime tests          | Missing | documented only; not executed |
| Security controls             | Partial | stale-state, fail-closed G08, shell=False modeled; no real execution |
| Documentation                 | Partial | AS_BUILT present but inaccurate (K7); startup evidence missing (K6) |
| Evidence                      | Partial | completion.json + 12 task-results; startup/manual evidence missing (K6) |
| Upstream integration          | NO | G02 not integrated; frozen contracts only |
| Downstream contract readiness | Implemented | `transformation_result.schema.json` provided + registered |

## 17. Jira Completion Summary

| Category                | Total | Complete | Partial | Blocked | Missing |
| ----------------------- | ----: | -------: | ------: | ------: | ------: |
| Features                |     3 |        0 |       3 |       0 |       0 |
| Implementation subtasks |    12 |        6 |       6 |       0 |       0 |
| Closeout tasks          |     4 |        1 |       2 |       0 |       1 |
| Acceptance criteria     |    24 |       12 |       8 |       0 |       4 |

(Subtasks: AMFA-178/182/186 = Complete (verified); AMFA-179/180/184/188 = Partial; AMFA-181/185/189 = verified-not-runtime. Closeout: C92 Complete; C90/C93 Partial; C91 Missing.)

## 18. Final Status

| Field                  | Value |
| ---------------------- | ----- |
| `branch_ready`         | false |
| `harness_ready`        | false |
| `integration_verified` | false |
| `jira_complete`        | false |
| Reviewer verdict       | Solid tested backend for diffs + G08, but flagship "execute + verify" is not runtime-wired and all frontend is dead code; not branch-complete |
| Pushed                 | true |
| Remote SHA             | `7e742f1840cf152f65481b92ca84924aed119432` |

## 19. Recommended Next Actions

1. G03 / AMFA-146 — add `complete_update`/`verify_target_version` API routes (or wire integration) so S3-F07 happy path can reach SUCCEEDED/VERIFIED.
2. G03 / AMFA-146 — dispatch `AngularUpdateCommand` via CommandExecutor (post-G01) so `command_execution_id` is populated and execution authority holds.
3. G03 / AMFA-180/184/188 — mount the three UI components into the run dashboard.
4. G03 / AMFA-148 — implement G08 approval-binding drift detection (fingerprint/state/artifact).
5. G03 / evidence — create mandatory startup evidence (gap-map, dependency-status, shared-file-changes, manual-test-report); fix AS_BUILT.md.
6. G03 / all — execute MANUAL_TEST_PLAN (C91) against live stack under Python 3.11.

## 20. Audit Sources

- Git: `git status`, `git branch --show-current`, `git rev-parse HEAD`, `git ls-remote`, `git log --oneline -20`
- Root: `AGENT.md`
- Goal: `goals/03-angular-transform-review/{GOAL,TASK_INDEX,JIRA,ACCEPTANCE,REFERENCES,OWNERSHIP,CURRENT_CODE_MAP,CROSS_GOAL_CONTRACTS,MANUAL_TEST_PLAN}.md`, `tasks/T01..T12,C90..C93`, `manual-tests/MT-*`
- Backend: `domain/transformation.py`, `api/transformation_contracts.py`, `services/transformation_application_service.py`, `api/routes/transformations.py`, `api/router.py`, `repositories/transformation_models.py`, `domain/contracts.py`, `alembic/versions/20260719_07_*`
- Frontend: `api/transformations.ts`, `types/transformation.ts`, `components/{AngularUpdatePanel,TransformationEvidenceViewer,G08ReviewWorkspace}.tsx`, `components/AuthoritativeRunDashboard.tsx`
- Tests: `backend/tests/test_g03_domain.py`, `backend/tests/test_g03_api.py`
- Docs: `docs/capabilities/g03-angular-transform-review/AS_BUILT.md`
- Shared: `goals/shared/contracts/{transformation_result,approved_stage_plan,stage_sandbox_ready,command_execution_record,artifact_ref,durable_event_envelope}.schema.json`, `goals/shared/CONTRACT_REGISTRY.yaml/json`
- Evidence: `completion.json`, `task-results/*.json`
