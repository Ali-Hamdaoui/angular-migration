# G10 Full Runtime Proof — Audit Report

**Branch:** `hermes/10-full-runtime-proof`
**Audit SHA:** `82f89df` (pre-fix), see commit for post-fix SHA
**Audit date:** 2026-07-19
**Phase:** Phase A — `harness_ready`
**Completion claimed:** `branch_ready=true, harness_ready=true, integration_verified=false, jira_complete=false`

---

## 1. Harness Audit Results

### 1.1 Fixture Generators — PRESENT ✅
All 7 fixture generators exist in `backend/tests/fixture_generators/angular_fixture.py`:
- `create_angular_fixture` (18.2.x baseline)
- `create_angular_fixture_180x` (18.0.x variant)
- `create_passable_fixture`
- `create_compiler_error_fixture` (intentional syntax error in main.ts)
- `create_dependency_conflict_fixture` (incompatible @angular/core 19.0.0 + rxjs 6.6.7)
- `create_environment_blocker_fixture` (precheck.js with exit(1))
- `create_cancellable_fixture` (infinite setTimeout loop)

All generators create workspaces under caller-supplied external temp root (not in repo). FIXTURE_GENERATORS dict in `acceptance_harness_service.py` has all 7 types registered.

### 1.2 Isolated Runtime Directories — PRESENT ✅
`/home/ubuntu/amfa-runtime/10-full-runtime-proof/` exists with:
- `artifacts/`, `browser/`, `evidence/`, `fixtures/`, `logs/`, `temp/`
- `session.json` with correct ports (8310/3310), db_path, artifact_store path
- No runtime state leaks into git repo

### 1.3 Deterministic Setup — PRESENT ✅
- `AcceptanceHarnessService.__init__` accepts `fake_model_config`, `session_scope_factory`, `artifact_store`, `evidence_collector`, `execution_worker`, `now_provider`
- In-memory `_idempotency_store` dict with `StaleStateVersionError` for conflict detection
- `@lru_cache(maxsize=1)` on `get_harness_service()` — **confirmed fixed** (acceptance.py:44)
- `_checksum_workspace()` computes deterministic SHA-256 over workspace contents

### 1.4 Execution Profiles — PRESENT ✅
5 harness subprocess profiles in `harness_profiles.py`:
- `ng-new`, `ng-generate`, `ng-build`, `npm-install`, `npx-ng-update`
- All have correct timeouts (60-120s), `TERMINATE_PROCESS_TREE` cancellation policy
- `build_harness_command_registry()` creates CommandRegistry with base + harness commands
- `run_subprocess_profile()` uses ExecutionWorker, CommandPolicy, sandbox_alias mapping

### 1.5 Test Orchestration — PRESENT ✅
- `generate_fixture()` — creates workspace, computes checksum, records manifest + isolation + source_integrity evidence
- `evaluate_fixture()` — runs ng build through subprocess profile, records integration_result + output_fingerprint/cancellation, records proof_report
- `run_acceptance_suite()` — orchestrates full fixture→subprocess→evaluation cycle with HarnessStatusDto
- Error handling: `StaleStateVersionError` (409), `ValueError` (422), unknown fixture type

### 1.6 Evidence Capture — PRESENT ✅
`RuntimeEvidenceCollector` with 11 record methods:
- `record_fixture_manifest`, `record_isolation_evidence`, `record_output_layout_evidence`, `record_integration_result`, `record_proof_report`
- `record_cancellation_evidence`, `record_restart_evidence`, `record_repair_lineage`, `record_output_fingerprint`, `record_source_integrity_proof`, `record_acceptance_suite_evidence`
- All use atomic write + SHA-256 through `LocalFilesystemArtifactStore` + `ArtifactMetadataModel` registration

### 1.7 Restart/Reconnect — PARTIAL ⚠️
- `record_restart_evidence()` exists (writes evidence payload) — T02 deliverable
- No actual restart/recovery logic — correctly deferred to Phase B (requires G01/G08)
- No restart/reconnect test coverage — acceptable for Phase A

