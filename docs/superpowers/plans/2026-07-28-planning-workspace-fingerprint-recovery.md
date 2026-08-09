# Planning Workspace Fingerprint Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Apply the supplied 12-file patch so approved G03 workspace identity reaches G04/G05/planning and legacy null-fingerprint runs can recover safely.

**Architecture:** Keep G03 as the authoritative physical identity, derive and validate it in backend services, and create a new fingerprint-bound feasibility/G05 command for legacy rows. Preserve append-only evidence and expose the recovery through the existing frontend panel.

**Tech Stack:** Python, SQLAlchemy, pytest, React/TypeScript, Vitest, Git unified patch.

## Global Constraints

- The frontend projects backend state only.
- SQLite and the Transition Service own workflow truth.
- Historical artifacts and evidence remain immutable and checksum-bound.
- Mutations require expected state versions and stable idempotency keys.
- Do not commit, push, switch branches, or repair unrelated environment failures.

### Task 1: Apply backend authority and retry changes

**Files:**
- Modify: `backend/app/services/analysis_evidence_application_service.py`
- Modify: `backend/app/services/planning_input_resolver.py`
- Modify: `backend/app/services/compatibility_evidence_application_service.py`
- Modify: `backend/app/orchestration/planning.py`
- Modify: `backend/app/services/planning_review_evidence_application_service.py`

- [ ] Apply the backend hunks from the supplied handoff document.
- [ ] Run the focused backend tests covering analysis, compatibility, workspace binding, planning failure classification, dispatch recovery, and review persistence.

### Task 2: Apply frontend recovery and terminal-state projection

**Files:**
- Modify: `frontend/src/components/FeasibilityPanel.tsx`
- Modify: `frontend/src/components/MigrationPlanPanel.tsx`
- Modify: `frontend/src/hooks/usePlanReview.ts`

- [ ] Add the authoritative regeneration action with `feasibility-rebind` idempotency namespace.
- [ ] Disable G05 approval for missing fingerprints.
- [ ] Render terminal failures without an `of max_attempts` claim.
- [ ] Run the targeted Vitest test and frontend typecheck/build where dependencies are available.

### Task 3: Apply and verify regression coverage

**Files:**
- Modify: `backend/tests/test_analysis_evidence_persistence_api_s2_f04_i02.py`
- Modify: `backend/tests/test_compatibility_evidence_persistence_api_s2_f05_i02.py`
- Create: `backend/tests/test_planning_workspace_fingerprint_binding.py`
- Modify: `frontend/src/components/__tests__/FeasibilityPanel.test.tsx`

- [ ] Apply the test hunks from the handoff.
- [ ] Run `git diff --check`.
- [ ] Run the complete focused backend suite and record passed, failed, and blocked checks exactly.
- [ ] Run the frontend targeted test and report missing dependency failures separately if they occur.

### Task 4: Independent read-only review

**Files:**
- Inspect all changed files and the design/plan documents.

- [ ] Check every acceptance criterion against the resulting diff and tests.
- [ ] Confirm no historical G04/G05 mutation or unrelated file change was introduced.
- [ ] Report remaining manual Windows end-to-end verification requirements.
