# G06 — Repair Proposer, Reviewer, and G10: Current Situation

## 1. Goal Identity

| Field | Value |
|---|---|
| Goal ID | G06 |
| Goal name | Repair Proposer, Reviewer, and G10 |
| Sprint | Sprint 4 (features S4-F04, S4-F05, S4-F06) |
| Worktree | `/home/ubuntu/amfa-worktrees/06-repair-agents-g10` |
| Branch | `hermes/06-repair-agents-g10` |
| Base SHA | `d759861290c1e76e26c4f2b27bbee9a77a12f0b5` |
| Current HEAD SHA | `4af15eb5e1165daeaf12931fbb978d8901bf4dd8` |
| Remote branch | `origin/hermes/06-repair-agents-g10` (present, matches HEAD) |
| Last audited date | 2026-07-20 |

## 2. Executive Situation

G06 produces a checksum-bound Repair Proposer candidate, independently reviews it with a non-authoring Reviewer under bounded revision cycles, and gates application behind a human G10 Apply/Reject decision. The backend **domain + application services, API routes, event vocabulary, ORM models, and migration all exist and import cleanly**, and the non-authoring/checksum-binding guarantees are present in code. However the branch is **not ready**. Blocking gaps: (a) the Proposer and Reviewer POST endpoints **never persist** (`ProposerResultModel`/`ReviewDecisionModel` are never instantiated); (b) `RepairProposalService.persist()` is **never called by any route**, so proposals are never created and the G10 gate is unreachable end-to-end; (c) required PROPOSER_*/REVIEWER_* events are never emitted; (d) the Alembic migration head `695779d2b9ee` depends on G05's `20260719_07/08` migrations which are **untracked/uncommitted** in this worktree, breaking `alembic upgrade head` on a clean checkout; (e) **zero G06 automated tests** exist (completion.json `automated_tests:PASS` is false/misleading); (f) all three frontend components are orphaned (not rendered) and `G10ApprovalPanel` imports a non-existent `getG10Package` (build error); (g) `completion.json` head_sha equals the base SHA (never regenerated). Biggest current risk: the G06 migration is coupled to G05's uncommitted migrations, so the feature is non-deployable without G05 merged first, and `completion.json` masks this by reporting head_sha==base.

## 3. Goal Objective

- **Business:** After staged validation fails, produce an AI-authored repair candidate, independently review it, and gate application behind an explicit human G10 decision — no unverified change applied automatically.
- **Technical:** checksum-bound Repair Proposer (only authoring agent), non-authoring Reviewer with bounded revision cycles, reviewed-proposal persistence, human G10 Apply/Reject via the governed Azure gateway.
- **Upstream inputs:** G05 (`failure_evidence`, `failure_route`, `repair_context_pack`), S2-F03 (governed Azure OpenAI gateway for proposer/reviewer prompts).
- **Downstream outputs:** `repair_proposal`, `repair_review_decision`, `repair_g10_package` schemas for G07/G10.

## 4. Related Jira Features

| Sprint | Feature | Jira ID | Expected capability | Current status |
|---|---|---|---|---|
| S4 | Checksum-bound Repair Proposer | AMFA-214 | Generate candidate + persist + PROPOSER_* events + UI | PARTIALLY_IMPLEMENTED |
| S4 | Non-authoring Repair Reviewer + bounded revision | AMFA-215 | Review candidate + persist + REVIEWER_* events + UI | PARTIALLY_IMPLEMENTED |
| S4 | G10 Apply/Reject package | AMFA-216 | Persist proposal + G10 package + decide + events + UI | PARTIALLY_IMPLEMENTED |

## 5. Related Jira Tasks and Subtasks

