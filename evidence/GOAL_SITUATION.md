# G10 — Integrated Angular 18→21 Runtime Proof: Current Situation

## 1. Goal Identity

| Field | Value |
|---|---|
| Goal ID | G10 |
| Goal name | Integrated Angular 18→21 Runtime Proof (Angular 18→21 Acceptance Harness and Integrated Runtime Proof) |
| Sprint | Sprint 4 (feature S4-F15) |
| Worktree | `/home/ubuntu/amfa-worktrees/10-full-runtime-proof` |
| Branch | `hermes/10-full-runtime-proof` |
| Base SHA | `d759861290c1e76e26c4f2b27bbee9a77a12f0b5` |
| Current HEAD SHA | `c301378199fb03079c4e8a81f435e879fe07caad` |
| Remote branch | `origin/hermes/10-full-runtime-proof` (present, matches HEAD) |
| Last audited date | 2026-07-20 |

## 2. Executive Situation

G10 is the terminal integration/proof goal: prove the full Angular 18.x→21.x pipeline end-to-end. The branch implements a **self-contained Phase-A acceptance/proof harness** and is **NOT an integration of G01–G09**. Every criterion requiring real upstream behavior is `BLOCKED_INTEGRATION`/`BLOCKED_UPSTREAM`. No G01–G09 service is imported or invoked anywhere (verified by grep); the only real external code paths are base-branch `command_execution.worker.ExecutionWorker` and a mock LLM gateway. The harness backend is genuinely built and **130 backend tests pass (Python 3.11)**, but two functional defects undermine even the Phase-A self-proof: (1) the `run_acceptance_suite()` orchestrator is **not exposed via any API endpoint**, and (2) production DI constructs `AcceptanceHarnessService` with **no `execution_worker`**, so `evaluate_fixture()` always returns `EVALUATION_SKIPPED` — **no real `ng`/`npm` subprocess ever runs in the live service** (only via `MagicMock` in unit tests). Frontend `AcceptanceChecklist` has a binding bug (keys by absent `fixture_type`; compares wrong outcome enum) so all cards render PENDING, and it is not linked in app navigation. `completion.json` is **inaccurate** (`head_sha` points to an off-branch orphan `5d4658e…`; claims 113 tests vs actual 130) and branch-owned T04 (AMFA-285) has **zero implementation/review evidence**. Manual validation (C91) was never executed. `integration_verified=false` and `jira_complete=false` are correctly and honestly self-declared.

## 3. Goal Objective

- **Business:** Prove the full Angular 18.0.x/18.2.x→19→20→21 MVP end-to-end (fixtures, repair, cancel, restart, final assurance, external publication, unchanged source).
- **Technical:** Phase A = reusable external acceptance harness; Phase B = execute the production proof against an integration branch containing S2-F03 + G01–G09. G10 must not re-implement upstream authority.
- **Upstream inputs:** G01–G09 and S2-F03/S2-F07 — **NOT integrated**; consumed as frozen contracts / base-branch modules only. Verified: zero references to any G01–G09 service class in G10 code.
- **Downstream outputs:** terminal goal; none.

## 4. Related Jira Features

| Sprint | Feature | Jira ID | Expected capability | Current status |
|---|---|---|---|---|
| S4 | Integrated Angular 18→21 Runtime Proof | AMFA-225 | Full end-to-end proof (gates, repair, env blocker, cancel, restart, assurance, publication) | PARTIALLY_IMPLEMENTED (Phase A harness only; Phase B not done) |

## 5. Related Jira Tasks and Subtasks

| Jira ID | Parent feature | Task description | Expected deliverable | Actual implementation | Status |
|---|---|---|---|---|---|
| AMFA-282 | AMFA-225 | T01 Backend application contract | Fixture harness, subprocess profiles, orchestration, evidence collector | `services/acceptance_harness_service.py`, `domain/contracts.py` (Harness* DTOs), `runtime_profiles/harness_profiles.py` | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-283 | AMFA-225 | T02 Persist/expose evidence (DB/API/events/artifacts) | Test-exec records; status endpoint; events; artifacts | `api/routes/acceptance.py` (6 endpoints), `services/runtime_evidence_collector.py` (11 record_*), 11 ACCEPTANCE_* events | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| AMFA-284 | AMFA-225 | T03 Frontend experience | Operator acceptance checklist linking scenarios to live pages/artifacts | `api/acceptance.ts`, `hooks/useAcceptanceChecklist.ts`, `components/AcceptanceChecklist.tsx`, `app/acceptance/page.tsx` — **binding bug; not in nav; no tests** | PARTIALLY_IMPLEMENTED |
| AMFA-285 | AMFA-225 | T04 Verify & document (tests/security/docs) | Automated + security + manual + as-built docs | **No implementation, no tests, no docs, no task-result file** | MISSING |

