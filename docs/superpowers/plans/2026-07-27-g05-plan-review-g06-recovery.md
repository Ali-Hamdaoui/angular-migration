# G05 → Plan → Planning Review → G06 Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion. Changes remain uncommitted per the task constraints.

**Goal:** Make the backend-owned planning continuation durable, stage-aware, evidence-bound, and correctly projected by the frontend from G05 approval through G06.

**Architecture:** SQLite remains authoritative. G05 approval enqueues one durable planning job; an atomic lease-aware worker executes one stage at a time, persisting plan and review evidence between stages. The frontend combines `/plan` responses with the authoritative `planning_job` projection and never advances workflow state locally.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, pytest, React, TypeScript, Vitest.

## Global Constraints

- Stay on the current branch; do not commit, push, merge, rebase, cherry-pick, reset, or force-push.
- Do not weaken validation or mutate historical approval evidence in place.
- Do not hold database transactions open during LLM, filesystem, subprocess, or network work.
- Do not start transformation after G06.

### Task 1: Reproduce the durable continuation and state-classification defects

**Files:** `backend/tests/test_planning_dispatch_recovery.py`, new focused backend regression tests as needed.

- [ ] Add real persistence tests for the normal `waiting_g05` → plan continuation, retry routing, terminal/human-wait classifications, and atomic claim behavior.
- [ ] Run the tests and capture the expected failures before changing production code.

### Task 2: Canonical planning-job states, atomic claims, and stage-aware orchestration

**Files:** `backend/app/services/planning_job_service.py`, `backend/app/orchestration/planning.py`, `backend/app/services/compatibility_evidence_application_service.py`.

- [ ] Define one canonical state set and predicates for terminal, claimable, retryable, human-wait, and active states.
- [ ] Make claims conditional on due time, executable stage, attempt limit, and expired/missing lease.
- [ ] Split feasibility, plan, and review execution into idempotent stage operations and route retries by `current_step`.
- [ ] Preserve domain error code/message/stage and persist missing-record failures.

### Task 3: Persist and validate independent checksum provenance and complete G05 input evidence

**Files:** compatibility/planning domain contracts, repository models, services, new Alembic revision, migration tests.

- [ ] Add `source_execution_profile_checksum` and `stage1_profile_checksum` to Stage 1/compatibility evidence without equating their payloads.
- [ ] Propagate the source checksum from the selected execution profile and independently recalculate Stage 1 integrity.
- [ ] Enforce artifact existence, checksums, artifact-set checksum, input-bundle checksum, compatibility package checksum, workspace fingerprint, and authorized profile identity.
- [ ] Mark legacy incomplete G05 packages stale/superseded with an explicit reason in a new migration; keep historical rows auditable.

### Task 4: G05/G06 idempotency and workspace binding

**Files:** compatibility/planning-review contracts and application services, repository models/migration, focused API tests.

- [ ] Ensure same-key same-payload replay is checked before state-version validation and changed payloads return `IDEMPOTENCY_PAYLOAD_MISMATCH`.
- [ ] Ensure G05 replay confirms one continuation job and G06 uses immutable decision evidence separate from pending gate identity.
- [ ] Carry and verify the authoritative workspace fingerprint through plan, review, and G06 boundaries.

### Task 5: Continuously active planning worker

**Files:** application lifecycle/worker module, worker tests.

- [ ] Add a configurable, lifecycle-owned single-iteration loop with graceful shutdown and lease-aware multi-process safety.
- [ ] Prove a retry scheduled after startup executes without restarting the API.

### Task 6: Frontend authoritative planning projection

**Files:** `frontend/src/hooks/usePlanProjection.ts`, `frontend/src/components/MigrationPlanPanel.tsx`, `frontend/src/components/FeasibilityPanel.tsx`, planning types/tests.

- [ ] Map `/plan=404` using `planning_job` states and expose retry/terminal diagnostics.
- [ ] Keep stable idempotency keys per logical G05/G06 operation, disable in-flight controls, and project the backend workspace fingerprint.
- [ ] Add focused Vitest coverage for every required job state.

### Task 7: Real-domain integration and verification

**Files:** integration tests and only directly related implementation files.

- [ ] Prove source profile checksum differs from Stage 1 checksum while source provenance matches.
- [ ] Prove G05 approval → one plan → one review → waiting G06 → G06 approval → completed planning and no transformation.
- [ ] Run focused tests, full backend/frontend checks available in the repository, `git diff --check`, and a fresh independent diff review.