| Jira ID | Parent feature | Task description | Expected deliverable | Actual implementation | Status |
|---|---|---|---|---|---|
| AMFA-238 | AMFA-214 | S4-F04-I01 backend domain | Proposer domain + service | `backend/app/domain/proposer.py`, `services/proposer_application_service.py:ProposerService.generate` | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-239 | AMFA-214 | S4-F04-I02 db/api/events/artifacts | Persist + API + events + artifact | `api/routes/repair_attempts.py` (POST/GET proposer); `ProposerResultModel` + migration `695779d2b9ee`; **POST never writes model; no PROPOSER_* event; no artifact** | PARTIALLY_IMPLEMENTED |
| AMFA-240 | AMFA-214 | S4-F04-I03 frontend | Proposer viewer | `frontend/src/components/ProposerViewer.tsx`, `api/repair.ts` — **not imported/rendered anywhere** | PARTIALLY_IMPLEMENTED |
| AMFA-241 | AMFA-214 | S4-F04-I04 tests/security/docs | Tests + docs | **No G06 test file; no as-built docs** | MISSING |
| AMFA-242 | AMFA-215 | S4-F05-I01 backend domain | Reviewer domain + service | `backend/app/domain/reviewer.py`, `services/reviewer_application_service.py:ReviewerService.generate` (max_revisions=3, non-authoring guards) | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-243 | AMFA-215 | S4-F05-I02 db/api/events/artifacts | Persist + API + events | `api/routes/repair_attempts.py` (reviewer/revisions); `ReviewDecisionModel` + migration; **never instantiated; no REVIEWER_* event** | PARTIALLY_IMPLEMENTED |
| AMFA-244 | AMFA-215 | S4-F05-I03 frontend | Reviewer panel | `frontend/src/components/ReviewerPanel.tsx` — **orphaned** | PARTIALLY_IMPLEMENTED |
| AMFA-245 | AMFA-215 | S4-F05-I04 tests/security/docs | Tests + docs | **No G06 test file; no docs** | MISSING |
| AMFA-246 | AMFA-216 | S4-F06-I01 backend domain | Proposal + G10 domain/service | `backend/app/domain/repair_proposal.py`, `services/repair_proposal_application_service.py` (RepairProposalService, G10DecisionService) | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-247 | AMFA-216 | S4-F06-I02 db/api/events/artifacts | Persist proposal + G10 package + API + events | `api/routes/repair_proposals.py` (GET proposal, POST G10 decision); `RepairProposalModel` + migration; **`persist()` never called → no proposal created; REPAIR_PROPOSAL_READY unreachable** | PARTIALLY_IMPLEMENTED |
| AMFA-248 | AMFA-216 | S4-F06-I03 frontend | G10 approval page | `frontend/src/components/G10ApprovalPanel.tsx` — **imports non-existent `getG10Package` (TS error); orphaned** | PARTIALLY_IMPLEMENTED |
| AMFA-249 | AMFA-216 | S4-F06-I04 tests/security/docs | Tests + docs | **No G06 test file; no docs** | MISSING |

Closeout tasks:
- C90 (capability contract/integration tests): MISSING (zero G06 tests exist).
- C91 (manual runtime validation): BLOCKED_BY_EXTERNAL_DEPENDENCY (not executed).
- C92 (as-built docs): BLOCKED (no as-built doc).
- C93 (final audits/completion/push): BLOCKED_BY_EXTERNAL_DEPENDENCY (evidence inaccurate; audits BLOCKED).

## 6. Acceptance Criteria Status

| Acceptance criterion | Expected behavior | Current evidence | Status | Gap |
|---|---|---|---|---|
| S4-F04 Happy path + persist + PROPOSER_* events | Persist result, emit events, UI | POST returns DTO; **no DB write, no events** | FAIL | no persistence/event |
| S4-F04 Stale state | STALE_STATE_VERSION | service checks via optional reader; route injects without reader → inactive | PARTIAL | reader not supplied |
| S4-F04 Evidence (SHA-256 artifact) | Diff/report artifact registered | no artifact registration | FAIL | not implemented |
| S4-F05 Happy path + persist + REVIEWER_* events | Persist decisions, emit events | service produces result; **no DB write, no events** | FAIL | not persisted/emitted |
| S4-F05 Non-authoring guarantee | Reviewer never authors diff | `reviewer.py` guards present | PASS (domain) | not runtime-verified |
| S4-F06 Persist proposal + REPAIR_PROPOSAL_READY | repair_proposals row + event | `persist()` implemented but **never called** | FAIL | no creation path |
| S4-F06 G10 decision + checksum binding | fail-closed binding, stale replay invalid | `G10ApprovalService.decide` implements checks; wired via POST | PARTIAL | unreachable (needs proposal) |
| S4-F06 Missing approval / technical truth | transition rejects w/o G10 | not enforced in G06 | FAIL/N-A | downstream |
| All: frontend states | distinct states visible | components exist but unwired; G10 panel import broken | FAIL | not integrated |
| All: automated tests pass | unit/API/component | **zero G06 tests** | FAIL | no tests |

