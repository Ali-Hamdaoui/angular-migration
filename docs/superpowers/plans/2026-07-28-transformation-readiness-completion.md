# Transformation Readiness Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the confirmed S2-F06/S2-F07 transformation-readiness gaps while preserving existing uncommitted work and keeping the external source read-only.

**Architecture:** Planning prompts, transformation commands, stage aliases, and runtime profiles are governed by backend-owned authorities. Approved G06 stage start prepares a contained temporary sandbox outside database transactions, fingerprints and atomically finalizes it, then persists stage rows, steps, separate preparation and fingerprint artifacts, the stage alias, ordered transitions, and the first-command continuation in a short transaction. Project facts and stage-specific runtime profiles are checksum-bound inputs to command generation.

**Tech Stack:** Python 3, Pydantic, SQLAlchemy, pytest, local filesystem artifact store.

## Global Constraints

- Preserve all pre-existing user modifications in the working tree.
- Remain on the checked-out branch; do not commit, push, switch branches, or create worktrees.
- Keep G06 and human approval gates mandatory.
- Keep SQLite/Transition Service authoritative and the external source read-only.
- Keep `CommandExecutorService` as the only production command-execution path.
- Never execute a real Angular transformation during verification.
- Do not fabricate fixture or package-availability evidence; represent unproven compatibility honestly.

---

### Task 1: Preserve safe planning prompt diagnostics

**Files:**
- Modify: `backend/app/services/planning_review_application_service.py`
- Test: `backend/tests/test_planning_review_application_service_s2_f07_i01.py`

- [ ] Add a failing test asserting proposer gateway failures retain a safe subtype, retryability, provider request ID, and transport-started flag in the application error details.
- [ ] Run the focused test and confirm it fails because the current service collapses the exception to a message only.
- [ ] Add a redacted diagnostic mapper that reads only stable `AzureGatewayError` fields and excludes provider payloads, prompts, and secrets.
- [ ] Raise `PlanningReviewApplicationError` with the mapped details for proposer and reviewer failures.
- [ ] Run planning review and gateway regression tests.

### Task 2: Unify transformation command authority

**Files:**
- Modify: `backend/app/domain/command.py`
- Modify: `backend/app/services/planning_application_service.py`
- Modify: `backend/app/command_execution/worker.py`
- Modify: `backend/app/services/command_registry_service.py`
- Test: `backend/tests/test_planning_transformation_boundary.py`
- Test: `backend/tests/test_command_registry_service.py`

- [ ] Add a failing contract test that replays every generated stage command through the domain template, database seed projection, and worker registry.
- [ ] Run it and record the current planner/registry drift.
- [ ] Define immutable transformation command definitions with argument factories for target versions and resolved script/target facts.
- [ ] Derive `DEFAULT_COMMAND_TEMPLATES`, planner references, database seed rows, and worker definitions from that authority.
- [ ] Keep placeholder matching strict: exact token counts, safe non-shell token values, and no arbitrary argument expansion.
- [ ] Run command registry, policy, planner, and worker contract tests.

### Task 3: Enforce stage alias confinement

**Files:**
- Modify: `backend/app/services/command_executor_service.py`
- Modify: `backend/app/command_execution/worker.py`
- Test: `backend/tests/test_command_registry_service.py`
- Test: `backend/tests/test_planning_transformation_boundary.py`

- [ ] Add failing tests for an authorized stage alias with unrelated aliases present and for an unbound stage alias.
- [ ] Run them and confirm full-map forwarding or unbound alias acceptance fails correctly.
- [ ] Filter worker aliases to the authorized `STAGE_WORKSPACE_*` alias only.
- [ ] Require the alias path to resolve beneath the registered stage sandbox root and reject dynamically invented aliases.
- [ ] Run command-execution and boundary regressions.

### Task 4: Make stage sandbox preparation safe and durable

**Files:**
- Modify: `backend/app/services/stage_preparation_primitives.py`
- Modify: `backend/app/services/stage_preparation_application_service.py`
- Modify: `backend/app/services/stage_execution_application_service.py`
- Modify: `backend/app/repositories/models/workflow.py`
- Create: `backend/alembic/versions/20260728_32_stage_workspace_bindings.py`
- Test: `backend/tests/test_stage_preparation_primitives.py`
- Test: `backend/tests/test_stage_preparation_application_service.py`
- Test: `backend/tests/test_stage_execution_application_service.py`

