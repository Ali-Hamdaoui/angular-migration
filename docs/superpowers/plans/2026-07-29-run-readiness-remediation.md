# Run Readiness Remediation Implementation Plan

**Execution status:** Completed on 2026-07-29. The authoritative results,
checksums, verification results, and readiness decision are recorded in
[`docs/as-built/RUN_READINESS_REMEDIATION_CLOSURE.md`](../../as-built/RUN_READINESS_REMEDIATION_CLOSURE.md).
The final persistence audit added migration `20260729_35` to normalize phase
artifact ownership after the tasks below were executed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the evidence, planning, review, and persistence defects found in `run-16a48fc55de7`, then prove a new run can reach a current human-approved G06 without starting transformation.

**Architecture:** Preserve the failed run as immutable forensic evidence. Correct evidence at its producer, carry runtime and workspace bindings through typed planning contracts, persist the migration-stage parent before stage-scoped metadata, model Planning reviewer non-acceptance as a durable governed outcome, and reserve technical failure handling for infrastructure or invalid-system failures. Validate with focused contract tests, the complete backend suite, Alembic/foreign-key checks, and a fresh end-to-end run stopped immediately after G06 approval.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, SQLite, pytest, Angular/npm/Jest evidence parsers.

## Global Constraints

- Do not modify any payload, metadata sidecar, event, gate, or database fact in `.migration-factory/runs/run-16a48fc55de7`.
- A migration may add missing `migration_stages` parent rows for historical stage-scoped metadata, but it must not rewrite historical artifacts.
- Do not switch branches, commit, push, create a pull request, start a transformation sandbox, or execute transformation commands.
- Every behavior change starts with a failing test and ends with focused and regression verification.
- Every newly persisted JSON artifact must be registered, checksum-valid, immutable where the surrounding producer requires immutability, and safe for operator display.
- The final readiness verdict is allowed only when a fresh run has an approved current G06 and `PRAGMA foreign_key_check` is empty.

---

### Task 1: Make baseline validation status and Jest counts truthful

**Files:**

- Modify: `backend/app/services/baseline_validation_application_service.py`
- Modify: `backend/app/services/baseline_g03_application_service.py`
- Test: `backend/tests/test_baseline_validation_application_s1_f12.py`
- Test: `backend/tests/test_baseline_qualification_persistence_api_s1_f14.py`

- [ ] Add a regression test using real Jest summary order:

```python
output = """
Test Suites: 2 passed, 2 total
Tests:       14 passed, 14 total
"""
assert BaselineValidationApplicationService._test_count(output) == 14
```

- [ ] Add a G03 aggregation test proving a lint validation whose only result is `skipped_not_configured` remains `skipped_not_configured`, not `passed`.
- [ ] Run the focused tests and confirm they fail for the two audited defects.
- [ ] Change `_test_count` to prefer the `Tests:` line and only use a generic fallback when that line is absent.
- [ ] Change validation aggregation so all-not-configured and all-not-applicable groups preserve their exact skipped status; mixed successful/skipped groups remain successful.
- [ ] Ensure `BaselineValidationApplicationService.execute()` persists a skipped-only validation with a skipped status instead of labeling the record passed.
- [ ] Run:

```powershell
python -m pytest backend/tests/test_baseline_validation_application_s1_f12.py backend/tests/test_baseline_qualification_persistence_api_s1_f14.py -q
```

### Task 2: Persist structured dependency-security evidence

**Files:**

- Modify: `backend/app/services/baseline_install_application_service.py`
- Test: `backend/tests/test_baseline_install_persistence_api_s1_f11.py`

- [ ] Add tests for npm output containing `86 vulnerabilities (10 low, 24 moderate, 48 high, 4 critical)` and for output with no vulnerability summary.
- [ ] Require a registered `01_baseline/dependency-security-summary.json` artifact with this stable shape:

```json
{
  "source": "npm-ci-output",
  "status": "risk_detected",
  "total": 86,
  "severity_counts": {"low": 10, "moderate": 24, "high": 48, "critical": 4},
  "policy_decision": "report_only",
  "risks": ["DEPENDENCY_VULNERABILITIES_REPORTED"],
  "blockers": []
}
```

