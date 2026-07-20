# G05 — Failure Evidence, C-Lite, and Repair Context: Current Situation

## 1. Goal Identity

| Field | Value |
|---|---|
| Goal ID | G05 |
| Goal name | Failure Evidence, C-Lite, and Repair Context |
| Sprint | Sprint 4 (features S4-F01, S4-F02, S4-F03) |
| Worktree | `/home/ubuntu/amfa-worktrees/05-failure-diagnostics-context` |
| Branch | `hermes/05-failure-diagnostics-context` |
| Base SHA | `d759861290c1e76e26c4f2b27bbee9a77a12f0b5` |
| Current HEAD SHA | `d6edf942a745e414ab09d758cd1f0d4aa53820ae` |
| Remote branch | `origin/hermes/05-failure-diagnostics-context` (present, matches HEAD) |
| Last audited date | 2026-07-20 |

## 2. Executive Situation

G05 captures immutable `FailureEvidence` from failed commands, routes failures with deterministic C-Lite classification, and builds a bounded, sanitized `RepairContextPack`. The backend domain layer for all three features is implemented and unit-verified (113 domain tests pass under Python 3.11). However the branch is **not ready and has blocking defects**. The Alembic chain has **two heads** (`20260719_07_g05` and `20260719_09_g05`, both deriving `failures`/`failure_diagnostics` from the same parent) so `alembic upgrade head` fails. API integration tests **fail** (5 failed, 8 errored) due to malformed fingerprint fixtures. A `repair_context_repository` bug stores `run_id = failure_id`, breaking retrieval. Two of three frontend components (`FailureRouteCard`, `ContextInspector`) are **missing** and the one present (`FailureEvidenceViewer`) is unwired. `completion.json` is stale (head_sha ≠ HEAD, `automated_tests:PASS` is false) and the worktree is dirty. Biggest current risk: the forked migration chain plus the unfixed fingerprint test defect will hard-fail on integration.

## 3. Goal Objective

- **Business:** Capture immutable failure evidence, classify deterministically with C-Lite, and assemble a bounded sanitized `RepairContextPack` for repair agents — without repository-wide browsing.
- **Technical:** FastAPI/SQLAlchemy control plane (domain → service → repository → API → events → Alembic).
- **Upstream inputs:** G01 (`command_execution_record`), G04 (`stage_validation_summary`, `artifact_ref`, `durable_event_envelope`) — consumed as **frozen contracts only** (no live integration).
- **Downstream outputs:** `failure_evidence`, `failure_route`, `repair_context_pack` schemas for G06/G10.

## 4. Related Jira Features

| Sprint | Feature | Jira ID | Expected capability | Current status |
|---|---|---|---|---|
| S4 | Capture FailureEvidence + parse deterministic diagnostics | AMFA-211 | Immutable failure evidence, parsers, origin compare, artifact registration | PARTIALLY_IMPLEMENTED |
| S4 | Route failures with C-Lite + env/retry actions | AMFA-212 | Deterministic C-Lite classification, remediation checklist, retry | PARTIALLY_IMPLEMENTED |
| S4 | Build/inspect bounded sanitized RepairContextPack | AMFA-213 | Sanitized pack, selection reasons, checksums, redaction, forbidden-action policy | PARTIALLY_IMPLEMENTED |

## 5. Related Jira Tasks and Subtasks

