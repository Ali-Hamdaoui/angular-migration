# G08 — Reconciliation and Human-in-the-Loop (HITL) Assistant: Current Situation

## 1. Goal Identity

| Field | Value |
|---|---|
| Goal ID | G08 |
| Goal name | Reconciliation and Human-in-the-Loop (HITL) Assistant |
| Sprint | Sprint 4 (features S4-F10, S4-F11) |
| Worktree | `/home/ubuntu/amfa-worktrees/08-reconciliation-assistant` |
| Branch | `hermes/08-reconciliation-assistant` |
| Base SHA | `d759861290c1e76e26c4f2b27bbee9a77a12f0b5` |
| Current HEAD SHA | `08209ff9d4d84d0a92c8f83c469d04d10ad5041d` |
| Remote branch | `origin/hermes/08-reconciliation-assistant` (present, matches HEAD) |
| Last audited date | 2026-07-20 |

## 2. Executive Situation

G08 provides reconciliation of DTO/transport vs canonical/domain models and an HITL assistant for review/escalation/sign-off (S4-F10 + S4-F11). Backend domain/API/services exist and **50 unit tests pass (Python 3.11)**, and frontend (`AssistedReviewPanel`, `ReconciliationDiffView`) is present. The branch is **not ready**. The reconciliation service is **AI-blocked**: `S2-F03` (domain reconciliation model) is **NOT in code**, so `reconcile()` delegates to a fallback heuristic and emits `RECONCILIATION_FALLBACK_USED`. `decide_assistant_action()` **also always returns `request_human_review` on uncertainty** rather than invoking S2-F03. A **latent FK defect (R-001)** in `approval_gates.attempt_id` references `repair_attempts.id` but only `repair_attempts(attempt_id)` exists (no `id` column) — corrupts gate persistence for G04/G06/G07/G08/G09/G10 but is masked because G08 routes are **in-memory** (never persist) and the migration was never tested against the model. The quarantine route **bypasses StateTransitionService** (K2) and `RecoveryService.quarantine()` swallows all errors with a bare `except Exception` (K3). Frontend components are **orphaned** (not imported/rendered). `evidence/completion.json` per-category breakdown is **inaccurate** (claims 21 domain + 11 integration; actual 19 domain + 13 integration) and lists 6 closeout tasks though the file only contains 4; no `evidence/completion.json` owned-by-G08 records were validated for `goal_completion.schema.json`. Manual validation (C91) not executed.

## 3. Goal Objective

- **Business:** Reconcile transport↔domain models and give reviewers an AI-assisted, human-in-the-loop review/escalation/sign-off assistant.
- **Technical:** domain → services → API routes; integration with `approval_gates`/`user_decisions` (G04 transition model); depends on `S2-F03` (domain reconciliation) from prior work.
- **Upstream inputs:** `stage_validation_summary` (G04, frozen contract), `repair_proposal`/`repair_review_decision` (G06, frozen contract), `S2-F03` reconciliation model (NOT in `goal`).
- **Downstream outputs:** consumed by G09/G10 via `reconciliation.schema.json` / `assistant.schema.json`.

## 4. Related Jira Features

| Sprint | Feature | Jira ID | Expected capability | Current status |
|---|---|---|---|---|
| S4 | Reconciliation engine (transport↔domain) | AMFA-220 | S2-F03 model + reconcile + events + API + UI | PARTIALLY_IMPLEMENTED |
| S4 | HITL assistant (review/escalate/sign-off) | AMFA-221 | Assisted decision + escalation + events + API + UI | PARTIALLY_IMPLEMENTED |

## 5. Related Jira Tasks and Subtasks

