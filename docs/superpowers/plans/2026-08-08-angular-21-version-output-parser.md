# Angular 21 Version Output Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make four-source verification accept Angular 21's padded `ng version` labels while retaining compact Angular 18–20 support and all fail-closed checks.

**Architecture:** Keep `TransformerWorkflow` and the `angular-version-verify` command unchanged. Adjust only `AngularTransformationEvidenceService` so it matches semantic labels followed by optional whitespace and a required colon, with one focused regression test proving the Angular 21 boundary.

**Tech Stack:** Python 3.11+, pytest, Ruff

## Global Constraints

- Preserve all four version sources and the existing target-major and resolved-version agreement rules.
- Do not modify command templates, command registry entries, stage plans, workflow state, persistence, gates, fingerprints, or frontend contracts.
- Do not address the pre-existing v2/v3 command-template test drift or the `--allow-dirty` policy contradiction.
- Do not switch to `ng version --json` in this patch.
- Do not mutate or manually recover any operational migration run.
- Do not use `--force`, `--legacy-peer-deps`, manual lockfile edits, or evidence bypasses.

---

### Task 1: Accept padded Angular 21 version labels

**Files:**

- Modify: `backend/tests/test_angular_transformation_evidence.py`
- Modify: `backend/app/services/angular_transformation_evidence_service.py:43-50,134-138`

**Interfaces:**

- Consumes: `AngularTransformationEvidenceService.build(..., ng_version_output: str, ...)`
- Produces: unchanged version-evidence dictionaries whose `core_sources.ng_version` and `cli_sources.ng_version` are populated for compact and padded labels

- [ ] **Step 1: Add the failing Angular 21 regression test**

Append this test to `backend/tests/test_angular_transformation_evidence.py`:

```python
def test_four_source_version_proof_accepts_angular_21_padded_ng_version_headers(
    tmp_path: Path,
):
    before = tmp_path / "before"
    workspace = tmp_path / "workspace"
    before.mkdir()
    workspace.mkdir()
    _write_json(before / "package.json", {"dependencies": {"@angular/core": "20.3.0"}})
    _write_json(
        workspace / "package.json",
        {"dependencies": {"@angular/core": "21.0.0", "@angular/cli": "21.0.0"}},
    )
    _write_json(
        workspace / "package-lock.json",
        {
            "packages": {
                "node_modules/@angular/core": {"version": "21.0.0"},
                "node_modules/@angular/cli": {"version": "21.0.0"},
            }
        },
    )
    _write_json(workspace / "node_modules/@angular/core/package.json", {"version": "21.0.0"})
    _write_json(workspace / "node_modules/@angular/cli/package.json", {"version": "21.0.0"})

    versions, _ = AngularTransformationEvidenceService().build(
        str(workspace),
        str(before),
        target_core="21.0.0",
        target_cli="21.0.0",
        ng_version_output=(
            "Angular CLI       : 21.0.0\n"
            "Angular           : 21.0.0\n"
            "Node.js           : 20.19.1\n"
            "Package Manager   : npm 10.8.2\n"
        ),
        angular_execution_id="execution-angular-21",
    )

    assert versions["status"] == "verified"
    assert versions["cli_sources"]["ng_version"] == "21.0.0"
    assert versions["core_sources"]["ng_version"] == "21.0.0"
```

- [ ] **Step 2: Run the new test and verify RED**

Run from `backend`:

```powershell
python -m pytest tests/test_angular_transformation_evidence.py::test_four_source_version_proof_accepts_angular_21_padded_ng_version_headers -q
```

Expected: one failed test. The failure must be `AngularTransformationEvidenceError: Four-source Angular version verification failed: cli.ng_version=missing, core.ng_version=missing`. A collection, import, or fixture error does not satisfy RED.

- [ ] **Step 3: Implement the minimal semantic-label matcher**

In `AngularTransformationEvidenceService.build()`, remove punctuation from the two label arguments:

```python
"ng_version": self._line_version(ng_version_output, "Angular"),
```

```python
"ng_version": self._line_version(ng_version_output, "Angular CLI"),
```

Replace `_line_version()` with:

```python
def _line_version(self, output: str, label: str) -> str | None:
    label_pattern = re.compile(rf"^\s*{re.escape(label)}\s*:")
    for line in output.splitlines():
        if label_pattern.match(line):
            return self._version(line)
    return None
```

- [ ] **Step 4: Run the new test and verify GREEN**

Run from `backend`:

```powershell
python -m pytest tests/test_angular_transformation_evidence.py::test_four_source_version_proof_accepts_angular_21_padded_ng_version_headers -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run focused behavior and integration regressions**

Run from `backend`:

```powershell
python -m pytest tests/test_angular_transformation_evidence.py -q
python -m pytest tests/test_transformer_bootstrap_vertical.py -q
```

Expected: every test in both files passes. The first file proves compact labels, padded labels, and mismatch rejection; the second proves the surrounding Transformer/G08 flow still succeeds.

- [ ] **Step 6: Run static and repository validation**

Run from `backend`:

```powershell
python -m ruff check app/services/angular_transformation_evidence_service.py tests/test_angular_transformation_evidence.py
python -m py_compile app/services/angular_transformation_evidence_service.py
```

Run from the repository root:

```powershell
git diff --check
git status --short
git diff --stat
```

Expected: Ruff and bytecode compilation exit `0`; `git diff --check` reports no errors; only the approved production file, regression test, and this plan are new or modified relative to the starting implementation commit.

- [ ] **Step 7: Inspect and commit the implementation**

Inspect the complete diff and confirm there are no changes to command policy, workflow state, version exactness, or unrelated tests. Then run:

```powershell
git add backend/app/services/angular_transformation_evidence_service.py backend/tests/test_angular_transformation_evidence.py docs/superpowers/plans/2026-08-08-angular-21-version-output-parser.md
git commit -m "fix(transformer): parse angular 21 version labels"
```

Expected: one focused implementation commit following the already committed design specification.
