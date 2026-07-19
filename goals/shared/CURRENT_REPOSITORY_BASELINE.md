# Current Repository Baseline — Fresh V3 Audit

- Source archive: `angular-migration-dev (2).zip`
- Archive SHA-256: `992e6ee1e66ed774a680d5e8682052707bd5a307eab4ae9b6c959e6c36263dbc`
- Source files inventoried directly from ZIP: **478**
- Backend Python files: **258**
- Frontend TypeScript/TSX files: **114**
- Alembic Python files: **28**
- Transient bytecode/cache files are excluded and are not source anchors.

## Important existing reuse points

- `backend/app/command_execution/worker.py` — CommandPolicyViolation, CommandDefinition, StructuredCommandRequest, CommandExecutionResult, SupervisedProcessResult, CommandRegistry, CommandPolicy, CommandLogWriter, WorkerSupervisor, ExecutionWorker.
- `backend/app/domain/planning.py` — PlanArtifactInput, CommandTemplateReference, ValidationPolicy, RecoveryPolicy, RepairPolicy, ForbiddenChangePolicy, BuildSystemDecision, MigrationPlan, StageExecutionPlan, PlanGenerationRequest, PlanGenerationResult, _checksum, checksum_model, utc_now.
- `backend/app/repositories/models/workflow.py` — MigrationRunModel, MigrationStageModel, StageStepModel, AgentExecutionModel, WorkflowEventModel, ApprovalEventModel, ApprovalPolicyEventModel, ArtifactMetadataModel, CommandExecutionModel, WorkerLeaseModel, ActiveRunClaimModel, RepairAttemptModel, LlmUsageRecordModel, LlmInvocationModel, UsageCostRecordModel, RunAssuranceStatusModel, EnvironmentCapabilityModel, EnvironmentDiagnosticEventModel.
- `backend/app/state/preflight_transition_service.py` — PreflightTransitionService.
- `backend/app/state/transition_service.py` — TransitionError, StaleStateVersionError, LeaseRequiredError, ResumeRejectedError, TransitionRequest, TransitionResult, StateTransitionService.
- `backend/tests/test_state_transition_service.py` — _session, _create_run, _transition_request, test_accepted_transition_increments_state_and_writes_ordered_event, test_stale_expected_state_version_is_rejected_without_event, test_duplicate_idempotency_key_returns_existing_result, test_worker_lease_prevents_stale_step_completion, test_cancel_sequence_is_idempotent_and_preserves_history, test_resume_validates_checkpoint_workspace_and_policy_placeholders.

## Validation performed during package audit

- `python3 -m compileall -q backend/app backend/tests` passed against a fresh source extraction.
- A full pytest run was not claimed: the audit environment lacked project dependencies such as LangGraph, and one test import requires repository-root/PYTHONPATH execution.
- Canonical Linux test bootstrap must install backend development dependencies and run from repository root, for example `PYTHONPATH="$PWD:$PWD/backend" python3 -m pytest backend/tests`.
- Frontend package installation/build was not run in the package-builder environment; each Hermes goal must execute the live repository commands in its isolated runtime.

## Live-branch rule

This inventory is only a starting map. Every goal must re-audit the actual `goal`-based worktree and record exact current symbols before editing. Do not assume uploaded-archive status equals VM branch status.

## Known documentation drift

The uploaded README and some historical docs still describe early mock/Sprint-0 behavior. Goals update only documentation affected by their implemented capability; Sprint-2-owned implementation is not rewritten merely to reconcile historical prose.
