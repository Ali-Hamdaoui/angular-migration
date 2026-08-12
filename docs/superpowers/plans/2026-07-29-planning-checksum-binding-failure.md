# Planning Checksum Binding Failure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the live Planning proposer and reviewer copy backend-computed checksum bindings instead of attempting to calculate SHA-256 values from large JSON inputs.

**Architecture:** `PlanningAgentService` remains the deterministic checksum owner and keeps its fail-closed equality checks. It supplies the exact checksum values in small trusted context segments, while the model remains responsible only for narrative and review content.

**Tech Stack:** Python 3.12, Pydantic, pytest, governed Azure OpenAI gateway contracts.

## Global Constraints

- Preserve the existing `PlanningNarrative`, `PlanningReview`, and persisted package contracts.
- Keep `PLANNING_INPUT_CHECKSUM_MISMATCH` and `PLANNING_REVIEW_CHECKSUM_MISMATCH` fail-closed validation.
- Do not change database state, generated Angular output, approval policy, or unrelated worktree changes.
- Do not commit or push without explicit user authorization.

---

### Task 1: Supply trusted Planning checksum bindings

**Files:**
- Modify: `backend/app/services/planning_review_application_service.py`
- Test: `backend/tests/test_planning_review_application_service_s2_f07_i01.py`

**Interfaces:**
- Consumes: `_deterministic_plan_checksum(plan, stage_plan) -> str` and `_checksum(proposer_output) -> str`.
- Produces: `LlmContextSegment` values named `deterministic-plan-binding` and `proposer-output-binding`, each containing canonical JSON with the exact backend-computed checksum.

- [ ] **Step 1: Write the failing proposer regression test**

Create a controlled gateway that never hashes plan JSON. For `PLAN_RATIONALE`, it locates `deterministic-plan-binding`, copies `deterministic_plan_checksum`, and returns a valid narrative.

- [ ] **Step 2: Write the failing reviewer regression test**

For `PLANNING_REVIEW`, the same gateway locates both trusted binding segments, copies `deterministic_plan_checksum` and `proposer_output_checksum`, and returns an accepted review.

- [ ] **Step 3: Run the focused test and verify RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_planning_review_application_service_s2_f07_i01.py -q
```

Expected: FAIL because the binding segments do not exist in the current Planning requests.

- [ ] **Step 4: Add the minimal trusted binding contexts**

In `PlanningAgentService.explain`, append:

```python
LlmContextSegment(
    segment_id="deterministic-plan-binding",
    label="deterministic plan checksum binding",
    content=_json({"deterministic_plan_checksum": deterministic_checksum}),
    untrusted=False,
)
```

In `_review`, append:

```python
LlmContextSegment(
    segment_id="proposer-output-binding",
    label="planning proposer checksum binding",
    content=_json({"proposer_output_checksum": proposer_checksum}),
    untrusted=False,
)
```

Update both trusted system policies to instruct exact copying of supplied binding values. Retain both equality checks unchanged.

- [ ] **Step 5: Run the focused test and verify GREEN**

Run the focused command from Step 3. Expected: all tests pass.

- [ ] **Step 6: Verify fail-closed tamper behavior**

Run the existing checksum-mismatch tests and add a changed-token case if coverage does not already prove that a model-returned value different from the trusted context is rejected.

- [ ] **Step 7: Run relevant regressions**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_planning_review_application_service_s2_f07_i01.py backend\tests\test_planning_review_evidence_s2_f07_i02.py backend\tests\test_planning_dispatch_recovery.py -q
backend\.venv\Scripts\python.exe -m compileall -q backend\app
```

Expected: zero failures and successful compilation.

- [ ] **Step 8: Reproduce the production-shaped request**

Use a controlled copy-only gateway with the persisted plan/stage pair from `run-b21277c2ce8a`. Assert that the computed `sha256:6650c1b00b7153b909f66832dc369894026e0829ec88275bfe250568e947e10b` is present in the trusted proposer and reviewer context, and that the package reaches an accepted review.

- [ ] **Step 9: Inspect the final diff**

Run:

```powershell
git diff --check
git status --short
git diff -- backend/app/services/planning_review_application_service.py backend/tests/test_planning_review_application_service_s2_f07_i01.py
```

Expected: only the focused service/test behavior plus this plan document; pre-existing unrelated changes remain untouched.