Closeout tasks:
- C90 (contract/integration tests): PARTIALLY_IMPLEMENTED (8 contract tests pass; harness tests pass; no integration tests).
- C91 (manual runtime validation): MISSING (MT-900/910/920 stub files; never executed).
- C92 (as-built docs): MISSING (not produced).
- C93 (final audits/completion/push): NOT_APPLICABLE (completion.json inaccurate; Phase A scoped).

## 6. Acceptance Criteria Status

| Acceptance criterion | Expected behavior | Current evidence | Status | Gap |
|---|---|---|---|---|
| Happy path (real deps + valid inputs) | full pipeline proof | no G01–G09 integration; `run_acceptance_suite` not wired to API | FAIL | no E2E proof |
| Invalid input → stable error | 422/409 envelopes | harness-level only | PARTIAL | — |
| Stale state → STALE_STATE_VERSION | state-version check | service has check; frontend never submits | PARTIAL | — |
| Persistence (records retrievable) | exec/migration records | `ArtifactMetadataModel` reused; GET endpoints | PASS | — |
| Evidence finalized + SHA-256 | atomic + checksum | `RuntimeEvidenceCollector` | PASS | harness-local |
| Frontend behavior (all states distinct) | live result binding | `AcceptanceChecklist` bug → all PENDING; not in nav | FAIL | GAP-F1 |
| Backend failure → correlation id | error envelope | present | PARTIAL | harness-level |
| Closeout | tests/docs/manual/signoff | T04 absent; manual not run | FAIL | C91/C92 MISSING |

## 7. Actual Backend Implementation

| File | Symbols | Responsibility | Jira task | Verification |
|---|---|---|---|---|
| `backend/app/services/acceptance_harness_service.py` | `AcceptanceHarnessService`, `generate_fixture`, `evaluate_fixture`, `run_subprocess_profile`, `run_acceptance_suite`, `get_status` | Core harness | AMFA-282 | 601 LOC; idempotency in-memory |
| `backend/app/domain/contracts.py` | `Harness*Dto`, 11 `ACCEPTANCE_*` events | Harness contracts | AMFA-282/283 | present (shared file) |
| `backend/app/services/runtime_evidence_collector.py` | `RuntimeEvidenceCollector` (11 record_*) | Evidence writer | AMFA-283 | atomic + checksum |
| `backend/app/runtime_profiles/harness_profiles.py` | `HARNESS_PROFILE_ENTRIES`, `HARNESS_COMMAND_REGISTRY` | 5 ng/npm/npx profiles | AMFA-282 | present |
| `backend/app/api/routes/acceptance.py` | 6 REST endpoints | Status/runs/evidence | AMFA-283 | registered; **no suite-run endpoint** |
| `backend/app/api/router.py` | `acceptance_router` wired ×2 | route wiring | AMFA-283 | present |
| `backend/tests/fixture_generators/angular_fixture.py` | 7 fixture generators | External temp-root fixtures | AMFA-282 | present |
| `backend/app/command_execution/worker.py` | `ExecutionWorker` | **base-branch** infra (NOT a G01 service) | not G10 | used with mock only |

## 8. Actual Frontend Implementation

| File | Component/API | Responsibility | Jira task | Wired into UI |
|---|---|---|---|---|
| `frontend/src/api/acceptance.ts` | Typed client (6 endpoints) | G10 client | AMFA-284 | YES (client); no run-suite method |
| `frontend/src/hooks/useAcceptanceChecklist.ts` | Polling hook | fetch status | AMFA-284 | YES (5s poll; never submits idempotency/state version) |
| `frontend/src/components/AcceptanceChecklist.tsx` | Operator checklist UI | G10 UI | AMFA-284 | **BUG**: keys by absent `fixture_type`; compares `"pass"/"SUCCEEDED"` vs backend `"PASSED"/"GENERATED"` → all PENDING |
| `frontend/src/app/acceptance/page.tsx` | Route page | G10 page | AMFA-284 | reachable by URL; **not in app nav** |
| `frontend/src/types/generated/api.ts` | Generated DTOs | TS contracts | AMFA-284 | present |

