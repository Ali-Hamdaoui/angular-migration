# Planning-to-Transformation Boundary Investigation

## Scope

This note records the evidence gathered before implementation on branch
`hermes/01-command-runtime` at `4fb9f5e`.

## Baseline evidence

- The supplied inspection is `run-inspection/run-5c3f5a90561d-20260724-003645`.
- Its durable diagnosis says discovery blocked with `ANGULAR_JSON_MISSING` because
  the `SOURCE_SNAPSHOT` alias points at the snapshot parent while the persisted
  `snapshot_path` contains `package.json` and `angular.json`.
- That inspection has no `llm_invocations`, `migration_plans`,
  `stage_execution_plans`, `planning_reviews`, `g05_approvals`, `g06_approvals`,
  `migration_stages`, or `stage_steps` rows. Therefore it cannot confirm a
  later planning or transformation failure for that run.
- Focused backend baseline, with the correct Python 3.14 interpreter:
  `python -m pytest -q tests/test_planning_verification_s2_f06_i04.py
  tests/test_planning_review_verification_s2_f07_i04.py
  tests/test_planning_review_evidence_s2_f07_i02.py
  tests/test_planning_review_application_service_s2_f07_i01.py
  tests/test_planning_dispatch_recovery.py tests/test_planning_gate_integrity.py
  tests/test_command_registry_service.py tests/test_command_route_authorization.py
  tests/test_state_transition_service.py tests/test_path_validation_service.py
  tests/test_artifact_store.py` -> 86 passed, 2 skipped, 0 failed.
- Full backend collection currently fails before execution because
  `tests/test_analysis_reviewer_lifecycle_regression.py` imports
  `backend.tests...`, which is not importable from the configured test root.

## Confirmed causes

1. **Discovery root mismatch is the earliest confirmed broken boundary in the
   supplied run.** The snapshot service persists a concrete snapshot path, but
   the workspace alias used by downstream discovery is the parent directory.
   This makes deterministic discovery report missing Angular workspace files.
2. **The planning worker is capable of writing the six versioned S2-F07/G06
   artifacts, but only after the worker reaches `run_planning_review_step`.**
   The inspection never reached that step, so artifact absence there is a
   downstream consequence, not evidence of a defective artifact writer.
3. **Planning orchestration discards authoritative builder evidence.**
   `backend/app/orchestration/planning.py:108-112` sets
   `builder="@angular-devkit/build-angular:application"` and uses
   `gate.artifact_set_checksum` as `input_fingerprint`.
4. **G06 is coupled to physical stage creation.**
   `backend/app/services/planning_review_evidence_application_service.py:391`
   advances an approved G06 directly to `RunStatus.STAGE_CREATED` and
   `:404-410` completes the planning job.
5. **The current stage-start service is only a protected event transition.**
   `backend/app/services/stage_execution_application_service.py:17-69`
   validates checksums and emits `STAGE_CREATED`; it does not create
   `MigrationStageModel`/`StageStepModel`, copy a sandbox, fingerprint it, or
   produce a G07 package.
6. **Command references cannot yet be proven executable against production
   registry state.** `planning_application_service.py:70` emits the alias
   `stage_workspace`, while run layout exposes `STAGE_SANDBOX`; the registry
   migration also makes `command_id` globally unique, preventing immutable
   template versions from coexisting.

## Secondary defects confirmed by code inspection

- `PlanningInputResolver` returns runtime/profile and G04 evidence, but no typed
  project-aware planning input containing package scripts, target inventory,
  project configurations, lockfile metadata, or `.npmrc` install flags.
- `StageExecutionPlan` requires a universal build/test/lint command group, and
  `StageExecutionPlanService` generates generic `npm run build`, `npm run test
  -- --watch=false`, and `npm run lint` commands without discovered capability
  checks.
- `StageExecutionPlan` stores only `input_fingerprint`; the contract does not
  separately carry `evidence_set_checksum` and physical workspace fingerprint.
- Stage retrieval and authorization paths contain migration-wide latest-plan
  queries in addition to pointer lookups; multi-stage pointer regression is
  required before relying on retrieval.

## Unverified hypotheses

- Provider-specific proposer/reviewer failure diagnostics may still be
  incomplete for every gateway failure subtype; the current tests cover the
  existing service behavior but not the full requested matrix.
- The current catalogue runtime values for Angular 20/21 require fresh official
  compatibility verification; the repository fixture/catalogue was not treated
  as current truth during this local investigation.
- The durable transformation worker and G08/G09/G12 path may exist in another
  issue-owned slice, but no production worker equivalent to the requested
  stage-by-stage transformation pipeline was found in the current inventory.

## Implementation order

1. Make planning inputs evidence/project aware and separate checksum meanings.
2. Make G06 an atomic executable-plan approval that waits for stage preparation.
3. Add idempotent stage preparation and G07 evidence with exact aliases.
4. Bind every planned command to a versioned registry template and validate the
   generated plan against the real registry.
5. Add portable path containment and stage-pointer retrieval regressions.
6. Add the durable transformation worker only after the stage aggregate and G07
   boundary are authoritative.