| Jira ID | Parent feature | Task description | Expected deliverable | Actual implementation | Status |
|---|---|---|---|---|---|
| AMFA-226 | AMFA-211 | S4-F01-I01 backend domain | Failure evidence domain | `backend/app/domain/failure.py`, `services/failure_evidence_builder.py` | IMPLEMENTED_AND_VERIFIED |
| AMFA-227 | AMFA-211 | S4-F01-I02 db/api/events/artifacts | Persist/expose + API + events + migration | `repositories/failure_repository.py`, `api/routes/failures.py`, `models::FailureModel`, migrations `20260719_07_g05`/`20260719_06_g05` | PARTIALLY_IMPLEMENTED |
| AMFA-228 | AMFA-211 | S4-F01-I03 frontend | Capture UX | `frontend/src/components/FailureEvidenceViewer.tsx` (NOT wired into dashboard) | PARTIALLY_IMPLEMENTED |
| AMFA-229 | AMFA-211 | S4-F01-I04 verify/docs | Tests + docs | domain tests pass; API tests fail; as-built docs absent | PARTIALLY_IMPLEMENTED |
| AMFA-230 | AMFA-212 | S4-F02-I01 backend domain | C-Lite routing domain | `backend/app/domain/route.py`, `services/clite_router.py` | IMPLEMENTED_AND_VERIFIED |
| AMFA-231 | AMFA-212 | S4-F02-I02 db/api/events/artifacts | Persist/expose routing + API + events | `route_repository.py`, `api/routes/routing.py`, `models::FailureRouteModel`, migration `20260719_08_g05` | PARTIALLY_IMPLEMENTED |
| AMFA-232 | AMFA-212 | S4-F02-I03 frontend | Routing UX | **`FailureRouteCard` component NOT FOUND** | MISSING |
| AMFA-233 | AMFA-212 | S4-F02-I04 verify/docs | Tests + docs | API tests fail; docs absent | PARTIALLY_IMPLEMENTED |
| AMFA-234 | AMFA-213 | S4-F03-I01 backend domain | RepairContextPack domain | `backend/app/domain/repair_context.py`, `services/repair_context_builder.py` | IMPLEMENTED_AND_VERIFIED |
| AMFA-235 | AMFA-213 | S4-F03-I02 db/api/events/artifacts | Persist/expose pack + API + events | `repair_context_repository.py`, `api/routes/repair_context.py`, `models::RepairContextPackModel`, migration `20260719_09_g05` | PARTIALLY_IMPLEMENTED |
| AMFA-236 | AMFA-213 | S4-F03-I03 frontend | Context inspector UX | **`ContextInspector` component NOT FOUND** | MISSING |
| AMFA-237 | AMFA-213 | S4-F03-I04 verify/docs | Tests + docs | API tests fail; docs absent | PARTIALLY_IMPLEMENTED |

Closeout tasks (from `evidence/task-results/`):
- C90 (integration tests): BLOCKED_BY_EXTERNAL_DEPENDENCY (no G01/G04 runtime).
- C91 (manual runtime validation): BLOCKED_BY_EXTERNAL_DEPENDENCY (not executed).
- C92 (as-built docs): BLOCKED (no as-built doc produced).
- C93 (final audits/completion/push): IMPLEMENTED_NOT_RUNTIME_VERIFIED (completion.json produced with false claims; push/head inconsistent).

## 6. Acceptance Criteria Status

| Acceptance criterion | Expected behavior | Current evidence | Status | Gap |
|---|---|---|---|---|
| S4-F01 Happy path | capture + persist + FAILURE_CAPTURED + UI | `failures.py::capture_failure_evidence` exists; API test FAILS (422) | FAILING | API test fixture fingerprint invalid → 422 |
| S4-F01 Persistence | failure + diagnostics + artifacts + events | `FailureModel`/`FailureDiagnosticModel`; repo tests ERROR | PARTIAL | migration dual-head (K1) |
| S4-F01 Evidence | SHA-256 artifacts | `failure_evidence_builder._register_artifacts` | PARTIAL | not verified by passing test |
| S4-F01 Frontend | all UI states | `FailureEvidenceViewer` renders but NOT wired | PARTIAL | not integrated |
| S4-F02 Happy path | classify + persist + FAILURE_CLASSIFIED + UI | `routing.py::classify_failure`; test FAILS | FAILING | not runtime-verified |
| S4-F02 Frontend | all UI states | **no `FailureRouteCard`** | MISSING | frontend absent |
| S4-F03 Happy path | build pack + persist + REPAIR_CONTEXT_CREATED + UI | `repair_context.py::build_repair_context`; test FAILS; `run_id=failure_id` bug | FAILING | K2 |
| S4-F03 Frontend | all UI states | **no `ContextInspector`** | MISSING | frontend absent |
| S4-F03 Evidence | sanitized pack, redaction, forbidden policy | `SecretSanitizer`, `ContextBudgetTracker`, `ForbiddenActionPolicy` | PARTIAL | not verified |
| S4-F01/02/03 Invalid input / Stale state / Backend failure | stable errors, STALE_STATE_VERSION | error/transition paths coded | PARTIAL | not covered by passing test |

## 7. Actual Backend Implementation