## 7. Actual Backend Implementation

| File | Symbols | Responsibility | Jira task | Verification |
|---|---|---|---|---|
| `backend/app/domain/proposer.py` | `ProposerRequest`, `ProposerCandidate`, `ProposerResult` | Proposer contracts + diff validation | AMFA-238 | imports OK; untested |
| `backend/app/domain/reviewer.py` | `ReviewRequest`, `ReviewDecision`, `ReviewResult` | Non-authoring reviewer + guards | AMFA-242 | imports OK; untested |
| `backend/app/domain/repair_proposal.py` | `RepairProposal`, `G10ApprovalPackage(Builder)`, `G10ApprovalService` | G10 domain (checksum binding) | AMFA-246 | imports OK; untested |
| `backend/app/services/proposer_application_service.py` | `ProposerService.generate` | Invoke proposer, checksum-bind | AMFA-238/239 | **no persistence; state reader inactive** |
| `backend/app/services/reviewer_application_service.py` | `ReviewerService.generate` | Bounded reviewer cycles | AMFA-242/243 | **no persistence** |
| `backend/app/services/repair_proposal_application_service.py` | `RepairProposalService.persist/get`, `G10DecisionService.decide` | Proposal + G10 lifecycle | AMFA-246/247 | `persist()` **never called**; `decide` wired but unreachable |
| `backend/app/domain/contracts.py` | `PROPOSER_*`/`REVIEWER_*`/`REPAIR_PROPOSAL_READY`/`G10_*` | Event vocabulary | AMFA-239/243/247 | enum present; mostly never emitted |
| `backend/app/repositories/models/workflow.py` | `ProposerResultModel`, `ReviewDecisionModel`, `RepairProposalModel` | Persistence tables | AMFA-239/243/247 | models defined; 2 of 3 never instantiated |
| `backend/app/api/routes/repair_attempts.py` | generate/get proposer, review, revise | Proposer/Reviewer endpoints | AMFA-239/243 | registered; POST no persist |
| `backend/app/api/routes/repair_proposals.py` | read proposal, decide G10 | Proposal read + G10 decision | AMFA-247 | registered; read returns partial |
| `backend/app/llm_gateway/azure_gateway.py` | repair_proposer_v1 / repair_reviewer_v1 prompts | Governed gateway | AMFA-238/242 | present (needs live creds) |

## 8. Actual Frontend Implementation

| File | Component/API/type | Responsibility | Jira task | Wired into UI |
|---|---|---|---|---|
| `frontend/src/components/ProposerViewer.tsx` | ProposerViewer | S4-F04 UI | AMFA-240 | NO (no external references) |
| `frontend/src/components/ReviewerPanel.tsx` | ReviewerPanel | S4-F05 UI | AMFA-244 | NO |
| `frontend/src/components/G10ApprovalPanel.tsx` | G10ApprovalPanel | S4-F06 UI | AMFA-248 | NO — imports non-existent `getG10Package` (build error) |
| `frontend/src/api/repair.ts` | getProposer/invokeProposer/getReviewer/invokeReviewer/getRepairProposal/decideG10 | API client | AMFA-240/244/248 | PARTIAL — `getG10Package` missing; `getReviewer` calls GET `/reviewer` (no such route) |
| `frontend/src/types/repair.ts` | Proposer/Reviewer/Proposal/G10 types | Type contracts | AMFA-240/244/248 | types present |

No page/dashboard imports any of the three components.

## 9. API and Event Coverage

### APIs

| Method | Path | Purpose | Jira task | Implemented | Tested |
|---|---|---|---|---|---|
| POST | `/runs/{run_id}/repair-attempts/{attempt_id}/proposer` | Invoke Proposer | AMFA-239 | Yes (no persist) | NO |
| GET | `/runs/{run_id}/repair-attempts/{attempt_id}/proposer` | Read result | AMFA-239 | Yes (empty table) | NO |
| POST | `/runs/{run_id}/repair-attempts/{attempt_id}/reviewer` | Invoke Reviewer | AMFA-243 | Yes (no persist) | NO |
| POST | `/runs/{run_id}/repair-attempts/{attempt_id}/revisions` | Bounded revision | AMFA-243 | Yes (no persist) | NO |
| GET | `/runs/{run_id}/repair-proposals/{proposal_id}` | Read proposal + G10 status | AMFA-247 | Yes (partial DTO) | NO |
| POST | `/runs/{run_id}/approvals/G10/decisions` | G10 human decision | AMFA-247 | Yes (unreachable w/o proposal) | NO |