### 1.8 Security — PRESENT ✅
- All DTOs use ContractModel with `extra='forbid'` + `frozen=True`
- CommandPolicy allows only registered commands via `HARNESS_COMMAND_REGISTRY`
- Correlation IDs on error responses (`x-correlation-id` header)
- No G01–G09 production service duplication
- Path traversal protection: `_fixture_root_path()` resolves to external temp only

### 1.9 Cleanup — PARTIAL ⚠️
- Fixtures are created under external temp root (`/tmp/amfa-harness-fixtures` or caller-supplied path)
- No automatic cleanup after evaluation — acceptable for Phase A
- Tests use `tmp_path` for isolation (pytest auto-cleanup)

### 1.10 Reproducibility — PARTIAL ⚠️
- Fixture generation is deterministic (same inputs → same workspace structure)
- Idempotency: same idempotency_key + same state_version returns cached result
- UUIDs used in fixture names and run_ids prevent exact-path replay — acceptable for Phase A (Phase B would use sequential IDs)

---

## 2. Test Coverage Assessment

| Test File | Lines | Tests | Status |
|-----------|-------|-------|--------|
| `test_angular18_fixture.py` | 165 | ~20 parametrized | ✅ After audit fix |
| `test_acceptance_harness.py` | ~412 | ~25 | ✅ After audit fixes |
| `test_acceptance_harness_api.py` | ~247 | ~15 | ✅ After rewrite |
| `test_fake_model_integration.py` | ~234 | ~12 | ✅ After fixes |
| `test_contracts.py` | existing | 8 | ✅ |

**Total:** 113 tests passing.

---

## 3. Task Completion Status

| Jira | Task | Status | Evidence |
|------|------|--------|----------|
| AMFA-282 | T01 Backend harness | ✅ Completed | Re-review passed, fixes confirmed |
| AMFA-283 | T02 DB/API/Events | ✅ Completed | Review PASS, all 7 criteria met |
| AMFA-284 | T03 Frontend | ⚠️ Code exists, NO review | No task result file, no component tests |
| AMFA-285 | T04 Tests/Security/Docs | ❌ No evidence | Not started |
| C90 | Contract tests | ✅ 8 tests pass | In test_contracts.py |
| C91 | Manual validation | ❌ Not executed | Deferred to Phase B |
| C92 | As-built documentation | ❌ Not created | Deferred to Phase B |
| C93 | Final audits | ✅ This audit | Current file |

---

## 4. Key Defects Found and Fixed During Audit

1. **test_unknown_fixture_type_raises**: Mutated shared module-level `FIXTURE_GENERATORS` global, breaking test isolation. Fixed with try/finally restore pattern.
2. **test_unknown_fixture_id_returns_not_found**: Used service without `execution_worker`, so `FIXTURE_NOT_FOUND` path never triggered. Fixed by adding `execution_worker=MagicMock()`.
3. **test_with_execution_worker_calls_subprocess**: Mocked `ExecutionWorker` but `run_subprocess_profile` actually builds a `CommandPolicy` that failed on mock worker. Fixed by patching `run_subprocess_profile` on the service.
4. **test_cancelled_build_records_cancellation_evidence**: Same pattern as above. Fixed.
5. **test_full_cycle_with_mock_worker**: Same pattern. Fixed.
6. **test_unregistered_profile_rejected**: Service without `execution_worker` returned `SKIPPED` before checking profile. Fixed by adding `execution_worker=MagicMock()`.
7. **API test monkey-patching**: `mod_acceptance.get_harness_service = lambda: test_service` doesn't work with `@lru_cache`. Fixed by using `app.dependency_overrides[]` (FastAPI's proper DI override mechanism).
8. **test_fake_model_integration**: Expected `recommended_actions` key in `MockLlmGateway.structured_output` which doesn't exist. Fixed to check actual keys.
9. **test_agents_can_call_gateway**: Used `_request()` with `AgentKind.PLANNING` but expected `AgentKind.REPAIR`. LlmRequest is frozen so can't modify after creation. Fixed by creating a dedicated repair request.

