# G07 — Exact Patch Apply, G11, and Loop Protection: Current Situation

## 1. Goal Identity

| Field | Value |
|---|---|
| Goal ID | G07 |
| Goal name | Exact Patch Apply, G11, and Loop Protection |
| Sprint | Sprint 4 (features S4-F07, S4-F08, S4-F09) |
| Worktree | `/home/ubuntu/amfa-worktrees/07-patch-validation-loop` |
| Branch | `hermes/07-patch-validation-loop` |
| Base SHA | `d759861290c1e76e26c4f2b27bbee9a77a12f0b5` |
| Current HEAD SHA | `477619cbcb2b6f26fcdea72d3f0d38f52de6273d` |
| Remote branch | `origin/hermes/07-patch-validation-loop` (present, matches HEAD) |
| Last audited date | 2026-07-20 |

## 2. Executive Situation

G07 validates/applies only the exact persisted approved repair diff (S4-F07), runs patch preflight / resumes the normal validation pipeline / decides G11 (S4-F08), and stops no-progress repair loops with safe rollback/reconstruction (S4-F09). The backend **domain + application services + API routes exist and unit tests pass (176 under Python 3.11)**. However the branch is **not ready**. The apply is **simulated** (no file is ever written; `fingerprint_after` is random; `checksum_after` is recomputed from the diff, not a real post-state); there is **no persistence** (no repository models/migration for patch ledger, G11 records, or repair chain); **no G07 durable events are emitted** (event enum only); the routes **defeat STALE_STATE_VERSION** (pass `actual_state_version=expected_state_version`) and build a **stub in-memory G11 gate** so binding/stale checks are unenforceable; the routes **bypass `StateTransitionService`**; and all three frontend components are **orphaned** (never rendered). `evidence/completion.json` is **missing** entirely. Biggest current risk: the central deliverable "apply only the exact persisted repair diff" does not actually apply anything or persist evidence, and dependency-status.json falsely claims G04/G06 are available implementations.

## 3. Goal Objective

- **Business:** Validate and apply only the exact persisted approved repair diff; run patch preflight / resume validation / decide G11; stop no-progress loops with rollback or stage reconstruction.
- **Technical:** domain → services → API routes. Controlled-mutation + gate-resume + loop-protection authority.
- **Upstream inputs:** G04 (`stage_validation_summary`), G06 (`repair_proposal`, `repair_review_decision`, `repair_g10_package`) — consumed as **frozen contracts only** (implementations not merged into `goal`).
- **Downstream outputs:** leaf goal; provides `patch_apply_ledger.schema.json` for integration testing.

## 4. Related Jira Features

| Sprint | Feature | Jira ID | Expected capability | Current status |
|---|---|---|---|---|
| S4 | Validate/apply only exact persisted repair diff | AMFA-217 | Apply exact diff + persist + REPAIR_APPLY_* events + UI | PARTIALLY_IMPLEMENTED |
| S4 | Patch preflight, resume validation, decide G11 | AMFA-218 | Preflight + resume + G11 gate + events + UI | PARTIALLY_IMPLEMENTED |
| S4 | Stop no-progress loops; reconstruct/roll back | AMFA-219 | Loop detection + recovery + DUPLICATE_PATCH_REJECTED + UI | PARTIALLY_IMPLEMENTED |

## 5. Related Jira Tasks and Subtasks

