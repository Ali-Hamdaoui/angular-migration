# Stage Sandbox Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject unsafe stage-sandbox copy targets before creation or traversal, while preserving deterministic copying of a valid sibling sandbox.

**Architecture:** `StageSandboxCopier.copy` resolves the registered root and source first, then rejects an equal target or any target inside the source. It also rejects a source path that resolves outside the registered root and symlink entries rather than following them. A valid target must be a sibling/descendant of the registered root but not of the source.

**Tech Stack:** Python 3, pathlib, shutil, pytest.

## Global Constraints

- The source workspace is read-only and must never be created in, copied into, or deleted by this operation.
- Reject unsafe topology before `target.mkdir` or `source.rglob`.
- Preserve deterministic fingerprints and current excluded-directory behavior.
- Do not commit or push without explicit user authorization.

---

### Task 1: Guard stage-copy topology before filesystem mutation

**Files:**
- Modify: `backend/app/services/stage_preparation_primitives.py:StageSandboxCopier.copy`
- Test: `backend/tests/test_stage_preparation_primitives.py`

**Interfaces:**
- Consumes: `copy(source: Path, target: Path, registered_root: Path | None = None)`.
- Produces: `SandboxCopyReport` only for a contained, distinct target outside the source tree; raises `ValueError` otherwise.

- [ ] **Step 1: Write failing topology tests**

```python
@pytest.mark.parametrize("target_name", ["baseline", "baseline/stage"])
def test_copy_rejects_equal_and_descendant_targets_before_copy(tmp_path, target_name):
    source = tmp_path / "baseline"
    source.mkdir()
    (source / "package.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="distinct from and outside"):
        StageSandboxCopier().copy(source, tmp_path / target_name)

    assert not (source / "stage").exists()
```

- [ ] **Step 2: Run the negative tests and observe the unsafe baseline**

Run: `Set-Location backend; $env:PYTHONPATH='.'; python -m pytest -q tests/test_stage_preparation_primitives.py -k equal_and_descendant`

Expected: FAIL because equal targets enter the copy loop and descendants recurse into the source tree.

- [ ] **Step 3: Add a single pre-copy topology guard**

```python
def _validate_target(self, source: Path, target: Path, root: Path) -> None:
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ValueError("stage sandbox containment check failed") from error
    if target == source or target.is_relative_to(source):
        raise ValueError("stage sandbox target must be distinct from and outside the source workspace")
```

Call `_validate_target` after resolving `source`, `target`, and `root`, and before `target.mkdir`.

- [ ] **Step 4: Reject symlink traversal and prove sibling copies still work**

```python
if item.is_symlink():
    raise ValueError("stage sandbox source contains an unsupported symlink")
```

Run: `Set-Location backend; $env:PYTHONPATH='.'; python -m pytest -q tests/test_stage_preparation_primitives.py`

Expected: PASS for valid sibling copy and all containment/equality/descendant/symlink tests.

- [ ] **Step 5: Review the focused diff; do not commit**

Run: `git diff --check; git diff -- backend/app/services/stage_preparation_primitives.py backend/tests/test_stage_preparation_primitives.py`

Expected: only topology validation and focused regression coverage change.