No G10 frontend component tests exist (`__tests__/` has none for `AcceptanceChecklist`).

## 9. API and Event Coverage

### APIs (6 endpoints exposed)

| Method | Path | Purpose | Jira task | Implemented | Tested |
|---|---|---|---|---|---|
| GET | `/api/v1/operator/acceptance-suite/status` | suite status | AMFA-283 | Yes | Yes |
| POST | `…/fixtures` | generate fixture | AMFA-282 | Yes | Yes |
| POST | `…/fixtures/evaluate` | evaluate fixture | AMFA-282 | Yes | Yes |
| GET | `…/runs` | list runs | AMFA-283 | Yes | Yes |
| GET | `…/runs/{run_id}` | get run | AMFA-283 | Yes | Yes |
| GET | `…/runs/{run_id}/evidence` | get evidence | AMFA-283 | Yes | Yes |
| (none) | `…/run` (orchestrator) | **run full suite** | AMFA-282 | **MISSING** | GAP-F2 |

### Events

| Event | Trigger | Jira task | Emitted | Payload verified |
|---|---|---|---|---|
| ACCEPTANCE_SUITE_STARTED / FIXTURE_GENERATED / FIXTURE_EVALUATED / OUTPUT_FINGERPRINT_CREATED / REPAIR_LINEAGE_RECORDED / etc. (11 enum values) | acceptance steps | AMFA-283 | **NO** (enum only; collector writes JSON artifacts, never calls event service) | N/A |

## 10. Persistence and Migration Status

- Reuses existing `ArtifactMetadataModel` (no new tables). No Alembic migration added (consistent — no schema change). `database-migration.json` template only.
- Idempotency: in-memory dict in `AcceptanceHarnessService` (self-documented Phase A; DB-backed in Phase B).
- No FK/schema defect in-branch.

## 11. Automated Test Situation

| Test file | Scope | Collected | Passing | Failing | Jira coverage |
|---|---|---|---|---|---|
| `backend/tests/test_acceptance_harness.py` | harness unit | 28 | 28 | 0 | AMFA-282 |
| `backend/tests/test_acceptance_harness_api.py` | harness API | 19 | 19 | 0 | AMFA-283 |
| `backend/tests/test_fake_model_integration.py` | mock LLM | 10 | 10 | 0 | AMFA-282 |
| `backend/tests/test_harness_persistence.py` | persistence | 17 | 17 | 0 | AMFA-283 |
| `backend/tests/test_angular18_fixture.py` | fixtures | 48 | 48 | 0 | AMFA-282 |
| `backend/tests/test_contracts.py` | contract (C90) | 8 | 8 | 0 | AMFA-282 |

Executed: `cd /home/ubuntu/amfa-worktrees/10-full-runtime-proof && PYTHONPATH=... python3.11 -m pytest <6 files>` → **130 passed, 0 failed** (reviewer).
- Audit env default py3.10 fails collection (`datetime.UTC`).
- Evidence claims **"113 tests"** — **inaccurate** (actual 130).
- No integration tests; no frontend component/SSE tests.
- Subprocess reality: tests use `MagicMock`/`ExecutionWorker` mocks; **no test executes a real `ng`/`npm` subprocess**. Production `evaluate_fixture()` returns `EVALUATION_SKIPPED` (no `execution_worker` injected).

## 12. Manual Test Situation

| Manual scenario | Documented | Executed | Result | Evidence |
| --------------- | ---------- | -------- | ------ | -------- |
| MT-001 S4-F15 authoritative scenario | Yes (stub) | No | deferred to Phase B | — |
| MT-900 integrated happy path | Yes (5 lines) | No | **never executed** | — |
| MT-910 stale/idempotency/reconnect/restart | Yes (5 lines) | No | — | — |
| MT-920 security/a11y/observability | Yes (5 lines) | No | — | — |

All documented as stubs; **none executed** (C91 MISSING; `completion.json` honestly `manual_tests:BLOCKED`).

## 13. Evidence Situation