| Jira ID | Parent feature | Task description | Expected deliverable | Actual implementation | Status |
|---|---|---|---|---|---|
| AMFA-250 | AMFA-217 | S4-F07-I01 backend domain | Exact-apply domain + safety | `backend/app/domain/patch.py`, `services/patch_apply_service.py` (`PatchSafetyService`, `PatchApplyService.apply_patch`) — **apply simulated** | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-251 | AMFA-217 | S4-F07-I02 db/api/events/artifacts | Persist ledger + REPAIR_APPLY_* events | `api/routes/patches.py::apply_repair_diff` — **in-memory, no repository, no event emit** | PARTIALLY_IMPLEMENTED |
| AMFA-252 | AMFA-217 | S4-F07-I03 frontend | Apply UI | `frontend/src/components/RepairApplyPanel.tsx`, `api/patches.ts` — **not imported/rendered** | PARTIALLY_IMPLEMENTED |
| AMFA-253 | AMFA-217 | S4-F07-I04 tests/security/docs | Tests + docs | `test_patch_apply_service.py` (66 pass); no docs; task-result missing | PARTIALLY_IMPLEMENTED |
| AMFA-254 | AMFA-218 | S4-F08-I01 backend domain | Preflight + G11 gate service | `services/repair_validation_service.py` (`PatchPreflightValidator`, `G11GateService`) | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-255 | AMFA-218 | S4-F08-I02 db/api/events | Persist preflight/G11 + events | `api/routes/patches.py::validate_repair`/`decide_g11` — **in-memory stub, no DB/events** | PARTIALLY_IMPLEMENTED |
| AMFA-256 | AMFA-218 | S4-F08-I03 frontend | Validation/G11 UI | `frontend/src/components/RepairValidationTimeline.tsx` — **orphaned** | PARTIALLY_IMPLEMENTED |
| AMFA-257 | AMFA-218 | S4-F08-I04 tests/security/docs | Tests + docs | `test_repair_validation_service.py` (52 pass); no docs; task-result missing | PARTIALLY_IMPLEMENTED |
| AMFA-258 | AMFA-219 | S4-F09-I01 backend domain | Loop-protection service | `services/repair_progress_service.py` (`RepairProgressService`) | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-259 | AMFA-219 | S4-F09-I02 db/api/events | Persist chain/rollback + events | `api/routes/patches.py::get_repair_chain`/`recover_repair_chain` — **in-memory** | PARTIALLY_IMPLEMENTED |
| AMFA-260 | AMFA-219 | S4-F09-I03 frontend | Chain/recovery UI | `frontend/src/components/RepairHistoryView.tsx` — **orphaned** | PARTIALLY_IMPLEMENTED |
| AMFA-261 | AMFA-219 | S4-F09-I04 tests/security/docs | Tests + docs | `test_repair_progress_service.py` (58 pass); no docs | PARTIALLY_IMPLEMENTED |

Closeout tasks:
- C90 (integration tests): PARTIALLY_IMPLEMENTED (in-goal unit only; no cross-goal integration).
- C91 (manual runtime validation): MISSING (scenario templates only; not executed).
- C92 (as-built docs): MISSING (no G07 doc).
- C93 (final audits/completion/push): NOT_APPLICABLE (no `evidence/completion.json` populated; branch pushed but completion unmet).

## 6. Acceptance Criteria Status

| Acceptance criterion | Expected behavior | Current evidence | Status | Gap |
|---|---|---|---|---|
| S4-F07 Happy path | apply exact diff, persist, emit events, UI | `apply_patch` returns result; **no persist, no event** | FAIL | no DB write/events |
| S4-F07 Stale state | STALE_STATE_VERSION | route passes `actual=expected` → check never fails | FAIL | stale defeated |
| S4-F07 Persistence | patch ledger, fingerprints, events | no model/migration for apply | FAIL | persistence absent |
| S4-F07 Evidence | SHA-256 artifacts retrievable | in-memory string refs, not written | FAIL | no artifact persistence |
| S4-F07 Frontend | all states | `RepairApplyPanel` present, not rendered | FAIL | not wired |
| S4-F08 Happy path | preflight, emit event, resume | `validate_repair` in-memory; no event/resume | FAIL | no event |
| S4-F08 Stale/Missing approval | STALE_STATE_VERSION; transition rejects | stub gate seeded from request; routes bypass transition_service | FAIL | unenforceable |
| S4-F08 Approval binding | replay of changed decision = stale | logic present, not reachable | PARTIAL | not reachable |
| S4-F09 Happy path | detect loop, emit, recover | in-memory; route builds empty chain | FAIL | no persistence/event |
| S4-F09 Persistence | counters, rollback/reconstruction | no model | FAIL | persistence absent |
| All: frontend states | distinct states | components present, not rendered | FAIL | not wired |
| Closeout | completion.json + audits + docs | no completion.json; no docs | FAIL | missing |

