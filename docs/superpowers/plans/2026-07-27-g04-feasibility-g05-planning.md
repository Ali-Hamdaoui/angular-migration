# G04 to G06 Durable Planning Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the backend-owned, durable G04 approval to feasibility/G05/planning/G06 continuation and align the frontend with authoritative state.

**Architecture:** Persist exact source evidence on `MigrationRunModel`, assemble all planning inputs in a backend service, and expose a command endpoint that only accepts concurrency/idempotency data. A database-backed dispatcher claims queued/due jobs with leases, retries missing evidence with bounded timestamps, leaves human-wait states untouched, and resumes G05 continuation through the injected session factory.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, Alembic, pytest, Next.js/React, Vitest/Testing Library.

## Global Constraints

- Remain on `hermes/01-command-runtime`; do not create branches or commit/push.
- SQLite and the Transition Service remain authoritative.
- Do not weaken validation or fabricate catalogue, registry, checksum, or runtime evidence.
- Do not rely on FastAPI `BackgroundTasks` as the durable worker.
- Use TDD: each production behavior starts with a failing regression test.
- Human-wait states `waiting_g05` and `waiting_g06` are not claimable.
- G05 is created only after feasibility artifacts are durably registered.

---

### Task 1: Capture the baseline and exact root cause

**Files:**
- Inspect `backend/app/main.py`, `backend/app/orchestration/planning.py`, `backend/app/services/planning_input_resolver.py`, `frontend/src/components/FeasibilityPanel.tsx`, and existing planning/compatibility tests.
- Test: add focused regression tests under `backend/tests/test_g04_planning_workflow.py`.

- [ ] Write tests for the current failure boundary: empty browser evidence is rejected before the service; a fresh G04-approved run produces a queued job without requiring synchronous feasibility inputs.
- [ ] Run the focused tests and record the expected failures.
- [ ] Keep the observed error codes and database facts for the final report.

### Task 2: Persist authoritative exact source evidence

**Files:**
- Modify: `backend/app/services/execution_profile_application_service.py`.
- Modify: `backend/app/orchestration/source_intake.py` only if the approved source intake path does not already pass the exact version.
- Test: `backend/tests/test_execution_profile_application_service.py` or a focused new source-version test.

- [ ] Add a failing test proving an exact `@angular/core` version reaches the run projection.
- [ ] Persist `request.source_angular_exact` through the existing state-transition/application-service boundary.
- [ ] Reject family values such as `18.x` for new planning inputs and preserve idempotent replay.
- [ ] Verify execution profile and run exact versions match.

### Task 3: Add backend-owned catalogue and registry evidence authority

**Files:**
- Create/modify: `backend/app/services/compatibility_catalogue_provider.py`.
- Create/modify: `backend/app/services/registry_snapshot_builder.py`.
- Modify: `backend/app/services/planning_input_resolver.py`.
- Modify: `backend/app/api/routes/compatibility.py` to stop owning catalogue truth.
- Test: focused resolver/provider tests.

- [ ] Add failing tests for all three missing-input codes: source, catalogue, and registry.
- [ ] Implement configured catalogue load/schema/checksum verification and immutable metadata persistence/reuse.
- [ ] Build run-bound registry snapshots only from approved capability/probe evidence and preserve provenance/checksum fields.
- [ ] Make the resolver use `source_version_detected`, compare it with the selected profile, bind only approved G04 artifacts, and return a typed internal feasibility request.

### Task 4: Make feasibility resolution a backend command

**Files:**
- Modify: `backend/app/api/routes/compatibility.py`.
- Modify: `backend/app/api/compatibility_contracts.py`.
- Modify: `backend/app/services/compatibility_evidence_application_service.py` only where needed for command delegation.
- Modify: `frontend/src/api/compatibility.ts`.
- Modify: `frontend/src/components/FeasibilityPanel.tsx`.
- Regenerate/update: `frontend/src/types/generated/api.ts` from the backend contract.
- Test: backend API and frontend FeasibilityPanel tests.

- [ ] Add a failing API test for `POST /runs/{run_id}/feasibility/actions/resolve` accepting only expected state version and idempotency key.
- [ ] Assemble evidence server-side and return queued/running authoritative job state using the project’s async command semantics.
- [ ] Keep the detailed `FeasibilityCreateRequest` internal; reject empty required evidence rather than accepting it.
- [ ] Disable the frontend action until backend planning state says it is actionable and remove all browser-supplied evidence fields/casts.

### Task 5: Implement durable planning dispatch, retry, and recovery

**Files:**
- Modify: `backend/app/repositories/models/workflow.py`.
- Modify: `backend/app/services/planning_job_service.py`.
- Modify: `backend/app/orchestration/planning.py`.
- Modify: `backend/app/main.py` startup recovery.
- Add: Alembic migration after `20260726_27_g05_input_bundle.py`.
- Test: fresh-run, worker-claim, restart-recovery, retry-recovery, and human-wait tests.

- [ ] Add failing tests for due retries, bounded `next_attempt_at`, max attempts, lease reclaim, and non-claimable human waits.
- [ ] Add durable job fields for max attempts, next attempt, error message, first/terminal failure, and correlation identity.
- [ ] Implement one dispatcher/worker entry point that recovers queued and due retry jobs, claims exactly once, executes feasibility, and records durable events/state.
- [ ] Ensure G04 queues exactly one idempotent job after commit; remove request-thread dependence.
- [ ] Ensure blocked feasibility is a business result, not technical failure, and successful feasibility transitions to `waiting_g05`.

### Task 6: Continue after G05 using the configured database/session

**Files:**
- Modify: `backend/app/orchestration/planning.py`.
- Modify: `backend/app/api/routes/compatibility.py` and/or the G05 application service.
- Test: isolated database/session G05 continuation test.

- [ ] Add a failing test that approves G05 through the API with an injected test session factory.
- [ ] Resume the same planning job, create plan/review evidence, and set `waiting_g06` or terminal state.
- [ ] Prove no global/default database session is opened by continuation.
- [ ] Preserve G05-approved artifact bundle and idempotency across retries.

### Task 7: Expose authoritative planning projection and frontend state

**Files:**
- Modify: `backend/app/domain/contracts.py` and `backend/app/services/migration_run_service.py`.
- Modify: generated frontend DTOs and `frontend/src/components/ExecutionProfilePanel.tsx`.
- Modify: `frontend/src/components/FeasibilityPanel.tsx`.
- Test: run-state API and frontend focused tests.

- [ ] Add failing tests for planning-job projection and structured failure details.
- [ ] Project job status, step, attempts, retry timing, error fields, correlation, and updated timestamp.
- [ ] Render queued/running/retry/waiting/blocked/failed states from authoritative snapshots/events.
- [ ] Use `source_angular_exact` and show unresolved state; remove the `18.0.0` fallback and unsafe casts.

### Task 8: Verify migrations, full suites, and independent review

**Files:**
- Inspect all changed files and migration chain.
- Update only relevant evidence/documentation if required.

- [ ] Run focused backend tests, frontend focused tests, migration upgrade/current checks, backend full suite, frontend tests, typecheck, lint, and build.
- [ ] Run `git diff --check`, confirm only issue-related files changed, and perform a read-only acceptance review.
- [ ] Report exact commands, exit codes, pass/fail/skip counts, root-cause evidence, remaining risks, and explicitly avoid claiming completion if the mandatory fresh-run/restart scenario is not verified.