- [ ] Run the focused persistence test and confirm the artifact expectation fails.
- [ ] Add a deterministic parser that reads finalized stdout/stderr, never shells out to `npm audit`, and returns `not_reported` when npm supplied no summary.
- [ ] Write and register the security artifact in success and failure finalization paths; include the risk list in `baseline_install_summary.json`.
- [ ] Preserve installation success when the report-only policy sees vulnerabilities, while making the known risk explicit for later analysis and human gates.
- [ ] Run:

```powershell
python -m pytest backend/tests/test_baseline_install_persistence_api_s1_f11.py -q
```

### Task 3: Correct parity source classification and HttpClient discovery

**Files:**

- Modify: `backend/app/domain/parity_baseline.py`
- Test: `backend/tests/test_parity_baseline_application_service_s2_f02.py`

- [ ] Add a fixture with:
  - `src/app/user.service.ts` using `this.http.get<User[]>('https://jsonplaceholder.typicode.com/users')` and `post<User>(literalUrl, body)`;
  - `.vscode/settings.json`;
  - `.migration-factory/source-manifest.json`;
  - an application file that genuinely contains a behavior-sensitive indicator.
- [ ] Assert GET and POST literal endpoints are discovered, no dynamic-endpoint unknown is emitted for them, editor/generated files are classified but excluded from behavior-sensitive evidence, and the real application file remains included.
- [ ] Run the focused test and confirm it fails.
- [ ] Extend `_HTTP` to allow optional TypeScript generic type arguments between the method and opening parenthesis.
- [ ] Introduce deterministic path classes: `application`, `build_configuration`, `test`, `editor`, and `generated_control`.
- [ ] Keep editor and generated-control files out of behavior-sensitive scanning; preserve them in a non-behavioral classification inventory so exclusions are auditable.
- [ ] Emit unresolved/dynamic endpoint unknowns only when an actual HttpClient argument cannot be resolved to a literal.
- [ ] Run:

```powershell
python -m pytest backend/tests/test_parity_baseline_application_service_s2_f02.py backend/tests/test_baseline_parity_persistence_api_s1_f13.py -q
```

### Task 4: Bind planning commands to proven scripts and the selected runtime

**Files:**

- Modify: `backend/app/domain/planning.py`
- Modify: `backend/app/services/planning_application_service.py`
- Modify: `backend/app/services/planning_evidence_application_service.py`
- Modify: `backend/app/orchestration/planning.py`
- Test: `backend/tests/test_planning_application_service_s2_f06_i01.py`
- Test: `backend/tests/test_project_aware_planning.py`
- Test: `backend/tests/test_planning_transformation_boundary.py`

- [ ] Add tests proving:
  - absent lint produces `commands["lint"] == ()` and no invented `resolved_scripts["lint"]`;
  - present lint still renders the registered npm-script command;
  - every command reference carries the selected execution-profile checksum;
  - required build/test scripts cannot silently fall back to invented names.
- [ ] Run the focused tests and confirm the absent-lint and runtime-binding assertions fail.
- [ ] Add `execution_profile_checksum` to `PlanGenerationRequest` with the SHA-256 contract.
- [ ] Supply it from the G05-selected profile in `_approved_plan_request()` / `generate_plan_step()` and revalidate it in `_require_approved_feasibility()`.
- [ ] Set `CommandTemplateReference.runtime_profile_checksum` for every generated command.
- [ ] Build `builds`, `tests`, and `lint` groups only from `resolved_scripts`; require build/test and allow lint to be an empty tuple.
- [ ] Tighten `StageExecutionPlan.validate_commands()` so only the optional lint group may be empty.
- [ ] Run:

```powershell
python -m pytest backend/tests/test_planning_application_service_s2_f06_i01.py backend/tests/test_project_aware_planning.py backend/tests/test_planning_transformation_boundary.py -q
```

### Task 5: Create stage parents before stage-scoped artifacts and repair historical foreign keys

**Files:**