## 7. Actual Backend Implementation

| File | Symbols | Responsibility | Jira task | Verification |
|---|---|---|---|---|
| `backend/app/domain/patch.py` | `PatchApplyStatus`, `PatchSafetyReport`, `PatchLedgerEntry`, `parse_unified_diff` | Patch domain + parser | AMFA-250 | unit tests (not run here) |
| `backend/app/services/patch_apply_service.py` | `PatchSafetyService`, `PatchApplyService.apply_patch` | Safety + apply (**simulated**) | AMFA-250 | logic present; apply simulated |
| `backend/app/domain/repair_validation.py` | `G11Package`, `G11GateRecord`, `PatchPreflightReport` | Validation/G11 domain | AMFA-254 | present |
| `backend/app/services/repair_validation_service.py` | `PatchPreflightValidator`, `G11GateService`, `RepairValidationOrchestrator` | Preflight + G11 | AMFA-254 | present (in-memory) |
| `backend/app/domain/repair_progress.py` | `RepairChainProgress`, `compare_failure_sets` | Loop detection | AMFA-258 | present |
| `backend/app/services/repair_progress_service.py` | `RepairProgressService` | Loop detection/recovery | AMFA-258 | present (in-memory) |
| `backend/app/api/routes/patches.py` | `apply_repair_diff`, `validate_repair`, `decide_g11`, `get_repair_chain`, `recover_repair_chain` | G07 HTTP routes | AMFA-251/255/259 | registered; in-memory, no DB/events |
| `backend/app/api/patch_contracts.py` | request/response models | API contracts | all | present |
| `backend/app/domain/contracts.py:357-376` | `REPAIR_APPLY_*`, `PATCH_PREFLIGHT_COMPLETED`, `G11_*`, `DUPLICATE_PATCH_REJECTED` | Event enum (defined only) | all | never emitted |
| `backend/app/services/production_preflight_service.py` | `ProductionPreflightService` | **G01** durable preflight (real) | not G07 | real DB+events; G01 scope |

## 8. Actual Frontend Implementation

| File | Component/API/type | Responsibility | Jira task | Wired into UI |
|---|---|---|---|---|
| `frontend/src/api/patches.ts` | API client (apply/validate/decideG11/getChain/recover) | G07 client | AMFA-252/256/260 | YES (client) |
| `frontend/src/components/RepairApplyPanel.tsx` | RepairApplyPanel | S4-F07 UI | AMFA-252 | **NO** (no import in app/pages) |
| `frontend/src/components/RepairValidationTimeline.tsx` | Timeline | S4-F08 UI | AMFA-256 | **NO** |
| `frontend/src/components/RepairHistoryView.tsx` | View | S4-F09 UI | AMFA-260 | **NO** |
| `frontend/src/app/preflights/[preflightId]/page.tsx` | Page | G01 preflight UI | not G07 | YES (G01 only) |

No G07 component tests exist.

## 9. API and Event Coverage

### APIs

| Method | Path | Purpose | Jira task | Implemented | Tested |
|---|---|---|---|---|---|
| POST | `/api/v1/runs/{run_id}/repair-proposals/{proposal_id}/apply` | Apply exact diff | AMFA-250/251 | Yes (in-memory) | No API test |
| GET | `…/apply-result` | Get apply result | AMFA-251 | Yes (stub) | No |
| POST | `/api/v1/runs/{run_id}/repair-attempts/{attempt_id}/validate` | Preflight+G11 | AMFA-254/255 | Yes (in-memory) | No |
| GET | `…/validation` | Get validation | AMFA-255 | Yes (stub) | No |
| POST | `/api/v1/runs/{run_id}/approvals/G11/decisions` | G11 decision | AMFA-255 | Yes (stub gate) | No |
| GET | `/api/v1/runs/{run_id}/repair-chains/{chain_id}` | Chain state | AMFA-258/259 | Yes (in-memory) | No |
| POST | `…/repair-chains/{chain_id}/recover` | Recover | AMFA-259 | Yes (in-memory) | No |