| File | Symbols | Responsibility | Jira task | Verification |
|---|---|---|---|---|
| `backend/app/domain/failure.py` | `FailureEvidence`, `FailureFingerprintService`, `OriginComparator`, `ParserRegistry` | Failure domain + origin compare | AMFA-226 | Unit tests pass (py3.11) |
| `backend/app/services/failure_evidence_builder.py` | `FailureEvidenceBuilder`, 6 stub parsers | Build evidence | AMFA-226 | Unit tests pass |
| `backend/app/domain/route.py` | `CLiteRuleRegistry`, `FailureRouteDecision`, `RemediationChecklist` | C-Lite domain | AMFA-230 | Unit tests pass |
| `backend/app/services/clite_router.py` | `CLiteRouter`, retry policy | Routing service | AMFA-230 | Unit tests pass |
| `backend/app/domain/repair_context.py` | `RepairContextPack`, `SecretSanitizer`, `ContextBudgetTracker`, `ForbiddenActionPolicy` | Repair context domain | AMFA-234 | Unit tests pass |
| `backend/app/services/repair_context_builder.py` | `RepairContextPackBuilder` | Build pack | AMFA-234 | Unit tests pass |
| `backend/app/repositories/failure_repository.py` | `FailureRepository` | Persist failures | AMFA-227 | repo tests ERROR |
| `backend/app/repositories/route_repository.py` | `RouteRepository` | Persist route decisions | AMFA-231 | API tests fail |
| `backend/app/repositories/repair_context_repository.py` | `RepairContextRepository` | Persist packs | AMFA-235 | tests fail; **`run_id=failure_id` bug** |
| `backend/app/api/routes/failures.py` | `capture_failure_evidence`, `get_failure_evidence` | Failure API | AMFA-227 | API test fails; GET path mismatch |
| `backend/app/api/routes/routing.py` | `classify_failure`, `get_route_decision`, `retry_failure` | Routing API | AMFA-231 | API test fails |
| `backend/app/api/routes/repair_context.py` | `build_repair_context`, `get_repair_context` | Repair context API | AMFA-235 | API test fails |
| `backend/app/services/parsers.py` | alternate parser set | DEAD CODE (incompatible signature) | — | not imported |

## 8. Actual Frontend Implementation

| File | Component/API/type | Responsibility | Jira task | Wired into UI |
|---|---|---|---|---|
| `frontend/src/api/failures.ts` | API client (capture/get/classify/retry/build/get) | G05 API client | AMFA-228/231/236 | NO (no callers) |
| `frontend/src/types/generated/api.ts` | `FailureEvidenceDto`, `FailureRouteDto`, `RepairContextPackDto` | TS types | AMFA-228/231/236 | YES (types present) |
| `frontend/src/components/FailureEvidenceViewer.tsx` | Failure evidence viewer | S4-F01 UI | AMFA-228 | NO (not imported by dashboard/hooks) |
| `frontend/src/components/FailureRouteCard.tsx` | — | S4-F02 UI | AMFA-232 | MISSING (file absent) |
| `frontend/src/components/ContextInspector.tsx` | — | S3-F03 UI | AMFA-236 | MISSING (file absent) |
| `frontend/src/hooks/useMigrationEvents.ts` | SSE handlers | G05 events projection | AMFA-228/231/236 | NO G05 event handling added |

## 9. API and Event Coverage

### APIs

| Method | Path | Purpose | Jira task | Implemented | Tested |
|---|---|---|---|---|---|
| POST | `/runs/{run_id}/commands/{command_id}/failure-evidence` | Capture failure evidence | AMFA-227 | Yes | FAIL (422 on bad fixture) |
| GET | `/runs/{run_id}/failures/{failure_id}` | Get failure evidence | AMFA-227 | Yes (path mismatch: frontend calls `/runs/{runId}/failures/{id}` with `{run_id}` seg) | FAIL/ERROR |
| POST | `/runs/{run_id}/failures/{failure_id}/classify` | C-Lite classify | AMFA-231 | Yes | FAIL |
| GET | `/runs/{run_id}/failures/{failure_id}/route` | Get route decision | AMFA-231 | Yes | FAIL |
| POST | `/runs/{run_id}/failures/{failure_id}/retry` | Schedule retry | AMFA-231 | Yes | FAIL |
| POST | `/runs/{run_id}/failures/{failure_id}/repair-context` | Build pack | AMFA-235 | Yes | FAIL |
| GET | `/runs/{run_id}/repair-contexts/{context_id}` | Get pack | AMFA-235 | Yes (retrieval broken by run_id bug) | FAIL/ERROR |