No GET `/reviewer` endpoint exists though `api/repair.ts:getReviewer` calls it.

### Events

| Event | Trigger | Jira task | Emitted | Payload verified |
|---|---|---|---|---|
| PROPOSER_STARTED/COMPLETED/INSUFFICIENT_CONTEXT/NOT_REPAIRABLE/FAILED | Proposer run | AMFA-239 | **NO** (enum only) | N/A |
| REVIEWER_STARTED/ACCEPTED/REQUESTED_REVISION/REJECTED/INSUFFICIENT_CONTEXT | Reviewer run | AMFA-243 | **NO** (never emitted) | N/A |
| REPAIR_PROPOSAL_READY | Proposal persisted | AMFA-247 | coded in `persist()` but **unreachable** | not runtime-verified |
| G10_APPROVED/REJECTED/STALE | G10 decision | AMFA-247 | coded in `decide` (needs existing proposal) | not runtime-verified |

## 10. Persistence and Migration Status

| Table/model | Migration | Purpose | Jira task | Status |
|---|---|---|---|---|
| `proposer_results` / `ProposerResultModel` | `695779d2b9ee` (down 20260719_08) | Proposer result | AMFA-239 | table created; **never written by app** |
| `review_decisions` / `ReviewDecisionModel` | `695779d2b9ee` | Reviewer decisions | AMFA-243 | table created; **never written** |
| `repair_proposals` / `RepairProposalModel` | `695779d2b9ee` | Proposal + G10 gate | AMFA-247 | created via `persist()` (never called) & updated by `decide()` |