### Events

| Event | Trigger | Jira task | Emitted | Payload verified |
|---|---|---|---|---|
| REPAIR_APPLY_STARTED/APPLIED/REJECTED_STALE/REJECTED_UNSAFE/FAILED | patch apply | AMFA-251 | **NO** (enum only) | N/A |
| PATCH_PREFLIGHT_COMPLETED | preflight | AMFA-255 | **NO** | N/A |
| REPAIR_VALIDATION_STARTED/COMPLETED/FAILED | validation | AMFA-255 | **NO** | N/A |
| G11_CREATED/APPROVED/REJECTED/STALE/EXPIRED | G11 | AMFA-255 | **NO** | N/A |
| DUPLICATE_PATCH_REJECTED/NO_PROGRESS_DETECTED/REPAIR_ROLLED_BACK/STAGE_RECONSTRUCTED/ATTEMPT_LIMIT_REACHED | loop | AMFA-259 | **NO** | N/A |

## 10. Persistence and Migration Status

| Table/model | Migration | Purpose | Jira task | Status |
|---|---|---|---|---|
| (none for patch apply) | — | patch ledger / post-fingerprint | AMFA-251 | **MISSING** |
| (none for G11 gate) | — | G11 records | AMFA-255 | **MISSING** |
| (none for repair chain) | — | attempt/rollback/reconstruction | AMFA-259 | **MISSING** |
| `preflights`/`approval_gates`/`user_decisions`/`preflight_events` (G01) | `20260714_05_production_preflight.py` | G01 durable preflight | not G07 | PRESENT (G01 scope) |

- Alembic head = `20260719_06`; **no G07 migration**. No conflicts.
- Idempotency persistence: none — `apply_repair_diff` generates fresh id and always passes `previous_idempotency_match=False`; no duplicate detection store.
- Stale-state persistence: none for G07; enforcement bypassed in route.

## 11. Automated Test Situation

| Test file | Scope | Collected tests | Passing | Failing | Jira coverage |
|---|---|---|---|---|---|
| `backend/tests/test_patch_apply_service.py` | PatchSafety/Apply unit + security | 66 | 66 | 0 | AMFA-250/253 |
| `backend/tests/test_repair_validation_service.py` | preflight, G11, orchestrator | 52 | 52 | 0 | AMFA-254/257 |
| `backend/tests/test_repair_progress_service.py` | loop detection, recovery | 58 | 58 | 0 | AMFA-258/261 |
| frontend `components/__tests__/*` | G07 component tests | none | — | — | AMFA-252/256/260 |

Executed commands:
- `cd /home/ubuntu/amfa-worktrees/07-patch-validation-loop && python3.11 -m pytest test_patch_apply_service.py test_repair_validation_service.py test_repair_progress_service.py` → **176 passed** (reviewer).
- Audit env default py3.10 fails collection (`datetime.UTC`).
- No API/integration tests for G07 routes. `current-state-gap-map.json` claims "all 176 tests pass" — total is accurate, but only unit tests; no integration.

## 12. Manual Test Situation

| Manual scenario | Documented | Executed | Result | Evidence |
| --------------- | ---------- | -------- | ------ | -------- |
| MT-001 S4-F07 | Yes | No | — | documented only |
| MT-002 S4-F08 | Yes | No | — | documented only |
| MT-003 S4-F09 | Yes | No | — | documented only |
| MT-900 integrated happy path | Yes | No | — | documented only |
| MT-910 stale/idempotency/reconnect | Yes | No | — | documented only |
| MT-920 security/a11y/observability | Yes | No | — | documented only |

All documented; **none executed** (C91 not performed; scenario templates only).

## 13. Evidence Situation