All routes registered in `router.py` (unversioned + `/api/v1`). All 6 G05 API tests fail/error under py3.11.

### Events

| Event | Trigger | Jira task | Emitted | Payload verified |
|---|---|---|---|---|
| FAILURE_CAPTURED | capture step 6 | AMFA-227 | Yes | Not verified (API test fails) |
| FAILURE_DIAGNOSTICS_PARSED | after capture | AMFA-227 | Yes | Not verified |
| FAILURE_CLASSIFIED | classify step 5 | AMFA-231 | Yes | Not verified |
| EXTERNAL_RETRY_SCHEDULED | retry step 5 | AMFA-231 | Yes | Not verified |
| REPAIR_CONTEXT_CREATED/BLOCKED | build_repair_context | AMFA-235 | Yes (conditional) | Not verified |
| ENVIRONMENT_ACTION_REQUIRED | — | AMFA-212 | **NO** (declared, never emitted) | N/A |
| DIAGNOSTIC_HOLD_ENTERED | — | AMFA-212 | **NO** (declared, never emitted) | N/A |

## 10. Persistence and Migration Status

| Table/model | Migration | Purpose | Jira task | Status |
|---|---|---|---|---|
| `failures`, `failure_diagnostics` | `20260719_07_g05` (rev 07, down 06) AND `20260719_06_g05` | Failure evidence | AMFA-227 | **DUPLICATE** (two heads create same tables) |
| `failure_routes`, `failure_attempts` | `20260719_08_g05` (down 07) | Routing | AMFA-231 | OK (model) |
| `repair_context_packs` | `20260719_09_g05` (down 08) | Pack | AMFA-235 | OK (model); retrieval bug |

- **BLOCKER:** `alembic heads` returns **TWO heads** (`20260719_07_g05` and `20260719_09_g05`); both `20260719_06_g05` and `20260719_07_g05` create identical `failures`/`failure_diagnostics` from same parent → `alembic upgrade head` refuses without `--head`.
- Idempotency: `failures` UNIQUE(run_id,idempotency_key); `RepairContextPackModel` UNIQUE(run_id,failure_id,repair_attempt) + repo idempotency check. Present.
- **MAJOR bug:** `repair_context_repository.save_context_pack` stores `run_id = pack.failure_id` → `get_repair_context` (filters by real run_id) returns CONTEXT_NOT_FOUND.

## 11. Automated Test Situation

| Test file | Scope | Collected tests | Passing | Failing | Jira coverage |
|---|---|---|---|---|---|
| `test_failure_evidence_builder_s4_f01_i01.py` | FailureEvidence domain + parsers | ~29 | 29 | 0 | AMFA-226 |
| `test_clite_router_s4_f02_i01.py` | C-Lite routing domain | ~50 | 50 | 0 | AMFA-230 |
| `test_repair_context_builder_s4_f03_i01.py` | RepairContextPack domain + sanitizer | ~34 | 34 | 0 | AMFA-234 |
| `test_failure_persistence_api_s4_f01_i02.py` | Failure persistence + API | — | partial | 4F/4E | AMFA-227 |
| `test_failure_routing_api_s4_f02_i02.py` | Routing API | — | partial | fail | AMFA-231 |
| `test_repair_context_api_s4_f03_i02.py` | Repair-context API | — | partial | 1F/4E | AMFA-235 |
| `frontend/.../FailureEvidenceViewer.test.tsx` | FE component | exists | NOT RUN | — | AMFA-228 |

Executed commands:
- `cd /home/ubuntu/amfa-worktrees/05-failure-diagnostics-context && python3.11 -m pytest <6 G05 test files>` → **domain 113 passed; API 19 passed, 5 failed, 8 errors** (reviewer).
- Root cause of failures: fixtures use invalid fingerprints (`"sha256:"+"a"*62` etc.) rejected by strict `^sha256:[0-9a-f]{64}$` regex.
- `completion.json` `automated_tests:"PASS"` is **FALSE** for API tests.
- App requires Python ≥3.11 (`datetime.UTC`); py3.10 cannot import.

## 12. Manual Test Situation