- **CRITICAL CHAIN DEFECT:** migration head `695779d2b9ee` has `down_revision='20260719_08'`, but `20260719_07` and `20260719_08` (G05's migrations) are **untracked/uncommitted** in this worktree → `alembic upgrade head` fails on a clean checkout. (Completion.json admits copied from G05 worktree.)
- Idempotency: unique constraints present (`uq_proposer_results_run_attempt_idempotency`, `uq_review_decisions_run_proposal_invocation`, `uq_repair_proposals_run_proposal`) but partly unreachable.
- Indexes: run_id/attempt/proposal/status present. Downgrade defined (untested).

## 11. Automated Test Situation

| Test file | Scope | Collected tests | Passing | Failing | Jira coverage |
|---|---|---|---|---|---|
| (none — no G06 test file exists) | G06-specific | 0 | 0 | 0 | AMFA-241/245/249 |
| backend/tests/ (full, py3.11) | whole backend | 329 | 313 | 15 (+1 skip) | **0 G06 tests** |

Executed commands:
- `cd /home/ubuntu/amfa-worktrees/06-repair-agents-g10 && python3.11 -m pytest backend/tests` → **313 passed, 15 failed** (failures unrelated to G06: planning/compatibility/config/preflight/workspace).
- `git diff --name-only d759861 4af15eb -- backend/tests tests` is **empty** — G06 commit added zero test files.
- System python3.10 cannot collect (`from datetime import UTC` requires 3.11).
- `completion.json` `automated_tests:"PASS"` is **unsubstantiated for G06** (the 123/124 "passing" are pre-existing tests unaffected by G06).

## 12. Manual Test Situation

| Manual scenario | Documented | Executed | Result | Evidence |
| --------------- | ---------- | -------- | ------ | -------- |
| MT-001 S4-F04 | Yes | No | — | manual-tests/MT-001 |
| MT-002 S4-F05 | Yes | No | — | manual-tests/MT-002 |
| MT-003 S4-F06 | Yes | No | — | manual-tests/MT-003 |
| MT-900 integrated happy path | Yes | No | — | manual-tests/MT-900 |
| MT-910 stale/idempotency/reconnect | Yes | No | — | manual-tests/MT-910 |
| MT-920 security/a11y/observability | Yes | No | — | manual-tests/MT-920 |

All documented; **none executed** (C91 BLOCKED). No manual-test report in `evidence/`.

## 13. Evidence Situation

| Evidence file | Purpose | Current | Accurate | Notes |
| ------------- | ------- | ------- | -------- | ----- |
| `evidence/completion.json` | Completion record | head_sha = base SHA `d759861` (≠ HEAD `4af15eb`); `automated_tests:PASS`; `pushed:true` w/ dirty tree | NO | never regenerated; misleading |
| `evidence/current-state-gap-map.json` | Pre-work gap map | all MISSING | NO | baseline; not updated |
| `evidence/dependency-status.json` | Dep declaration | G05/S2-F03/S4-F03 BLOCKED_UPSTREAM via local ports | PARTIAL | over-conservative (real gateway present) |
| `evidence/planned-shared-file-changes.json` | Planned shared edits | planning artifact | PARTIAL | — |
| `evidence/task-results/` | Per-task results | **EMPTY dir** | N/A | no task result JSONs recorded |

## 14. Dependency Situation

### Upstream dependencies

| Goal/feature | Required capability | Current availability | Impact |
| ------------ | ------------------- | -------------------- | ------ |
| G05 (failure context) | `failure_evidence`/`failure_route`/`repair_context_pack` schemas | consumed; G05 migrations `20260719_07/08` are **local uncommitted copies** (not integrated) | integration hazard: migration chain broken on clean checkout |
| S2-F03 (LLM gateway) | governed Azure OpenAI proposer/reviewer | declared BLOCKED_UPSTREAM/local-port, but gateway code + repair roles/prompts **actually present** | end-to-end needs live Azure creds (honestly flagged) |
| S4-F03 | repair context builder | BLOCKED_UPSTREAM (no production builder in branch) | real proposer execution blocked |

### Downstream consumers

| Goal/feature | Capability consumed | Contract provided | Readiness |
| ------------ | ------------------- | ----------------- | --------- |
| G07/G10 | `repair_proposal`, `repair_review_decision`, `repair_g10_package` | schemas PRESENT in `goals/shared/contracts/` | contract-ready; conformance not tested |

## 15. Known Issues and Gaps

| ID | Severity | Description | Jira impact | Owner | Required action |
| -- | -------- | ----------- | ----------- | ----- | --------------- |
| K1 | BLOCKER | Migration head `695779d2b9ee` down_revision `20260719_08` is uncommitted (untracked) → alembic chain broken on clean checkout | AMFA-247 (all persistence) | G06 | commit/resolve G05 migration dependency or re-parent |
| K2 | BLOCKER | `ProposerResultModel`/`ReviewDecisionModel` never instantiated; POST endpoints don't persist | AMFA-239, AMFA-243 | G06 | wire persistence + event emission |
| K3 | BLOCKER | `RepairProposalService.persist()` never called → proposals never created; G10 gate & GET proposal unreachable | AMFA-247 | G06 | add proposal-creation endpoint invoking persist |
| K4 | CRITICAL | PROPOSER_*/REVIEWER_* events never emitted (enum only) | AMFA-239, AMFA-243 | G06 | emit events on transitions |
| K5 | CRITICAL | Frontend components unwired; `G10ApprovalPanel` imports non-existent `getG10Package` (build error) | AMFA-240/244/248 | G06 | wire into dashboard; fix export |
| K6 | CRITICAL | Zero G06 automated tests; completion claims PASS | AMFA-241/245/249 | G06 | author unit/API/component/security tests |
| K7 | MAJOR | Proposer/Reviewer routes inject services without `state_version_reader` → STALE_STATE_VERSION inactive | AMFA-239/243 | G06 | supply reader in DI |
| K8 | MAJOR | `api/repair.ts:getReviewer` calls GET `/reviewer` that does not exist | AMFA-244 | G06 | add GET reviewer route or fix client |
| K9 | MAJOR | completion.json head_sha wrong; `pushed:true` with unclean worktree | — | G06 | regenerate completion evidence |
| K10 | MINOR | `read_repair_proposal` returns hardcoded empty fields | AMFA-247 | G06 | persist & project |
| K11 | INFO | System Python 3.10 cannot run suite (needs ≥3.11) | — | Env | use py3.11 harness |

## 16. Goal Completion Matrix

| Dimension                     | Status | Evidence |
| ----------------------------- | ------ | -------- |
| Backend (domain/services)     | Partial | domain+services present & import-clean; persistence/event wiring incomplete |
| Frontend                      | Partial/Broken | 3 components exist, none wired; G10 panel import error |
| API contracts                 | Partial | 6 endpoints registered; persistence/side-effects missing; client/route mismatch |
| Persistence                   | FAIL | 3 tables migrated; 2 never written; proposal never created; broken migration chain |
| Events                        | FAIL | PROPOSER_*/REVIEWER_* never emitted; READY/G10 unreachable |
| Automated tests               | FAIL | no G06 tests; full suite 313 pass/15 fail (none G06) |
| Manual runtime tests          | Blocked | 6 documented, none executed |
| Security controls             | Partial | non-authoring guards + checksum binding in domain; untested |
| Documentation                 | FAIL | as-built docs not generated |
| Evidence                      | Partial/Inaccurate | core files present; completion.json inaccurate; task-results empty |
| Upstream integration          | Partial | frozen schemas + gateway present; G05 migrations only uncommitted copies |
| Downstream contract readiness | Partial | 3 provided schemas present; no conformance tests |

## 17. Jira Completion Summary

| Category                | Total | Complete | Partial | Blocked | Missing |
| ----------------------- | ----: | -------: | ------: | ------: | ------: |
| Features                |     3 |        0 |       3 |       0 |       0 |
| Implementation subtasks |    12 |        3 |       6 |       0 |       3 |
| Closeout tasks          |     4 |        0 |       0 |       3 |       1 |
| Acceptance criteria     |    10 |        1 |       3 |       0 |       6 |

(Subtasks: AMFA-238/242/246 = verified-not-runtime; AMFA-239/243/247 = Partial (not persisted/created); AMFA-240/244/248 = Partial (unwired/broken); AMFA-241/245/249 = Missing (no tests/docs). Closeout: C90 Missing; C91/C92/C93 Blocked.)

## 18. Final Status

| Field                  | Value |
| ---------------------- | ----- |
| `branch_ready`         | false |
| `harness_ready`        | false |
| `integration_verified` | false |
| `jira_complete`        | false |
| Reviewer verdict       | Backend domain/API/persistence/events for all three features are implemented and wired into the router, but not branch-ready: zero automated tests, three orphaned (one build-broken) frontend components, externally-coupled untracked migration, and stale completion evidence |
| Pushed                 | true |
| Remote SHA             | `4af15eb5e1165daeaf12931fbb978d8901bf4dd8` |

## 19. Recommended Next Actions

1. G06 / AMFA-247 — add a proposal-creation endpoint that calls `RepairProposalService.persist()` so proposals (and the G10 gate) become reachable (K3).
2. G06 / AMFA-239/243 — wire persistence + emit PROPOSER_*/REVIEWER_* events in the proposer/reviewer services and routes (K2, K4).
3. G06 — commit/resolve the G05 migration dependency so `alembic upgrade head` works on a clean checkout (K1).
4. G06 / AMFA-240/244/248 — wire components into the dashboard and fix `getG10Package` export / `getReviewer` route (K5, K8).
5. G06 / AMFA-241/245/249 — author unit/API/component/security tests; regenerate completion.json at HEAD `4af15eb` (K6, K9).
6. G06 — supply `state_version_reader` in DI so STALE_STATE_VERSION is enforced (K7).

## 20. Audit Sources

- Git: `git rev-parse/branch --show-current/status --short/log`, `git show --stat 4af15eb`, `git diff --name-only d759861 4af15eb -- backend/tests tests`
- Root: `AGENT.md`
- Goal: `goals/06-repair-agents-g10/{GOAL,TASK_INDEX,JIRA,ACCEPTANCE,CURRENT_CODE_MAP,CROSS_GOAL_CONTRACTS,OWNERSHIP,REFERENCES}.md`, `manual-tests/MT-*`, `evidence-templates/*`
- Backend: `domain/{proposer,reviewer,repair_proposal,contracts}.py`, `services/{proposer,reviewer,repair_proposal}_application_service.py`, `api/router.py`, `api/routes/{repair_attempts,repair_proposals}.py`, `repositories/models/workflow.py`, `llm_gateway/{contracts,azure_gateway}.py`, `alembic/versions/695779d2b9ee_*.py` (+ untracked `20260719_07/08`)
- Frontend: `components/{ProposerViewer,ReviewerPanel,G10ApprovalPanel}.tsx`, `api/repair.ts`, `types/repair.ts`
- Shared: `goals/shared/contracts/{repair_proposal,repair_review_decision,repair_g10_package,failure_evidence,failure_route,repair_context_pack}.schema.json`
- Tests: `backend/tests/` (full py3.11 run), grep for G06 symbols (none)