| Jira ID | Parent feature | Task description | Expected deliverable | Actual implementation | Status |
|---|---|---|---|---|---|
| AMFA-262 | AMFA-220 | S4-F10-I01 backend domain | Reconciliation domain + S2-F03 model | `domain/reconciliation.py` (`TransportReconciliation`, `ReconciliationResult`) — **no S2-F03 AI model**; `reconcile()` heuristic/fallback | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-263 | AMFA-220 | S4-F10-I02 db/api/events | Persist + RECONCILIATION_* events | `api/routes/reconciliation.py` — **in-memory, no repository/events** | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-264 | AMFA-220 | S4-F10-I03 frontend | Diff UI | `frontend/src/components/ReconciliationDiffView.tsx` — **orphaned** | PARTIALLY_IMPLEMENTED |
| AMFA-265 | AMFA-220 | S4-F10-I04 tests/security/docs | Tests + docs | `test_reconciliation_service.py` (29 pass); no docs | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-266 | AMFA-221 | S4-F11-I01 backend domain | Assistant decision/escalation | `domain/assistant.py` (`AssistedDecision`, `EscalationContext`), `services/assistant_service.py` (`AssistedReviewService.decide_assistant_action`) — **always fallback on uncertainty** | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-267 | AMFA-221 | S4-F11-I02 db/api/events | Persist decisions/escalation + events | `api/routes/assistant.py` — **in-memory** | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-268 | AMFA-221 | S4-F11-I03 frontend | Assisted review UI | `frontend/src/components/AssistedReviewPanel.tsx` — **orphaned** | PARTIALLY_IMPLEMENTED |
| AMFA-269 | AMFA-221 | S4-F11-I04 tests/security/docs | Tests + docs | `test_assistant_service.py` (21 pass); no docs | IMPLEMENTED_NOT_RUNTIME_VERIFIED |

Closeout tasks (per completion.json shape):
- C90 (integration tests): PARTIALLY_IMPLEMENTED (in-goal unit only; 13 listed integration entries not executed).
- C91 (manual runtime validation): MISSING (no task-result; scenario templates only).
- C92 (as-built docs): PARTIALLY_IMPLEMENTED (completion.json implies doc `complete:true`; no doc file found).
- C93 (final audits/completion/push): MISSING (completion.json inaccurate; schema not validated).

## 6. Acceptance Criteria Status

| Acceptance criterion | Expected behavior | Current evidence | Status | Gap |
|---|---|---|---|---|
| S4-F10 Happy path | reconcile transport↔domain | `reconcile()` runs heuristic | PARTIAL | S2-F03 not present; RECONCILIATION_FALLBACK_USED instead of model |
| S4-F10 Persist | reconciliation record + events | route in-memory; no repository/events | FAIL | no DB/events |
| S4-F10 Frontend | diff view all states | component present, not rendered | FAIL | not wired |
| S4-F11 Happy path | assisted decision + escalate | `decide_assistant_action` returns action | PARTIAL | always `request_human_review` on uncertainty |
| S4-F11 HITL gate | quarantine→StateTransition | `/quarantine` bypasses transition service | FAIL | K2 |
| S4-F11 Persist | decisions/escalation + events | route in-memory | FAIL | no DB/events |
| S4-F11 Frontend | assisted panel | component present, not rendered | FAIL | not wired |
| All: error handling | typed errors, no bare except | `RecoveryService.quarantine` bare `except Exception` | FAIL | K3 |
| All: persistence integrity | FK valid | `approval_gates.attempt_id→repair_attempts.id` (no `id` col) | FAIL | R-001 latent |
| Closeout | accurate completion.json + docs | inaccurate breakdown; no validated file | FAIL | K4/K5 |

## 7. Actual Backend Implementation

| File | Symbols | Responsibility | Jira task | Verification |
|---|---|---|---|---|
| `backend/app/domain/reconciliation.py` | `TransportReconciliation`, `ReconciliationResult`, `ReconciliationStatus`, `ReconciliationType` | Reconciliation domain | AMFA-262 | present (heuristic) |
| `backend/app/services/reconciliation_service.py` | `ReconciliationService.reconcile` | Reconcile logic | AMFA-262 | AI-blocked → fallback; emits RECONCILIATION_FALLBACK_USED |
| `backend/app/domain/assistant.py` | `AssistedDecision`, `EscalationContext`, `AssistAction` | Assistant domain | AMFA-266 | present |
| `backend/app/services/assistant_service.py` | `AssistedReviewService.decide_assistant_action` | Decide HITL action | AMFA-266 | always `request_human_review` on uncertainty |
| `backend/app/api/routes/reconciliation.py` | `reconcile`, `get_reconciliation` | G08 HTTP routes | AMFA-263 | in-memory |
| `backend/app/api/routes/assistant.py` | `decide_action`, `escalate`, `quarantine` | G08 HTTP routes | AMFA-267 | in-memory; quarantine bypasses transition |
| `backend/app/services/recovery_service.py` | `RecoveryService.quarantine` | Quarantine | AMFA-267 | bare `except Exception` |
| `backend/app/state/transition_service.py` | `StateTransitionService` | Gate enforcement | G04 | present; G08 quarantine bypasses it |
| `backend/app/domain/contracts.py` | `RECONCILIATION_*`, `ASSIST_*` events | Event enum | all | defined; not emitted by G08 |
| `backend/app/repositories/{preflight_models,gates_models}.py` | `ApprovalGate.attempt_id` (FK repair_attempts.id) | Gate persistence | G04 | **R-001**: repair_attempts has no `id` column |

