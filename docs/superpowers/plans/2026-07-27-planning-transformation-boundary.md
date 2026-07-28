# Planning-to-Transformation Boundary Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the evidence-bound, project-aware path from deterministic planning through G06, authoritative stage preparation/G07, governed commands, and durable stage progression.

**Architecture:** SQLite remains authoritative. Planning resolves only persisted discovery/baseline/compatibility evidence; the Transition Service owns workflow changes; the registry/policy engine owns command authorization; and the Artifact Store owns finalized evidence. G06 approves an exact executable plan and moves to a legal preparation wait, while stage preparation creates the physical aggregate and sandbox before G07.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy, Alembic, pytest, React/TypeScript.

## Global Constraints

- Stay on `hermes/01-command-runtime`; do not create a branch, commit, push, merge, rebase, cherry-pick, reset, or modify `dev/main`.
- Source snapshot remains immutable.
- Do not introduce a subprocess path outside `CommandExecutor` and the command registry/policy engine.
- Do not use an artifact-set checksum as a physical workspace fingerprint.
- Do not invent build, test, lint, production configuration, project, or builder values.
- Do not hold database transactions across LLM calls, filesystem copies, subprocesses, or approval waits.
- Every production change begins with a failing regression test.

### Task 1: Correct snapshot-root authority and preserve diagnostic lineage

**Files:**
- Modify: `backend/app/services/migration_workspace_layout_service.py`, snapshot/discovery handoff service identified by the failing test.
- Test: `backend/tests/test_authoritative_angular18_integration.py`, new snapshot-root regression test.

- [ ] Write a failing test where the persisted snapshot path is a child of the source-snapshot alias and discovery reads the child path containing `package.json` and `angular.json`.
- [ ] Run the test and confirm it fails with the current `ANGULAR_JSON_MISSING` result.
- [ ] Make downstream discovery consume the persisted concrete snapshot path while keeping the source alias immutable and parent-contained.
- [ ] Run the focused test and the existing snapshot/security tests.

### Task 2: Add typed project-aware planning inputs

**Files:**
- Modify: `backend/app/services/planning_input_resolver.py`, `backend/app/orchestration/planning.py`, `backend/app/domain/planning.py`.
- Modify: persisted discovery/baseline models only where existing evidence lacks required fields.
- Test: new `backend/tests/test_project_aware_planning.py`.

- [ ] Write failing tests for application, browser, library, SSR/custom, multi-project, absent build/test/lint, absent production configuration, and unsupported package manager cases.
- [ ] Add `ResolvedPlanningInputs` with exact target records, scripts, builders/configurations, package-manager/lockfile/npmrc metadata, baseline results, runtime profile, compatibility provenance, evidence checksum, and physical workspace fingerprint.
- [ ] Resolve builder and commands from persisted evidence; return typed `NOT_CONFIGURED`, `MANUAL_PREPARATION_REQUIRED`, or blocking findings instead of generic commands.
- [ ] Remove the hardcoded application builder from orchestration and bind the exact resolved inputs.
- [ ] Run the new focused suite and planning regressions.

### Task 3: Separate evidence-set and physical-input checksums

**Files:**
- Modify: `backend/app/domain/planning.py`, planning/compatibility models and services.
- Add: next Alembic migration after `20260727_30_g06_decisions.py`.
- Test: `backend/tests/test_planning_evidence_persistence_api_s2_f06_i02.py`, new checksum-lineage tests.

- [ ] Write failing tests proving an evidence checksum and physical workspace fingerprint are stored and compared independently.
- [ ] Add `evidence_set_checksum` and `input_workspace_fingerprint` to exact stage-plan/G06 contracts and persistence while retaining auditable legacy fields.
- [ ] Carry compatibility resolution/catalogue/entry/registry/support/warnings/fixture/profile provenance into exact plan and G06 package checksums.
- [ ] Reject duplicate global CLI targets unless they equal the first route CLI and match the Angular core major.
- [ ] Verify clean upgrade/current-schema behavior for the migration.

### Task 4: Bind generated commands to immutable versioned templates

**Files:**
- Modify: `backend/app/domain/planning.py`, `backend/app/services/planning_application_service.py`, `backend/app/services/command_registry_service.py`.
- Modify: `backend/app/repositories/models/workflow.py`.
- Add: Alembic migration replacing command-id-only uniqueness with template identity/version uniqueness.
- Test: `backend/tests/test_planning_command_registry_contract.py`, command registry/authorization regressions.