| Evidence file | Purpose | Current | Accurate | Notes |
| ------------- | ------- | ------- | -------- | ----- |
| `evidence/completion.json` | Completion gate | **MISSING** (only unfilled template) | N/A | blocking for branch_ready/push |
| `evidence/current-state-gap-map.json` | Gap map | present | INACCURATE | `base_sha` `709495c` (≠ actual `d759861`); all gaps CLOSED though persistence/events/wiring absent |
| `evidence/dependency-status.json` | Dep status | present | INACCURATE | claims G04/G06 "available" (location goal branch) — implementations not merged; only frozen contracts |
| `evidence/shared-file-changes.json` | Shared edits | present | Accurate | lists router.py, contracts.py only |
| `evidence/task-results/01..12*.json` | 12 subtask results | present | self-reported | all PASS; AMFA-253/257 have no task-result file |

## 14. Dependency Situation

### Upstream dependencies

| Goal/feature | Required capability | Current availability | Impact |
| ------------ | ------------------- | -------------------- | ------ |
| G04 (`stage_validation_summary`) | resume-through-validation input | **frozen contract only**; implementation not merged into `goal` | resume-through-G11 not runtime-verifiable |
| G06 (`repair_proposal`/`repair_review_decision`/`repair_g10_package`) | exact diff to apply | **frozen contract only**; G06 not merged; G07 simulates proposals | apply operates on simulated proposals |
| Real file apply | workspace-level mutation | delegated to G10 runtime (absent in-branch) | "exact patch apply" simulated end-to-end |

### Downstream consumers

| Goal/feature | Capability consumed | Contract provided | Readiness |
| ------------ | ------------------- | ----------------- | --------- |
| None (leaf) | — | `patch_apply_ledger.schema.json` | provided for integration testing |

## 15. Known Issues and Gaps

| ID | Severity | Description | Jira impact | Owner | Required action |
| -- | -------- | ----------- | ----------- | ----- | --------------- |
| K1 | BLOCKER | No persistence for patch apply / G11 / repair chain (no models/migration) | AMFA-251/255/259 | G07 | add repository models + migration; persist in routes |
| K2 | BLOCKER | G07 durable events never emitted | all | G07 | wire event append in services/routes |
| K3 | CRITICAL | `apply_repair_diff` passes `actual_state_version=expected` & `current_fingerprint=expected` → STALE/fingerprint checks defeated | AMFA-217/251 | G07 | load actual state before compare |
| K4 | CRITICAL | `decide_g11` builds in-memory stub gate from request → G11 binding/stale unreachable | AMFA-218/255 | G07 | load real gate record from DB |
| K5 | MAJOR | G07 routes bypass `transition_service.py`; no gate enforcement | AMFA-217/218 | G07 | integrate Transition Service |
| K6 | MAJOR | Frontend components orphaned (not rendered) | AMFA-252/256/260 | G07 | import/compose in dashboard |
| K7 | MAJOR | No `evidence/completion.json`; push criteria unmet | all | G07 | generate + validate |
| K8 | MAJOR | No as-built docs | closeout | G07 | run C92 |
| K9 | MINOR | gap-map wrong base_sha + false "all pass" | evidence | G07 | correct |
| K10 | MINOR | G04/G06 not actually consumed despite "available" status | dependency | G07 | integrate or mark BLOCKED_UPSTREAM |
| K11 | INFO | Manual validation (C91) not executed | closeout | G07 | execute MT-001..920 |

## 16. Goal Completion Matrix

| Dimension                     | Status | Evidence |
| ----------------------------- | ------ | -------- |
| Backend (domain/services)     | Partial | in-memory logic present; apply simulated |
| Frontend                      | Partial | clients + components present; components not wired; no tests |
| API contracts                 | Partial | routes registered; in-memory stubs only |
| Persistence                   | MISSING | no G07 models/migration |
| Events                        | MISSING | event enum defined, never emitted |
| Automated tests               | Partial (verified) | 176 unit tests pass; no API/integration |
| Manual runtime tests          | MISSING | 6 documented, none executed |
| Security controls             | Partial | safety checks coded but bypassed by route (K3/K4) |
| Documentation                 | MISSING | no as-built docs |
| Evidence                      | Partial | gap-map/dependency inaccurate; completion.json missing |
| Upstream integration          | MISSING | G04/G06 not consumed in code |
| Downstream contract readiness | N/A | leaf; schema provided |