- [ ] Add failing tests which inject a copy failure, fingerprint failure, artifact-registration failure, and database failure after copy; assert no prepared stage or alias success state, and no final sandbox or that the residue is quarantined.
- [ ] Add a failing test for one `StageWorkspaceBindingModel` row keyed by `(run_id, stage_id, alias)` and a second binding attempt that violates the unique constraint. Add failing tests that assert a successful start creates distinct immutable `stage-preparation.json` and `stage-workspace-fingerprint.json` metadata records, ordered `STAGE_CREATED`, preparation-completed, and first-command-continuation events, and exactly the expected stage-step count.
- [ ] Add failing replay and competing-request tests asserting one sandbox, one stage, one set of steps, one alias binding, one preparation artifact pair, and one first-command continuation.
- [ ] Run the new tests and confirm they fail because preparation currently copies straight to its final path, persists a single report, and emits a single state transition.
- [ ] Extend `StageSandboxCopier` with a contained temporary sibling path and atomic rename/finalization operation. Validate source, target, registered root, output root, symlinks, and non-empty destinations before creating the temporary directory; remove the temporary directory on copying or fingerprint failure.
- [ ] Extend `StagePreparationApplicationService.prepare()` to return the finalized path, fingerprint, copied-file count, and cleanup/quarantine information without mutating workflow state.
- [ ] Add `StageWorkspaceBindingModel` and migration `20260728_32` with a unique active binding for `(run_id, stage_id, alias)`, contained resolved path, workspace fingerprint, and creation timestamp; use it as the authoritative stage-alias lookup instead of trusting a caller-supplied path.
- [ ] Make `StageExecutionApplicationService.start()` write distinct immutable preparation-report and workspace-fingerprint artifacts, persist stage/step/alias state, and emit the ordered preparation events only after finalization. On persistence failure, remove or quarantine the finalized sandbox and report the error without committing a success transition.
- [ ] Make idempotent replay return the original durable result and make concurrent duplicate starts converge on one prepared stage rather than copying twice.
- [ ] Run all stage-preparation, stage-execution, state-transition, and artifact-metadata regressions.

### Task 5: Carry project targets and stage-specific runtime profiles

**Files:**
- Modify: `backend/app/services/project_planning_resolver.py`
- Modify: `backend/app/domain/planning.py`
- Modify: `backend/app/services/planning_input_resolver.py`
- Modify: `backend/app/services/planning_application_service.py`
- Modify: `backend/app/services/compatibility_catalogue_provider.py`
- Modify: compatibility resolver/application contracts as required
- Test: `backend/tests/test_project_aware_planning.py`
- Test: relevant planning and compatibility tests

- [ ] Add failing tests proving selected project/target/script facts appear in the generated command arguments and proving later Angular stages do not reuse Node 20.11.1.
- [ ] Run them and confirm hardcoded scripts and shared runtime exact versions are still present.
- [ ] Extend immutable planning inputs with selected build/test/lint target identities, script names, package-manager configuration, and stage runtime profile binding.
- [ ] Generate commands from those facts and select stage-compatible runtime entries.
- [ ] Keep exact package pins only when backed by explicit catalogue metadata; otherwise expose a warning/blocker.
- [ ] Run project-planning, compatibility, and planning checksum regressions.

### Task 6: End-to-end dry run and independent review

**Files:**
- Modify: `backend/app/services/stage_execution_application_service.py`
- Test: `backend/tests/test_planning_transformation_dry_run.py`
- Test: `backend/tests/test_planning_transformation_boundary.py`

- [ ] Add a failing production-path dry-run test that creates a G05-approved plan through controlled proposer/reviewer gateway transports, accepts G06, starts the stage, and asserts the first generated command has one accepted `CommandAuthorizationAuditModel` and exactly one queued `CommandExecutionModel` without starting a process.
- [ ] In the same test, replay every generated command through the real seeded `CommandPolicyEngineService` and the production `CommandRegistry`/`CommandPolicy`, asserting each is accepted with the bound stage alias and approved runtime/network/timeout values.
- [ ] Run the test and confirm it fails because stage start does not currently create an authorization decision or queue a command.
- [ ] Add a first-command continuation helper in `StageExecutionApplicationService` that converts the first approved `CommandTemplateReference` into `CommandPolicyValidateRequestDto`, invokes the real policy engine, and hands its accepted decision to `CommandExecutorService.queue_authorized_command` with a deterministic idempotency key. Do not invoke worker process execution.
- [ ] Persist the authorization and queue events after preparation completion, reject policy failure without a successful stage transition, and return their identifiers in the stage-start projection.
- [ ] Run the dry run and verify the first command is reached only after approved G06 and prepared workspace binding.
- [ ] Run the complete relevant backend suite, frontend typecheck/build if dependencies permit, and `git diff --check`.
- [ ] Perform a read-only issue review against each audit gap and report any unproven external fixture/package claims separately.