- [ ] Write failing tests for template resolution, template-version mismatch, missing alias, invalid token/package/project/configuration, and every generated command.
- [ ] Add `template_id`, `template_version`, typed parameter bindings, resolved argv, runtime checksum, network/timeout/cancellation data to each reference.
- [ ] Register approved bootstrap/update/version/build/test/lint templates; allow only discovered command variants.
- [ ] Add a production contract test that loads a generated stage plan and authorizes every reference through the real registry/policy path.
- [ ] Run command policy and authorization tests.

### Task 5: Make G06 an atomic executable-plan approval

**Files:**
- Modify: `backend/app/services/planning_review_evidence_application_service.py`, `backend/app/domain/contracts.py`, `backend/app/state/transition_service.py`.
- Modify: G06 models/contracts and add the next migration if approval binding fields are missing.
- Test: `backend/tests/test_g06_atomic_approval.py`, `backend/tests/test_planning_gate_integrity.py`.

- [ ] Write failing tests proving approved G06 marks the exact migration/stage plan executable, persists an immutable binding, and enters `WAITING_STAGE_PREPARATION` without `STAGE_CREATED`.
- [ ] Verify all active pointers, plan/stage/review/evidence/compatibility checksums, physical input fingerprint, actor, event sequence, and state version in one transaction.
- [ ] Invalidate revised-plan, pointer, evidence, catalogue, or workspace drift approvals and route all state changes through Transition Service.
- [ ] Run state-machine, gate integrity, and idempotency tests.

### Task 6: Implement idempotent stage preparation and G07

**Files:**
- Create/modify: `backend/app/services/stage_preparation_application_service.py`, `backend/app/api/routes/stage_execution.py`, `backend/app/api/stage_execution_contracts.py`.
- Modify: stage models and workspace layout/copy services; add Alembic migration for preparation evidence fields if needed.
- Test: `backend/tests/test_stage_preparation.py`, path/workspace security regressions.

- [ ] Write failing tests for exact stage aggregate/steps, duplicate prepare replay, copy exclusions, source immutability, containment, input fingerprint drift, finalized artifacts, and G07-required progression.
- [ ] Create/load the exact stage aggregate, lock the approved plan, copy baseline/sealed output into an exact stage sandbox, fingerprint it, and register `STAGE_WORKSPACE_<SOURCE>_TO_<TARGET>`.
- [ ] Finalize and register stage-start, profile, input, fingerprint, copy-report, sandbox-verification, plan-lock, and G07 artifacts before exposing `WAITING_G07_APPROVAL`.
- [ ] Add G07 decision binding and move to `SANDBOX_READY` only after checksum re-verification.
- [ ] Run stage preparation and path security tests.

### Task 7: Correct stage retrieval and portable containment

**Files:**
- Modify: planning/stage retrieval and authorization services, `backend/app/services/path_validation_service.py`.
- Test: new multi-stage retrieval and Windows/POSIX/UNC containment tests.

- [ ] Write failing tests proving requested stage retrieval uses the authoritative stage pointer and rejects drive, UNC, mixed-separator, and traversal escapes on POSIX.
- [ ] Classify paths using `PureWindowsPath`/`PurePosixPath` before canonicalization and enforce containment under the exact registered stage alias.
- [ ] Run path, authorization, and stage retrieval regressions.

### Task 8: Add durable transformation worker checkpoints

**Files:**
- Create/modify: `backend/app/orchestration/stage_worker.py`, `backend/app/services/stage_transformation_service.py`, command execution evidence services.
- Modify: stage/step/execution models and add migrations as required.
- Test: new worker restart, failure, cancellation, duplicate-delivery, G08/G09/G12, sealing, copy-forward, and no-outside-sandbox tests.

- [ ] Write failing tests for one durable step at a time and restart-safe completed mutations.
- [ ] Implement only registry-authorized bootstrap/update/validation/build/test/lint operations through `CommandExecutor` with durable authorization, execution, output, fingerprints, event, and state-version evidence.
- [ ] Add lockfile/package/.npmrc integrity checkpoint before final install and seal/copy-forward verification.
- [ ] Resolve each later stage from the verified sealed prior output and exact compatibility catalogue snapshot.
- [ ] Run worker-focused and end-to-end fixture tests.

### Task 9: Complete frontend authoritative projection and verification

**Files:**
- Modify: relevant planning/stage frontend components, API types, and tests.
- Test: frontend unit/typecheck/lint/build suites and backend full suite.

- [ ] Write failing UI tests for planning review failures, G06 wait/approval, preparation/G07, command lifecycle, G08/G09/G12, sealing, and next-stage resolution.
- [ ] Render only backend snapshots/events, expose correlation IDs and diagnostic artifact links, and enable commands only when exact plan/template/alias checks pass.
- [ ] Run clean migrations, focused suites, full backend suite, frontend tests/typecheck/lint/build, `git diff --check`, and a read-only acceptance review.