(S2-F03 model: **NOT present** in `goal` — only referenced as missing prior capability.)

## 8. Actual Frontend Implementation

| File | Component/API | Responsibility | Jira task | Wired into UI |
|---|---|---|---|---|
| `frontend/src/api/reconciliation.ts` + `assistant.ts` | Clients | G08 clients | AMFA-264/268 | YES (client) |
| `frontend/src/components/ReconciliationDiffView.tsx` | DiffView | S4-F10 UI | AMFA-264 | **NO** |
| `frontend/src/components/AssistedReviewPanel.tsx` | Panel | S4-F11 UI | AMFA-268 | **NO** |
| `frontend/src/app/(dashboard)/runs/[runId]/assisted-review/page.tsx` | Page | Assisted review page | AMFA-268 | **NO** (page exists, component not imported) |

## 9. API and Event Coverage

### APIs

| Method | Path | Purpose | Jira task | Implemented | Tested |
|---|---|---|---|---|---|
| POST | `/api/v1/runs/{run_id}/reconcile` | Reconcile transport↔domain | AMFA-263 | Yes (in-memory) | No API test |
| GET | `…/reconciliations/{recon_id}` | Get reconciliation | AMFA-263 | Yes (stub) | No |
| POST | `/api/v1/runs/{run_id}/assistant/decide` | Assisted decision | AMFA-267 | Yes (in-memory) | No |
| POST | `…/assistant/escalate` | Escalate | AMFA-267 | Yes (in-memory) | No |
| POST | `…/assistant/quarantine` | Quarantine | AMFA-267 | Yes (bypasses transition) | No |

### Events

| Event | Trigger | Jira task | Emitted | Payload verified |
|---|---|---|---|---|
| RECONCILIATION_STARTED/COMPLETED/FAILED/FALLBACK_USED | reconcile | AMFA-263 | **NO** (enum only; FALLBACK_USED conceptually reached) | N/A |
| ASSIST_DECISION_REQUESTED/COMPLETED/ESCALATED/QUARANTINED/SIGNED_OFF | assistant | AMFA-267 | **NO** | N/A |

## 10. Persistence and Migration Status

- No G08-specific models; reconciliation/assistant data held in-memory.
- **R-001 (latent, HIGH):** `repositories/gates_models.py::ApprovalGate.attempt_id` is a `ForeignKey("repair_attempts.id")` but `repair_attempts` only has `attempt_id` (no `id` PK column). Any real gate persist across G04/G06/G07/G08/G09/G10 would fail FK. Masked now because G08 routes never persist and the 20260719_06 migration was not exercised against the model.
- Alembic head = `20260719_06`; no G08 migration; no conflicts.

## 11. Automated Test Situation

| Test file | Scope | Collected | Passing | Failing | Jira coverage |
|---|---|---|---|---|---|
| `backend/tests/test_reconciliation_service.py` | reconcile + security | 29 | 29 | 0 | AMFA-262/265 |
| `backend/tests/test_assistant_service.py` | decide/escalate + security | 21 | 21 | 0 | AMFA-266/269 |

Executed: `cd /home/ubuntu/amfa-worktrees/08-reconciliation-assistant && python3.11 -m pytest test_reconciliation_service.py test_assistant_service.py` → **50 passed** (reviewer).
- Audit env default py3.10 fails collection (`datetime.UTC`).
- Frontend: no component tests for ReconciliationDiffView/AssistedReviewPanel.
- No API/integration tests. `completion.json` claims 11 integration tests — **none found/executed**.

## 12. Manual Test Situation