| Evidence file | Purpose | Current | Accurate | Notes |
| ------------- | ------- | ------- | -------- | ----- |
| `evidence/completion.json` | Completion gate | present | **INACCURATE** | `head_sha`=`5d4658e8…` is an **off-branch orphan** (not ancestor of HEAD `c301378`); claims 113 tests (actual 130); `branch_ready=true`/`harness_ready=true` asserted while T04 has no evidence |
| `evidence/current-state-gap-map.json` | Gap map | present | Accurate | honestly marks C91/C92 MISSING, T03/T04 PARTIAL |
| `evidence/dependency-status.json` | Dep status | present | Accurate | correctly marks G01–G09 `BLOCKED_UPSTREAM`; only base `ExecutionWorker` + mock used |
| `evidence/integration-blocker-matrix.json` | Blocker matrix | present | Accurate | 11 BICs + GAP-T03/T04; confirms no upstream integration |
| `evidence/runtime-proof-audit-report.md` | audit | present | Minor staleness | "113 tests" wrong; Audit SHA pre-fix |
| `evidence/task-results/01-*`, `02-*` | I01/I02 results | present (PASS) | Accurate | verified |
| `evidence/task-results/03-*`, `04-*` | I03/I04 results | **ABSENT** | — | matches PARTIAL/MISSING |
| `evidence/shared-file-changes.json` | Shared edits | **ABSENT** (template only) | — | minor gap |

## 14. Dependency Situation

### Upstream dependencies (the key question for an integration goal)

| Goal/feature | Required capability | Current availability | Impact |
| ------------ | ------------------- | -------------------- | ------ |
| G01–G09, S2-F03, S2-F07 | full pipeline | **NOT integrated** | harness uses base-branch `ExecutionWorker` + mock LLM only; zero G01–G09 service imports |
| S0 `ExecutionWorker`/`CommandRegistry`/`LocalFilesystemArtifactStore` | base infra | base branch | genuinely used (only when `execution_worker` injected — not in prod DI) |

G10 does **NOT** integrate G01–G09. It is a standalone Phase-A harness consuming frozen contracts + one base-branch component. This is honestly reflected in `integration_verified=false`/`jira_complete=false`.

### Downstream consumers

| Goal/feature | Capability consumed | Contract provided | Readiness |
| ------------ | ------------------- | ----------------- | --------- |
| None (terminal) | — | — | — |

## 15. Known Issues and Gaps

| ID | Severity | Description | Jira impact | Owner | Required action |
| -- | -------- | ----------- | ----------- | ----- | --------------- |
| GAP-F1 | HIGH | `AcceptanceChecklist.tsx` keys results by absent `fixture_type`; compares wrong outcome enum → all cards PENDING; real results never display | AMFA-284 | G10 | fix DTO/projection + outcome enum |
| GAP-F2 | HIGH | `run_acceptance_suite()` not exposed via API → no full-suite run path | AMFA-282 | G10 | expose suite-run endpoint (or document deferral) |
| GAP-F3 | HIGH | Production `evaluate_fixture()` returns `EVALUATION_SKIPPED` (no `execution_worker` in DI) → no real subprocess runs in live service | AMFA-282 | G10 | inject real `ExecutionWorker` or document harness-only |
| GAP-F4 | MEDIUM | 11 ACCEPTANCE_* events declared but never emitted (collector writes JSON only) | AMFA-283 | G10 | emit durable events or correct claim |
| GAP-T03 | MEDIUM | T03 (AMFA-284) frontend: no reviewer PASS, no component test, not in nav | AMFA-284 | G10 | add tests + reviewer verdict (Phase B) |
| GAP-T04 | MEDIUM | T04 (AMFA-285) tests/security/docs: zero evidence | AMFA-285 | G10 | implement in Phase B (or re-scope out of Phase-A closure) |
| GAP-E1 | LOW | `completion.json.head_sha` orphan off-branch (`5d4658e…`) | evidence | G10 | regenerate at HEAD `c301378` |
| GAP-E2 | LOW | Test count misreported as 113 (actual 130) | evidence | G10 | correct count |
| GAP-E3 | LOW | `shared-file-changes.json`/`database-migration.json` not instantiated | evidence | G10 | populate in Phase B |
| GAP-I1 | LOW | Idempotency in-memory only (lost on restart) | AMFA-282 | G10 | DB-back in Phase B |

## 16. Goal Completion Matrix

| Dimension                     | Status | Evidence |
| ----------------------------- | ------ | -------- |
| Backend (harness)             | Partial (verified) | harness genuinely built; 130 tests pass |
| Frontend                      | Partial | page + client + hook present; binding bug; not in nav; no tests |
| API contracts                 | Partial | 6 endpoints; no suite-run endpoint |
| Persistence                   | Present (reuse) | ArtifactMetadataModel reused |
| Events                        | Partial | enum defined, never emitted |
| Automated tests               | Partial (verified) | 130 pass; no integration/FE tests |
| Manual runtime tests          | MISSING | none executed |
| Security controls             | Partial | auth present; harness-level |
| Documentation                 | MISSING | no as-built docs |
| Evidence                      | Partial (inaccurate) | head_sha orphan; wrong test count |
| Upstream integration          | MISSING | G01–G09 not integrated |
| Downstream contract readiness | N/A | terminal goal |