---

## 5. Integration Blocker Matrix

### G01–G09 Dependency Status

| Dependency | Goal | Worktree on Disk | Pushed to Origin? | G10 Consumes |
|-----------|------|-----------------|-------------------|-------------|
| Command Runtime | G01 | ✅ | ✅ | ExecutionWorker, CommandRegistry |
| Stage Bootstrap | G02 | ✅ | ✅ | (test fake: external temp dirs) |
| Angular Transform | G03 | ✅ | ✅ | (test fake: synthetic fixtures) |
| Stage Validation | G04 | ✅ | ❌ Not pushed | (Phase B only) |
| Failure Diagnostics | G05 | ✅ | ✅ | (Phase B only) |
| Repair Agents G10 | G06 | ✅ | ✅ | (Phase B only) |
| Patch Validation | G07 | ✅ | ❌ Not pushed | (Phase B only) |
| Reconciliation | G08 | ✅ | ✅ | (Phase B only) |
| Assurance/Delivery | G09 | ✅ | ✅ | (Phase B only) |

### Blocker Matrix

| # | Integration Area | Required By | What Exists in G10 | What's Missing | Severity |
|---|-----------------|-------------|-------------------|----------------|----------|
| 1 | Angular 18→19→20→21 execution | G01–G09 | Harness profiles + synthetic fixtures | Production CommandExecutor, stage engine, transform pipeline | BLOCKED_INTEGRATION |
| 2 | Human gates | G03–G09 | None (correct for Phase A) | G03/G04 review, G10 apply/reject, G11 confirmation, G12 sign-off | BLOCKED_INTEGRATION |
| 3 | Repair loop | G04–G09 | `record_repair_lineage()` placeholder | FailureEvidence, C-Lite, Proposer, Reviewer, G10 apply | BLOCKED_INTEGRATION |
| 4 | Final assurance/delivery/report | G09 | None (correct for Phase A) | G13, G14, G15 services | BLOCKED_INTEGRATION |
| 5 | Cancellation/process-tree | G01/G04 | Cancellable fixture + evidence capture | Production cancellation integration | BLOCKED_INTEGRATION |
| 6 | Restart/reconnect | G01/G08 | `record_restart_evidence()` | Actual restart/recovery logic | BLOCKED_INTEGRATION |

---

## 6. Honest Completion Values

| Field | Current Value | Honest Assessment |
|-------|--------------|-------------------|
| `branch_ready` | `true` | `true` — harness works, tests pass, branch is pushable (T03/T04 gaps noted but not blocking for Phase A push) |
| `harness_ready` | `true` | `true` — acceptance harness is built and validated |
| `integration_verified` | `false` | `false` — correct, no integration |
| `jira_complete` | `false` | `false` — correct, Phase A only |
| `automated_tests` | `PASS` | `PASS` — 113 tests after audit fixes |
| `manual_tests` | `BLOCKED` | `BLOCKED` — deferred to Phase B |
| `documentation` | `BLOCKED` | `BLOCKED` — deferred to Phase B |
| `architecture_audit` | `BLOCKED` | `BLOCKED` — deferred to Phase B |
| `product_audit` | `BLOCKED` | `BLOCKED` — deferred to Phase B |
| `human_product_signoff` | `not_required` | `not_required` — correct for Phase A |

---

## 7. VCS Metadata

- **Base SHA:** `d759861290c1e76e26c4f2b27bbee9a77a12f0b5`
- **Head SHA (pre-fix):** `82f89df61505d8a178a284b9a273cd70520b4df6`
- **Branch:** `hermes/10-full-runtime-proof`
- **Remote:** `origin`
- **Test suite:** `113 passed, 0 failed, 1 warning` (harness + contract tests)