- Modify: `backend/app/services/planning_evidence_application_service.py`
- Modify: `backend/app/services/stage_execution_application_service.py`
- Create: `backend/alembic/versions/20260729_34_run_readiness_remediation.py`
- Test: `backend/tests/test_planning_evidence_persistence_api_s2_f06_i02.py`
- Test: `backend/tests/test_stage_execution_application_service.py`
- Test: `backend/tests/test_migration_schema_upgrade.py`

- [ ] Add a planning persistence test with SQLite foreign keys enabled; assert the first-stage `MigrationStageModel` exists with status `planned` before any `ArtifactMetadataModel.stage_id` references it.
- [ ] Add a stage-preparation test proving the planned row is reused and advanced to `prepared` without duplicate insertion or order drift.
- [ ] Add an Alembic upgrade test that seeds a historical stage-scoped artifact without a parent, upgrades, and obtains an empty `PRAGMA foreign_key_check`.
- [ ] Run focused tests and confirm the current write ordering/backfill assertions fail.
- [ ] In `PlanningEvidenceApplicationService.create()`, insert or validate the run-owned `MigrationStageModel` and flush it before `_write_artifacts()`.
- [ ] In `StageExecutionApplicationService._persist_prepared_stage()`, update the planned record instead of creating a second record.
- [ ] Create revision `20260729_34` with `down_revision = "20260729_33"`; derive one parent per distinct `(run_id, stage_id)` in historical `artifact_metadata`, populate safe nullable version fields, deterministic stage order, and status `planned`.
- [ ] Keep downgrade data-safe: remove only backfilled rows that still have no execution-owned child state, or leave rows in place if deletion would violate a foreign key.
- [ ] Run:

```powershell
python -m pytest backend/tests/test_planning_evidence_persistence_api_s2_f06_i02.py backend/tests/test_stage_execution_application_service.py backend/tests/test_migration_schema_upgrade.py -q
```

### Task 6: Make Planning reviewer outcomes durable and non-technical

**Files:**

- Modify: `backend/app/domain/planning_review.py`
- Modify: `backend/app/services/planning_review_application_service.py`
- Modify: `backend/app/services/planning_review_evidence_application_service.py`
- Modify: `backend/app/services/planning_job_service.py`
- Modify: `backend/app/orchestration/planning.py`
- Modify: `backend/app/repositories/planning_review_models.py`
- Modify: `backend/alembic/versions/20260729_34_run_readiness_remediation.py`
- Test: `backend/tests/test_planning_review_application_service_s2_f07_i01.py`
- Test: `backend/tests/test_planning_review_evidence_s2_f07_i02.py`
- Test: `backend/tests/test_planning_failure_classification.py`
- Test: `backend/tests/test_planning_dispatch_recovery.py`

- [ ] Define `PlanningReviewOutcome` containing the safe proposer narrative, reviewer decision/notes/concerns, both checksums, usage, revision count, and an optional accepted `PlanningPackage`.
- [ ] Add service tests for final `accept`, `request_revision`, `reject`, and `insufficient_context`; all four must return an outcome and preserve reviewer detail, while only accept has a G06 package.
- [ ] Add evidence tests proving non-accept outcomes persist proposer/reviewer invocations, outputs, usage, and a durable review record without creating G06.
- [ ] Add orchestration tests proving non-accept outcomes become `review_revision_required`, `review_rejected`, or `review_insufficient_context`, never `technical_failed`.
- [ ] Run focused tests and confirm current `PLANNING_REVIEW_NOT_ACCEPTED` behavior fails them.
- [ ] Return `PlanningReviewOutcome` from `PlanningAgentService.explain()` instead of raising for governed reviewer decisions.
- [ ] Add nullable JSON `proposer_output`, JSON `reviewer_output`, integer `revision_count`, and string `outcome` columns to `PlanningReviewModel` and migration `20260729_34`; backfill existing accepted rows as `accept` and failed `PLANNING_REVIEW_NOT_ACCEPTED` rows as `unknown_nonaccept` without changing their historical artifact evidence.
- [ ] Persist safe proposer and reviewer outputs before branching on the decision.
- [ ] On accept, retain the current six explanation/G06 artifacts and G06 creation path.
- [ ] On non-accept, persist the five review evidence artifacts that exist independently of G06 (`planning-input-manifest`, proposer output, reviewer output, explanation, usage/cost), append a decision-specific audit event, leave G06 unavailable, and return a response whose `gate_status` is `not_created`.
- [ ] Extend planning-job states with the three governed outcomes and classify them as human/governance waits, not technical terminal failures.
- [ ] Keep retry classification restricted to the existing infrastructure allowlist.
- [ ] Run:

```powershell
python -m pytest backend/tests/test_planning_review_application_service_s2_f07_i01.py backend/tests/test_planning_review_evidence_s2_f07_i02.py backend/tests/test_planning_failure_classification.py backend/tests/test_planning_dispatch_recovery.py -q
```

### Task 7: Make failure evidence and run state describe the actual failing stage

**Files:**

- Modify: `backend/app/services/planning_evidence_application_service.py`
- Modify: `backend/app/orchestration/planning.py`
- Modify: `backend/app/state/transition_service.py`
- Test: `backend/tests/test_planning_dispatch_recovery.py`
- Test: `backend/tests/test_state_transition_service.py`

- [ ] Add tests that force input resolution, plan generation, and technical review failures.
- [ ] Assert the artifact path, first event type, final reason, payload, run status, run phase status, and planning-job status all agree with the actual stage.
- [ ] Run the tests and confirm the current generic input-resolution artifact/event and “before plan creation” reason fail.
- [ ] Parameterize `record_failure()` with stage-specific artifact filenames and policy metadata.
- [ ] Use `PLANNING_INPUT_RESOLUTION_FAILED` only for input resolution; use `PLANNING_FAILED` directly for later technical failures and `PLANNING_RETRY_SCHEDULED` only for allowlisted transient failures.
- [ ] Set a terminal technical failure to `MigrationRunModel.status = "FAILED"` and `phase_status = "failed"` while retaining the planning phase; do not mark governed reviewer outcomes failed.
- [ ] Construct the final reason from the real stage, such as `planning review failed technically`, and preserve the safe diagnostic/error code.
- [ ] Run:

```powershell
python -m pytest backend/tests/test_planning_dispatch_recovery.py backend/tests/test_state_transition_service.py -q
```

### Task 8: Regression, schema, artifact, and fresh-run proof

**Files:**

- Modify if required by verified failures only: `backend/tests/test_planning_review_verification_s2_f07_i04.py`
- Create: the fresh run root returned by the normal application workflow under `.migration-factory/runs`
- Do not modify: `.migration-factory/runs/run-16a48fc55de7/**`

- [ ] Run formatting/static checks configured by the repository.
- [ ] Run the complete backend suite:

```powershell
python -m pytest backend/tests -q
```

- [ ] Upgrade a disposable database from the pre-remediation head through `20260729_34`; run both `PRAGMA integrity_check` and `PRAGMA foreign_key_check`.
- [ ] Re-hash every registered artifact and metadata sidecar in the preserved failed run to prove it was not modified.
- [ ] Launch a new run from the same source through normal APIs/workers.
- [ ] Approve G02, G03, G04, G05, and G06 using current package checksums and state versions.
- [ ] Stop immediately after G06 approval. Confirm no stage sandbox, transformation command execution, or transformation event exists.
- [ ] Audit the fresh run:

```text
registered payload missing = 0
registered checksum mismatch = 0
unregistered payload = 0
orphan metadata sidecar = 0
invalid JSON payload = 0
SQLite integrity_check = ok
SQLite foreign_key_check rows = 0
G06 current status = approved
planning job status = waiting_g06 or completed after approval projection
transformation artifacts/events/commands = 0
```

- [ ] Record the fresh run path, run ID, exact verification commands, pass counts, and any residual non-blocking warnings.
- [ ] Declare `READY_FOR_TRANSFORMATION_DEVELOPMENT` only if every item above is satisfied; otherwise report the remaining blocker with direct evidence.