## 17. Jira Completion Summary

| Category                | Total | Complete | Partial | Blocked | Missing |
| ----------------------- | ----: | -------: | ------: | ------: | ------: |
| Features                |     1 |        0 |       1 |       0 |       0 |
| Implementation subtasks |     4 |        2 |       1 |       0 |       1 |
| Closeout tasks          |     4 |        0 |       1 |       0 |       3 |
| Acceptance criteria     |     7 |        2 |       3 |       0 |       2 |

(AMFA-282/283 Complete-ish (verified-not-runtime); AMFA-284 Partial; AMFA-285 Missing. `jira_complete` correctly false.)

## 18. Final Status

| Field                  | Value |
| ---------------------- | ----- |
| `branch_ready`         | false |
| `harness_ready`        | true |
| `integration_verified` | false |
| `jira_complete`        | false |
| Reviewer verdict       | G10 is an honest, well-built Phase-A branch-local harness, not the integrated runtime proof AMFA-225 ultimately requires: it consumes base-branch modules and mocks, never the real G01–G09 branches, and executes no end-to-end pipeline. branch_ready cannot stand as-is because completion.json records an off-branch orphan head_sha and branch-owned T04 claims closure with zero implementation/review evidence; both must be fixed before push is defensible |
| Pushed                 | true |
| Remote SHA             | `c301378199fb03079c4e8a81f435e879fe07caad` |

## 19. Recommended Next Actions

1. G10 / evidence — regenerate `completion.json` at correct HEAD `c301378`; correct the 113→130 test count (GAP-E1/E2).
2. G10 / AMFA-282 — expose a `run_acceptance_suite` endpoint (GAP-F2) and inject a real `ExecutionWorker` so production `evaluate_fixture()` runs real `ng`/`npm` subprocesses (GAP-F3).
3. G10 / AMFA-284 — fix `AcceptanceChecklist` result binding (fixture_type/outcome enum) and add it to app navigation + component tests (GAP-F1, GAP-T03).
4. G10 / AMFA-285 — implement T04 tests/security/docs or explicitly re-scope it out of Phase-A closure (GAP-T04).
5. G10 / AMFA-283 — emit the declared `ACCEPTANCE_*` durable events or correct the evidence claim (GAP-F4).
6. Program-level — Phase B remains mandatory: integrate G01–G09 + S2-F03 into an integration branch and execute the MT-900 end-to-end proof before `jira_complete=true`.

## 20. Audit Sources

- Git: `git log/status/rev-parse/branch --show-current/branch -r`, `git diff --stat d759861..HEAD`, `git ls-tree d759861 backend/app`, `git merge-base --is-ancestor`
- Root: `AGENT.md`
- Goal: `goals/10-full-runtime-proof/{GOAL,TASK_INDEX,JIRA,ACCEPTANCE,OWNERSHIP,CROSS_GOAL_CONTRACTS,REFERENCES,CURRENT_CODE_MAP,MANUAL_TEST_PLAN}.md`, `tasks/T01..T04,C90..C93`, `manual-tests/MT-*`, `evidence-templates/completion.json`
- Backend: `services/acceptance_harness_service.py`, `domain/contracts.py`, `services/runtime_evidence_collector.py`, `runtime_profiles/harness_profiles.py`, `api/routes/acceptance.py`, `api/router.py`, `command_execution/worker.py`, `tests/fixture_generators/angular_fixture.py`
- Frontend: `api/acceptance.ts`, `hooks/useAcceptanceChecklist.ts`, `components/AcceptanceChecklist.tsx`, `app/acceptance/page.tsx`, `types/generated/api.ts`
- Tests: `backend/tests/{test_acceptance_harness,test_acceptance_harness_api,test_fake_model_integration,test_harness_persistence,test_angular18_fixture,test_contracts}.py`
- Evidence: `evidence/{completion,current-state-gap-map,dependency-status,integration-blocker-matrix}.json`, `runtime-proof-audit-report.md`, `task-results/*`, `plans/t01-t03-*`
- Shared: `goals/shared/contracts/*`, `goal_completion.schema.json`, `GOAL_INDEX.yaml`