| Manual scenario | Documented | Executed | Result | Evidence |
| --------------- | ---------- | -------- | ------ | -------- |
| MT-001 S4-F01 | Yes | No | — | no manual-test-report.json |
| MT-002 S4-F02 | Yes | No | — | not executed |
| MT-003 S4-F03 | Yes | No | — | not executed |
| MT-900 integrated happy path | Yes | No | — | not executed |
| MT-910 stale/idempotency/reconnect | Yes | No | — | not executed |
| MT-920 security/a11y/observability | Yes | No | — | not executed |

All six documented; **none executed** (C91 not performed).

## 13. Evidence Situation

| Evidence file | Purpose | Current | Accurate | Notes |
| ------------- | ------- | ------- | -------- | ----- |
| `evidence/completion.json` | Completion claim | head_sha `9c5001f` (≠ HEAD `d6edf94`); `automated_tests:PASS` (false); dirty in working tree | NO | stale + inaccurate |
| `evidence/current-state-gap-map.json` | Pre-impl gap map | all criteria MISSING | NO | baseline-only; not updated |
| `evidence/dependency-status.json` | Dependency map | G01/G04 FROZEN_CONTRACT_ONLY | PARTIAL | accurate re frozen-only |
| `evidence/shared-file-changes.json` | Declared shared edits | claims FailureRouteCard/ContextInspector added (absent) | PARTIAL | inaccurate |
| `evidence/task-results/01,02*.json` | Task results | 02 claims PASS/"6 passed" | NO | contradicts API failures |

## 14. Dependency Situation

### Upstream dependencies

| Goal/feature | Required capability | Current availability | Impact |
| ------------ | ------------------- | -------------------- | ------ |
| G01 (command runtime) | `command_execution_record` | FROZEN CONTRACT ONLY (not integrated) | no live G01 call |
| G04 (stage validation seal) | `stage_validation_summary`, `artifact_ref`, `durable_event_envelope` | FROZEN CONTRACT ONLY (not integrated) | no live G04 call |

### Downstream consumers

| Goal/feature | Capability consumed | Contract provided | Readiness |
| ------------ | ------------------- | ----------------- | --------- |
| G06 (depends_on G05) | `failure_evidence`, `failure_route`, `repair_context_pack` | schemas PRESENT | contract-ready; not integrated |

## 15. Known Issues and Gaps

| ID | Severity | Description | Jira impact | Owner | Required action |
| -- | -------- | ----------- | ----------- | ----- | --------------- |
| K1 | BLOCKER | Alembic has two heads; `20260719_06_g05` & `20260719_07_g05` both create `failures`/`failure_diagnostics` → `alembic upgrade head` fails | AMFA-227/231/235 | G05 | delete/merge orphan duplicate migration |
| K2 | MAJOR | `repair_context_repository.save_context_pack` stores `run_id = failure_id` → retrieval broken | AMFA-235 | G05 | store real run_id |
| K3 | MAJOR | API integration tests FAIL (5F/8E) due to invalid fingerprint fixtures | AMFA-227/231/235/229/233/237 | G05 | fix fixtures to `sha256:`+64-hex |
| K4 | CRITICAL | `completion.json` `automated_tests:PASS` false; head_sha ≠ HEAD; file dirty | all | G05 | correct completion evidence before push |
| K5 | MAJOR | Frontend S4-F02/S4-F03 components missing; S4-F01 viewer unwired | AMFA-232/236/228 | G05 | implement + integrate components, SSE handlers |
| K6 | MAJOR | `get_failure_evidence` path mismatch (`/runs/failures/{id}` vs frontend `/runs/{run_id}/failures/{id}`) | AMFA-227 | G05 | add `{run_id}` path param |
| K7 | MINOR | `parsers.py` dead code with incompatible signature | — | G05 | remove or fix & wire |
| K8 | INFO | `ENVIRONMENT_ACTION_REQUIRED`, `DIAGNOSTIC_HOLD_ENTERED` declared but never emitted | AMFA-212 | G05 | emit or drop |
| K9 | MINOR | no as-built docs; C92 not done | closeout | G05 | generate docs |

## 16. Goal Completion Matrix