| Manual scenario | Documented | Executed | Result | Evidence |
| --------------- | ---------- | -------- | ------ | -------- |
| MT-001 S4-F10 | Yes | No | — | documented only |
| MT-002 S4-F11 | Yes | No | — | documented only |
| MT-900 integrated | Yes | No | — | documented only |
| MT-910 security/a11y/observability | Yes | No | — | documented only |

All documented; **none executed** (C91 not performed).

## 13. Evidence Situation

| Evidence file | Purpose | Current | Accurate | Notes |
| ------------- | ------- | ------- | -------- | ----- |
| `evidence/completion.json` | Completion gate | present (4 closeout) | **INACCURATE** | "feature_subtasks": 30 with `domain_implementation:21, integration_implementation:11` — actual 19 domain + 13 integration; lists 6 closeout tasks but file has 4; no `goal_completion.schema.json` validation |
| `evidence/current-state-gap-map.json` | Gap map | present | PARTIAL | "RECONCILIATION_AI_AVAILABLE": false acknowledged; but still marks all gaps CLOSED |
| `evidence/dependency-status.json` | Dep status | present | PARTIAL | S2-F03 marked not-available/missing (correct); others claim available |
| `evidence/shared-file-changes.json` | Shared edits | present | Accurate | lists contracts.py, router.py |
| `evidence/task-results/*` | subtask results | present | self-reported | all PASS |

## 14. Dependency Situation

### Upstream dependencies

| Goal/feature | Required capability | Current availability | Impact |
| ------------ | ------------------- | -------------------- | ------ |
| S2-F03 (domain reconciliation model) | AI reconcile model | **NOT in `goal`** | G08 reconcile falls back; RECONCILIATION_FALLBACK_USED |
| G04 `stage_validation_summary` | transition model input | frozen contract only | quarantine bypasses transition (K2) |
| G06 `repair_proposal`/`repair_review_decision` | review inputs | frozen contract only | not consumed in code |

### Downstream consumers

| Goal/feature | Capability consumed | Contract provided | Readiness |
| ------------ | ------------------- | ----------------- | --------- |
| G09/G10 | reconciliation + assistant outputs | `reconciliation.schema.json`, `assistant.schema.json` | provided for integration testing |

## 15. Known Issues and Gaps

| ID | Severity | Description | Jira impact | Owner | Required action |
| -- | -------- | ----------- | ----------- | ----- | --------------- |
| R-001 | BLOCKER (latent) | `approval_gates.attempt_id` FK → `repair_attempts.id`, but `repair_attempts` has no `id` column | AMFA-263/267 (shared) | G04/G08 | drop/repoint FK; test migration |
| K2 | CRITICAL | `/quarantine` bypasses StateTransitionService; gate enforcement unenforceable | AMFA-267 | G08 | integrate TransitionService |
| K3 | MAJOR | `RecoveryService.quarantine` bare `except Exception` masks errors | AMFA-267 | G08 | typed error handling |
| F-001 | MAJOR | Frontend components orphaned (not rendered) | AMFA-264/268 | G08 | mount in dashboard/assisted-review page |
| F-002 | MAJOR | `decide_assistant_action` always `request_human_review` on uncertainty (S2-F03 unused) | AMFA-266 | G08 | invoke S2-F03 or mark AI_BLOCKED |
| K4 | MAJOR | No persistence/events for reconciliation/assistant (in-memory only) | AMFA-263/267 | G08 | add repository + emit events |
| K5 | MAJOR | `completion.json` inaccurate (count + closeout list) and not schema-validated | evidence | G08 | correct + validate |
| K6 | MAJOR | No as-built docs; C91 not executed | closeout | G08 | run C91/C92 |
| K7 | MINOR | `current-state-gap-map.json` marks all CLOSED though AI-blocked/unwired | evidence | G08 | reflect reality |

## 16. Goal Completion Matrix

| Dimension                     | Status | Evidence |
| ----------------------------- | ------ | -------- |
| Backend (domain/services)     | Partial | heuristic reconcile + assistant; AI-blocked |
| Frontend                      | Partial | clients + components present; components not wired; no tests |
| API contracts                 | Partial | routes registered; in-memory stubs |
| Persistence                   | MISSING | in-memory only; FK defect R-001 |
| Events                        | MISSING | event enum defined, never emitted |
| Automated tests               | Partial (verified) | 50 unit tests pass; no API/integration |
| Manual runtime tests          | MISSING | documented, none executed |
| Security controls             | Partial | present but bare-except + transition bypass weaken it |
| Documentation                 | MISSING | no as-built doc found/validated |
| Evidence                      | Partial (inaccurate) | completion.json wrong counts |
| Upstream integration          | MISSING | S2-F03 not consumed; G04/G06 not in code |
| Downstream contract readiness | N/A | schemas provided |