## 17. Jira Completion Summary

| Category                | Total | Complete | Partial | Blocked | Missing |
| ----------------------- | ----: | -------: | ------: | ------: | ------: |
| Features                |     3 |        0 |       3 |       0 |       0 |
| Implementation subtasks |    12 |        0 |      12 |       0 |       0 |
| Closeout tasks          |     4 |        0 |       1 |       0 |       3 |
| Acceptance criteria     |    13 |        0 |       1 |       0 |      12 |

(Subtasks all Partial — domain verified-not-runtime; db/api/events/frontend partial. Closeout: C90 Partial; C91 Missing; C92 Missing; C93 N/A.)

## 18. Final Status

| Field                  | Value |
| ---------------------- | ----- |
| `branch_ready`         | false |
| `harness_ready`        | false |
| `integration_verified` | false |
| `jira_complete`        | false |
| Reviewer verdict       | Backend domain/API/unit tests are genuinely implemented and green, but not branch-ready: apply is simulated, persistence faked, frontend orphaned, completion.json absent, and dependency-status falsely claims upstream implementations available |
| Pushed                 | true |
| Remote SHA             | `477619cbcb2b6f26fcdea72d3f0d38f52de6273d` |

## 19. Recommended Next Actions

1. G07 / AMFA-251/255/259 — add repository models + Alembic migration; persist patch ledger/G11/chain and emit REPAIR_APPLY_*/PATCH_PREFLIGHT_COMPLETED/G11_*/DUPLICATE_PATCH_REJECTED (K1, K2).
2. G07 / AMFA-251/255 — load actual state before STALE/fingerprint checks; load real G11 gate record from DB (K3, K4).
3. G07 / AMFA-217/218 — integrate `StateTransitionService` so gate enforcement + resume work (K5).
4. G07 / AMFA-252/256/260 — mount components into the run dashboard (K6).
5. G07 / evidence — generate `completion.json` (validate against `goal_completion.schema.json`); add as-built docs; fix gap-map base_sha (K7–K9).
6. G07 / dependency — integrate or honestly mark G04/G06 BLOCKED_UPSTREAM (K10).

## 20. Audit Sources

- Git: `git log/status/rev-parse/branch --show-current/branch -r`, `git diff --stat d759861..HEAD`, `git ls-tree goal backend/app`
- Root: `AGENT.md`
- Goal: `goals/07-patch-validation-loop/{GOAL,TASK_INDEX,JIRA,ACCEPTANCE,OWNERSHIP,CROSS_GOAL_CONTRACTS,REFERENCES,CURRENT_CODE_MAP,MANUAL_TEST_PLAN}.md`, `tasks/T01..T12,C90..C93`, `manual-tests/MT-*`, `evidence-templates/completion.json`
- Backend: `domain/{patch,repair_validation,repair_progress,contracts}.py`, `services/{patch_apply_service,repair_validation_service,repair_progress_service,production_preflight_service}.py`, `api/{router,patch_contracts}.py`, `api/routes/{patches,preflights}.py`, `state/transition_service.py`, `repositories/preflight_models.py`, `alembic/versions/*`
- Frontend: `api/patches.ts`, `components/{RepairApplyPanel,RepairValidationTimeline,RepairHistoryView}.tsx`, `app/preflights/*`, `components/__tests__/*`
- Tests: `backend/tests/{test_patch_apply_service,test_repair_validation_service,test_repair_progress_service,test_production_preflight,test_preflight_events,test_preflight_service}.py`
- Shared: `goals/shared/contracts/{patch_apply_ledger,stage_validation_summary,repair_proposal,repair_g10_package,repair_review_decision,durable_event_envelope}.schema.json`, `goal_completion.schema.json`, `GOAL_INDEX.yaml`
