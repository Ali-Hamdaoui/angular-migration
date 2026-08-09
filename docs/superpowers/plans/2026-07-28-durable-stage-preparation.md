# Durable Stage Preparation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn an approved G06 stage start into an idempotent, durable prepared stage with a contained copied workspace, alias binding, artifacts, and executable step records.

**Architecture:** Use `BASELINE_SANDBOX` as the read-only copy source and create a stage-specific child under `STAGE_SANDBOX`. Stage start reserves the validated idempotency key in a short transaction, copies/fingerprints outside every transaction, then rechecks and persists `MigrationStageModel`, `StageStepModel`, immutable evidence, the `STAGE_WORKSPACE_<stage>` alias, and the preparation transition in a second short transaction.

**Tech Stack:** Python 3, SQLAlchemy, local filesystem artifact store, pytest.

## Global Constraints

- G06 checksum/state/workspace validation remains mandatory.
- Never mutate `BASELINE_SANDBOX` or the external source.
- Filesystem copy must run outside every database transaction and finish before authoritative success state is persisted.
- Replays return the existing prepared state; a failed copy creates no success state.
- Do not commit or push without explicit user authorization.

---

### Task 1: Add a stage-preparation application service

**Files:**
- Create: `backend/app/services/stage_preparation_application_service.py`
- Test: `backend/tests/test_stage_preparation_application_service.py`

**Interfaces:**
- Consumes: `prepare(run_id, stage_plan, actor, idempotency_key)` and authoritative run aliases.
- Produces: a prepared stage ID, `STAGE_WORKSPACE_<stage_id>` alias, fingerprint, and copy-report artifact inputs.

- [ ] **Step 1: Write a failing real-SQLite test for preparation**

```python
def test_prepare_copies_baseline_and_returns_bound_stage_alias(db_session, tmp_path):
    result = service.prepare("run-1", stage_plan, "operator", "stage-start-1")
    assert result.workspace_alias == "STAGE_WORKSPACE_ANGULAR_18_TO_19"
    assert Path(result.workspace_path).is_dir()
    assert result.fingerprint.startswith("sha256:")
```

- [ ] **Step 2: Run the test to prove the service is absent**

Run: `Set-Location backend; $env:PYTHONPATH='.'; python -m pytest -q tests/test_stage_preparation_application_service.py -k copies_baseline`

Expected: FAIL because no preparation service or alias binding exists.

- [ ] **Step 3: Implement copy/fingerprint after reservation and before persistence**

```python
source = Path(aliases["BASELINE_SANDBOX"])
root = Path(aliases["STAGE_SANDBOX"])
target = root / stage_plan.stage_id
report = self._copier.copy(source, target, registered_root=root)
alias = "STAGE_WORKSPACE_" + stage_plan.stage_id.upper().replace("-", "_")
```

- [ ] **Step 4: Prove replay and failed-copy behavior**

Run: `Set-Location backend; $env:PYTHONPATH='.'; python -m pytest -q tests/test_stage_preparation_application_service.py`

Expected: PASS; repeat request returns the same result, while an invalid copy target leaves no stage rows or alias.

### Task 2: Persist stage, steps, artifacts, alias, and transition

**Files:**
- Modify: `backend/app/services/stage_execution_application_service.py:StageExecutionApplicationService.start`
- Modify: `backend/app/api/stage_execution_contracts.py:StageStartResponse`
- Test: `backend/tests/test_stage_execution_application_service.py`

**Interfaces:**
- Consumes: validated approved G06 and `StagePreparationResult`.
- Produces: one `MigrationStageModel`, rows for every planned command, bound workspace alias, immutable copy-report/fingerprint artifacts, and a prepared-stage response.

- [ ] **Step 1: Write a failing stage-start integration test**

```python
def test_start_creates_durable_stage_steps_and_workspace_evidence(service, seeded_run):
    response = service.start("run-1", "angular-18-to-19", request, "operator")
    assert stage_row.status == "prepared"
    assert step_count == 7
    assert response.workspace_fingerprint.startswith("sha256:")
```

- [ ] **Step 2: Run it to prove current start only emits an event**

Run: `Set-Location backend; $env:PYTHONPATH='.'; python -m pytest -q tests/test_stage_execution_application_service.py -k durable_stage_steps`

Expected: FAIL because no stage rows, step rows, artifacts, or alias are written.

- [ ] **Step 3: Reserve, prepare, then persist in separate short transactions**

```python
with scope() as session:
    reservation = reserve_validated_stage_start(session, run_id, stage_id, request, actor)
prepared = preparation.prepare(reservation)
with scope() as session:
    run = reload_and_recheck_reservation(session, reservation)
    run.workspace_aliases = {**(run.workspace_aliases or {}), prepared.workspace_alias: prepared.workspace_path}
    session.add(MigrationStageModel(id=prepared.stage_id, run_id=run_id, stage_order=1, status="prepared", created_at=now))
```

- [ ] **Step 4: Run focused stage and sandbox regressions**

Run: `Set-Location backend; $env:PYTHONPATH='.'; python -m pytest -q tests/test_stage_preparation_application_service.py tests/test_stage_execution_application_service.py tests/test_stage_preparation_primitives.py`

Expected: PASS, with no authoritative preparation state after a copy failure.

- [ ] **Step 5: Review the vertical-slice diff; do not commit**

Run: `git diff --check; git diff --stat`

Expected: changes are limited to preparation, protected stage start, response contract, and focused tests.