## 17. Jira Completion Summary

| Category                | Total | Complete | Partial | Blocked | Missing |
| ----------------------- | ----: | -------: | ------: | ------: | ------: |
| Features                |     2 |        0 |       2 |       0 |       0 |
| Implementation subtasks |     8 |        0 |       8 |       0 |       0 |
| Closeout tasks          |     4 |        0 |       2 |       0 |       2 |
| Acceptance criteria     |    10 |        0 |       2 |       0 |       8 |

(Subtasks: AMFA-262/263/265/266/267/269 IMPLEMENTED_NOT_RUNTIME_VERIFIED; AMFA-264/268 PARTIALLY_IMPLEMENTED. Closeout: C90 Partial, C92 Partial claimed; C91/C93 Missing.)

## 18. Final Status

| Field                  | Value |
| ---------------------- | ----- |
| `branch_ready`         | false |
| `harness_ready`        | false |
| `integration_verified` | false |
| `jira_complete`        | false |
| Reviewer verdict       | Backend + unit tests genuinely implemented and green, but not branch-ready: AI-blocked reconciliation (S2-F03 absent) forces fallback, frontend orphaned, in-memory only with no events, quarantine bypasses the transition gate, an inaccurate completion.json, and a latent approval_gates FK defect that corrupts gate persistence once it is actually used |
| Pushed                 | true |
| Remote SHA             | `08209ff9d4d84d0a92c8f83c469d04d10ad5041d` |

## 19. Recommended Next Actions

1. G08 / R-001 — fix `ApprovalGate.attempt_id` FK (repoint to `repair_attempts.attempt_id` or add PK); exercise the migration against the model.
2. G08 / AMFA-263/267 — add repositories + emit RECONCILIATION_*/ASSIST_* events; persist reconciliation/decision records (K4).
3. G08 / AMFA-267 — route quarantine through `StateTransitionService`; replace bare `except` in `RecoveryService.quarantine` with typed handling (K2, K3).
4. G08 / AMFA-266 — invoke S2-F03 in `decide_assistant_action` or formally declare AI_BLOCKED rather than silently always requesting human review (F-002).
5. G08 / AMFA-264/268 — mount `ReconciliationDiffView`/`AssistedReviewPanel` into the dashboard / assisted-review page (F-001).
6. G08 / evidence — correct and schema-validate `completion.json`; add as-built docs; execute C91 manual validation.

## 20. Audit Sources

- Git: `git log/status/rev-parse/branch --show-current/branch -r`, `git diff --stat d759861..HEAD`, `git ls-tree goal backend/app`
- Root: `AGENT.md`
- Goal: `goals/08-reconciliation-assistant/{GOAL,TASK_INDEX,JIRA,ACCEPTANCE,OWNERSHIP,CROSS_GOAL_CONTRACTS,REFERENCES,CURRENT_CODE_MAP,MANUAL_TEST_PLAN}.md`, `tasks/T01..T08,C90..C93`, `manual-tests/MT-*`, `evidence/completion.json`
- Backend: `domain/{reconciliation,assistant,contracts}.py`, `services/{reconciliation_service,assistant_service,recovery_service}.py`, `api/{router,reconciliation_contracts,assistant_contracts}.py`, `api/routes/{reconciliation,assistant}.py`, `state/transition_service.py`, `repositories/{preflight_models,gates_models}.py`, `alembic/versions/*`
- Frontend: `api/{reconciliation,assistant}.ts`, `components/{ReconciliationDiffView,AssistedReviewPanel}.tsx`, `app/(dashboard)/runs/[runId]/assisted-review/page.tsx`
- Tests: `backend/tests/{test_reconciliation_service,test_assistant_service}.py`
- Shared: `goals/shared/contracts/{reconciliation,assistant,stage_validation_summary,repair_proposal,repair_review_decision,durable_event_envelope}.schema.json`, `goal_completion.schema.json`, `GOAL_INDEX.yaml`