| Dimension                     | Status | Evidence |
| ----------------------------- | ------ | -------- |
| Backend (domain)              | Verified | 113 domain unit tests pass |
| Backend (API)                 | Partial/Failing | 3 API test files fail/error |
| Frontend                      | Partial | only `FailureEvidenceViewer` exists, unwired; 2 missing |
| API contracts                 | Implemented, not verified | routes registered; tests fail; GET path mismatch |
| Persistence                   | Partial/Broken | dual-head migration; run_id bug |
| Events                        | Partial | 6/8 emitted; 2 declared-never-emitted |
| Automated tests               | Failing (API) | 113 pass (domain), 5F/8E (API); completion.json inaccurate |
| Manual runtime tests          | Blocked | 6 documented, none executed |
| Security controls             | Partial | SecretSanitizer + forbidden policy present; authority by design |
| Documentation                 | Blocked | no as-built docs |
| Evidence                      | Inaccurate | completion.json stale/dirty; gap-map not updated |
| Upstream integration          | Not integrated | G01/G04 frozen-contract-only |
| Downstream contract readiness | Provided, not integrated | 3 schemas provided |

## 17. Jira Completion Summary

| Category                | Total | Complete | Partial | Blocked | Missing |
| ----------------------- | ----: | -------: | ------: | ------: | ------: |
| Features                |     3 |        0 |       3 |       0 |       0 |
| Implementation subtasks |    12 |        3 |       7 |       0 |       2 |
| Closeout tasks          |     4 |        0 |       0 |       4 |       0 |
| Acceptance criteria     |    21 |        0 |      17 |       1 |       2 |

(Subtasks Complete: AMFA-226/230/234. Partial: AMFA-227/228/229/231/233/235/237. Missing: AMFA-232/236. Closeout all Blocked.)

## 18. Final Status

| Field                  | Value |
| ---------------------- | ----- |
| `branch_ready`         | false |
| `harness_ready`        | false |
| `integration_verified` | false |
| `jira_complete`        | false |
| Reviewer verdict       | Domain logic complete & unit-verified, but not branch_ready: dual-head migration, failing API tests, repair-context run_id bug, missing/unwired frontend, inaccurate stale completion evidence |
| Pushed                 | true |
| Remote SHA             | `d6edf942a745e414ab09d758cd1f0d4aa53820ae` |

## 19. Recommended Next Actions

1. G05 — delete/merge the orphan duplicate migration so a single linear Alembic head exists (K1).
2. G05 / AMFA-235 — fix `save_context_pack` to store the real `run_id` (K2).
3. G05 / AMFA-227/231/235 — fix API test fixtures to valid `sha256:`+64-hex fingerprints (K3).
4. G05 / AMFA-232/236/228 — implement `FailureRouteCard`/`ContextInspector` and wire `FailureEvidenceViewer` into the dashboard + SSE (K5).
5. G05 / AMFA-227 — add `{run_id}` path param to `get_failure_evidence` (K6).
6. G05 / evidence — regenerate completion.json at HEAD `d6edf94`; add as-built docs (C92).

## 20. Audit Sources

- Git: `git log/status/rev-parse/branch --show-current`, `git diff --stat`, `git show HEAD:evidence/completion.json`
- Root: `AGENT.md`
- Goal: `goals/05-failure-diagnostics-context/{GOAL,TASK_INDEX,JIRA,ACCEPTANCE,CURRENT_CODE_MAP,CROSS_GOAL_CONTRACTS,OWNERSHIP,REFERENCES,MANUAL_TEST_PLAN}.md`, `manual-tests/MT-*`, `evidence-templates/*`
- Backend: `domain/failure.py`, `domain/route.py`, `domain/repair_context.py`, `services/failure_evidence_builder.py`, `services/clite_router.py`, `services/repair_context_builder.py`, `services/parsers.py`, `repositories/failure_repository.py`, `route_repository.py`, `repair_context_repository.py`, `repositories/models/workflow.py`, `api/routes/{failures,routing,repair_context}.py`, `api/router.py`, `domain/contracts.py`, `alembic/versions/20260719_0{6,7,8,9}_g05_*`
- Frontend: `components/FailureEvidenceViewer.tsx`, `api/failures.ts`, `types/generated/api.ts`, `components/AuthoritativeRunDashboard.tsx`, `hooks/{useMigrationEvents,applyEventToRun}.ts`
- Tests: `backend/tests/test_*s4_f0[123]*.py`
- Shared: `goals/shared/contracts/{failure_evidence,failure_route,repair_context_pack,command_execution_record,stage_validation_summary,artifact_ref,durable_event_envelope}.schema.json`
