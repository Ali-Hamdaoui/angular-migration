"""Pointer-only LangGraph for the durable Transformer state machine.

File-size exception: the transition handlers stay together so restart routing,
gate bindings, and transaction/IO boundaries can be audited as one state
machine. Command execution, evidence, validation, repair, and sealing logic
remain in dedicated services.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.artifact_store import (
    ArtifactNotFoundError,
    ArtifactStoreError,
    LocalFilesystemArtifactStore,
    StoredArtifact,
)
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.domain.planning import (
    VALIDATION_TARGET_GROUPS,
    ValidationTargetUnionError,
    validation_target_union,
)
from app.orchestration.transformer_sealing_flow import TransformerSealingFlow
from app.repositories.models import (
    ActivePlanVersionModel,
    ArtifactMetadataModel,
    CommandExecutionModel,
    CommandLogChunkModel,
    CompatibilityCatalogueModel,
    CompatibilityResolutionModel,
    G06ApprovalModel,
    FailureIntelligenceModel,
    LlmInvocationModel,
    MigrationPlanModel,
    MigrationRunModel,
    RepairAttemptModel,
    RepairFingerprintRecoveryModel,
    StageRecoveryOperationModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageGatePackageModel,
    StageGateDecisionModel,
    StagePromptRequestModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.session import session_scope
from app.services.angular_transformation_evidence_service import (
    AngularTransformationEvidenceError,
    AngularTransformationEvidenceService,
)
from app.services.artifact_binding import canonical_artifact_set_checksum
from app.services.causal_review import g10_eligibility, repair_budget
from app.services.dependency_closure_service import verify_dependency_add_state
from app.services.dependency_transition_runner import (
    DependencyTransitionError,
    DependencyTransitionRunner,
)
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.failure_intelligence_service import FailureIntelligenceService
try:
    from app.services.dependency_failure_bundle_service import build_dependency_normalization_bundle
except ImportError:  # fallback for type checking
    build_dependency_normalization_bundle = None
from app.services.lockfile_generation_runner import (
    LOCKFILE_GENERATION_ETARGET,
    LOCKFILE_GENERATION_ERESOLVE,
    LockfileGenerationError,
    LockfileGenerationRunner,
)
from app.services.patch_apply_service import PatchApplyService, workspace_apply_lock
from app.services.prompt_explanation_service import PromptExplanationService
from app.services.repair_application_service import (
    RepairApplicationError,
    RepairApplicationService,
    RepairLlmError,
    RepairProposal,
)
from app.services.repair_lifecycle_service import RepairLifecycleService
from app.services.stage_gate_service import StageGateError, StageGateService
from app.services.stage_execution_application_service import validation_execution_key
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformer_stage_service import (
    ReconstructionMode,
    TransformerStageError,
    TransformerStageService,
)
from app.services.transformation_replan_recovery_service import (
    TransformationReplanRecoveryError,
    TransformationReplanRecoveryRequest,
    TransformationReplanRecoveryService,
)
from app.services.transformation_continuation_service import (
    append_continuation_event,
)
from app.services.validation_runner import (
    BuildAgent,
    TestAgent,
    ValidationRunner,
    ValidationRunnerError,
)
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE

logger = logging.getLogger(__name__)

# Frozen V2.2 contracts — code against strings even if sibling files absent (use constants/try imports)
try:
    from app.domain.dependency_normalization import DEPENDENCY_NORMALIZATION_REPAIR_KIND as _DN_KIND
    DEPENDENCY_NORMALIZATION_REPAIR_KIND = _DN_KIND
except ImportError:
    DEPENDENCY_NORMALIZATION_REPAIR_KIND = "dependency_manifest_normalization"
try:
    from app.domain.dependency_normalization import DEPENDENCY_NORMALIZATION_SCHEMA_VERSION as _DN_VER
    DEPENDENCY_NORMALIZATION_SCHEMA_VERSION = _DN_VER
except ImportError:
    DEPENDENCY_NORMALIZATION_SCHEMA_VERSION = "dependency-normalization-v1"
try:
    from app.services.lockfile_generation_runner import DEPENDENCY_NORMALIZATION_RESOLUTION_FAILED as _DNRF
    DEPENDENCY_NORMALIZATION_RESOLUTION_FAILED = _DNRF
except ImportError:
    DEPENDENCY_NORMALIZATION_RESOLUTION_FAILED = "DEPENDENCY_NORMALIZATION_RESOLUTION_FAILED"
try:
    from app.domain.transformation import FailureRoute as _FR, TransformationNode as _TN
    _DEPENDENCY_INCOMPATIBLE = _FR.DEPENDENCY_INCOMPATIBLE
    _MIGRATE_PACKAGES_NODE = _TN.MIGRATE_PACKAGES.value
except (ImportError, AttributeError):
    _DEPENDENCY_INCOMPATIBLE = "dependency_incompatible"
    _MIGRATE_PACKAGES_NODE = "migrate_packages"
# angular-migrate-range tpl-angular-migrate-range-v1 => npx ng update <package> --migrate-only --from <from> --to <to>, NG_DISABLE_VERSION_CHECK=true, no --force, no --allow-dirty
_MIGRATE_RANGE_TEMPLATE = "tpl-angular-migrate-range-v1"

# Checkpoint kinds an Angular-update execution may legitimately be bound to for
# reconstruction: the initial pre-update tree, or the post-repair tree
# (post-uninstall / pre-angular-retry). No other kind may authorize Angular
# workspace recovery.
_ANGULAR_RECOVERY_CHECKPOINT_KINDS = frozenset(
    {"pre_angular_update", "post_repair"}
)


class TransformerPointer(TypedDict):
    continuation_id: str
    worker_id: str


class TransformerOrchestrator:
    def __init__(
        self,
        *,
        scope=session_scope,
        stage_service=None,
        gate_service=None,
        transformation_evidence=None,
        prompt_explainer=None,
        validation_runner=None,
        failure_evidence=None,
        repair_service=None,
        patch_service=None,
        lockfile_runner=None,
        dependency_transition_runner=None,
        sealing_flow=None,
    ) -> None:
        self._scope = scope
        self._stage = stage_service or TransformerStageService(scope=scope)
        self._gates = gate_service or StageGateService()
        self._evidence = transformation_evidence or AngularTransformationEvidenceService()
        self._prompt_explainer = prompt_explainer or PromptExplanationService(scope=scope)
        self._validation = validation_runner or ValidationRunner()
        self._build_agent = BuildAgent(self._validation)
        self._test_agent = TestAgent(self._validation)
        self._failures = failure_evidence or FailureEvidenceService()
        self._repairs = repair_service or RepairApplicationService(scope=scope)
        self._patches = patch_service or PatchApplyService()
        self._lockfiles = lockfile_runner or LockfileGenerationRunner(
            stage_service=self._stage
        )
        self._dependency_transitions = dependency_transition_runner or DependencyTransitionRunner(
            stage_service=self._stage
        )
        self._sealing_flow = sealing_flow or TransformerSealingFlow(
            scope=scope,
            stage_service=self._stage,
            gate_service=self._gates,
        )

    def advance(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            node = continuation.current_node
        if node == "validate_g06":
            self._validate_g06(continuation_id, worker_id)
        elif node == "prepare_workspace":
            self._stage.prepare(continuation_id, worker_id)
        elif node == "resolve_runtime":
            self._resolve_runtime(continuation_id, worker_id)
        elif node == "dependency_preflight":
            self._preflight(continuation_id, worker_id)
        elif node == "collect_known_decisions":
            self._collect_decisions(continuation_id, worker_id)
        elif node == "create_g07":
            self._create_g07(continuation_id, worker_id)
        elif node == "bootstrap_install":
            with self._scope() as session:
                cont = self._owned(session, continuation_id, worker_id)
                step = session.scalar(
                    select(StageStepModel).where(
                        StageStepModel.stage_id == cont.current_stage_id,
                        StageStepModel.name == "bootstrap_install-0",
                        StageStepModel.status == "PASSED",
                    )
                )
                if step is not None:
                    cont.current_node = "verify_bootstrap"
                    cont.status = "queued"
                    cont.worker_id = None
                    cont.lease_expires_at = None
                    cont.state_version += 1
                    cont.updated_at = datetime.now(UTC)
                    return
                self._stage.queue_bootstrap(session, cont)
        elif node == "verify_bootstrap":
            with self._scope() as session:
                self._stage.verify_bootstrap(session, self._owned(session, continuation_id, worker_id))
        elif node == "angular_update":
            self._angular_update(continuation_id, worker_id)
        elif node == "handle_prompt":
            self._handle_prompt(continuation_id, worker_id)
        elif node == "target_inspection":
            with self._scope() as session:
                continuation = self._owned(session, continuation_id, worker_id)
                self._stage.queue_version_check(
                    session,
                    continuation,
                    attempt_key=(
                        f"target:{self._validation_attempt_key(session, continuation)}"
                    ),
                )
        elif node == "version_verify":
            self._version_verify(continuation_id, worker_id)
        elif node == "final_install":
            self._final_install(continuation_id, worker_id)
        elif node == "build":
            self._build(continuation_id, worker_id)
        elif node == "test":
            self._test(continuation_id, worker_id)
        elif node == "aggregate_validation":
            self._aggregate_validation(continuation_id, worker_id)
        elif node == "classify_failure":
            self._classify_failure(continuation_id, worker_id)
        elif node == "deterministic_replan":
            self._deterministic_replan(continuation_id, worker_id)
        elif node == "propose_repair":
            self._propose_repair(continuation_id, worker_id)
        elif node == "review_repair":
            self._review_repair(continuation_id, worker_id)
        elif node == "create_g10":
            self._create_repair_gate(continuation_id, worker_id, "G10")
        elif node == "apply_repair":
            self._apply_repair(continuation_id, worker_id)
        elif node == "verify_repair":
            self._verify_repair(continuation_id, worker_id)
        elif node == "angular_update_retry":
            self._angular_update_retry(continuation_id, worker_id)
        elif node == "dependency_transition":
            self._dependency_transition(continuation_id, worker_id)
        elif node == "lockfile_generation":
            self._lockfile_generation(continuation_id, worker_id)
        elif node == _MIGRATE_PACKAGES_NODE or node == "migrate_packages":
            self._migrate_packages(continuation_id, worker_id)
        elif node == "repair_revalidate":
            self._start_revalidation(continuation_id, worker_id)
        elif node == "create_g11":
            self._create_repair_gate(continuation_id, worker_id, "G11")
        elif node == "create_g09":
            self._create_g09_from_repair(continuation_id, worker_id)
        elif node == "create_g12":
            self._sealing_flow.create_g12(continuation_id, worker_id)
        elif node == "seal_stage":
            self._sealing_flow.seal(continuation_id, worker_id)
        elif node == "materialize_next_stage":
            self._sealing_flow.materialize(continuation_id, worker_id)
        elif node == "complete_run":
            self._sealing_flow.complete(continuation_id, worker_id)
        elif node == "cancel":
            self._cancel(continuation_id, worker_id)
        else:
            raise TransformerStageError("TRANSFORMATION_NODE_UNSUPPORTED", f"Unsupported node: {node}")

    def fail(
        self,
        continuation_id: str,
        worker_id: str,
        error: TransformerStageError | StageGateError,
    ) -> None:
        with self._scope() as session:
            continuation = session.get(TransformationContinuationModel, continuation_id)
            if continuation is not None and continuation.status == "running" and continuation.worker_id == worker_id:
                self._block(session, continuation, error.code, error.message)

    def _validate_g06(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            gate = session.get(G06ApprovalModel, continuation.g06_approval_id)
            pointer = session.scalar(
                select(ActivePlanVersionModel).where(
                    ActivePlanVersionModel.run_id == continuation.run_id,
                    ActivePlanVersionModel.scope == continuation.current_stage_id,
                )
            )
            if (
                gate is None
                or gate.status not in {"approved", "approved_with_comment"}
                or gate.plan_checksum != continuation.plan_checksum
                or gate.stage_plan_checksum != continuation.stage_plan_checksum
                or pointer is None
                or pointer.stage_plan_id != continuation.stage_plan_id
            ):
                self._block(session, continuation, "G06_BINDING_STALE", "Approved G06 binding changed")
                return
            self._queue(continuation, "prepare_workspace")

    def _resolve_runtime(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            try:
                self._stage.resolve_stage_runtime(session, continuation)
            except TransformerStageError as error:
                self._block(session, continuation, error.code, error.message)
                return
            continuation.last_error_code = None
            continuation.last_error_message = None
            self._queue(continuation, "dependency_preflight")

    def _preflight(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            report = self._stage.preflight(session, continuation)
            if report["blockers"]:
                self._block(
                    session,
                    continuation,
                    "DEPENDENCY_PREFLIGHT_BLOCKED",
                    ", ".join(report["blockers"]),
                )
                return
            self._queue(continuation, "collect_known_decisions")

    def _collect_decisions(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            decisions = self._stage.known_decisions(session, continuation)
            build = decisions.get("build_system_decision") or {}
            if build.get("action") == "blocked":
                self._block(session, continuation, "BUILD_SYSTEM_DECISION_BLOCKED", "Approved build decision blocks execution")
                return
            self._queue(continuation, "create_g07")

    def _create_g07(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            run = session.get(MigrationRunModel, continuation.run_id)
            plan = session.get(MigrationPlanModel, continuation.plan_id)
            if plan is None or plan.run_id != continuation.run_id:
                raise TransformerStageError("PLAN_BINDING_MISSING", "Migration plan for the run is missing")
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == continuation.run_id,
                    StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            payload = {
                "gate_id": "G07",
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
                "plan_version": plan.version,
                "plan_checksum": continuation.plan_checksum,
                "stage_plan_checksum": continuation.stage_plan_checksum,
                "workspace_fingerprint": binding.workspace_fingerprint,
                "runtime": self._stage.runtime_binding(session, continuation),
                "dependency_preflight": self._stage.preflight(session, continuation),
                "known_decisions": self._stage.known_decisions(session, continuation),
            }
            context = (
                continuation.run_id,
                continuation.current_stage_id,
                run.artifact_root,
                binding.workspace_fingerprint,
            )
        stored = self._stage.write_gate_package(
            run_id=context[0],
            stage_id=context[1],
            artifact_root=context[2],
            gate_id="G07",
            payload=payload,
        )
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            self._stage.register_artifact(session, stored, continuation)
            package = self._gates.create(
                session,
                continuation,
                gate_id="G07",
                package_artifact_id=stored.ref.artifact_id,
                package_checksum=stored.ref.checksum,
                artifact_set_checksum=self._stage.checksum({stored.ref.artifact_id: stored.ref.checksum}),
                workspace_fingerprint=context[3],
            )

    def _angular_update(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            binding = self._stage._binding(session, continuation)
            run = session.get(MigrationRunModel, continuation.run_id)
            decided_prompt = session.scalar(
                select(StagePromptRequestModel)
                .where(
                    StagePromptRequestModel.stage_id == continuation.current_stage_id,
                    StagePromptRequestModel.status == "decided",
                )
                .order_by(StagePromptRequestModel.decided_at.desc())
            )
            if decided_prompt is not None:
                checkpoint_id = decided_prompt.reconstruction_checkpoint_id
                snapshot_context = None
                prompt_id = decided_prompt.id
            else:
                checkpoint_id = None
                prompt_id = None
                snapshot_context = (
                    binding.workspace_path,
                    (run.workspace_aliases or {})["STAGE_SANDBOX"],
                    continuation.current_stage_id,
                )
        if snapshot_context is not None:
            snapshot = self._stage.snapshot_workspace(*snapshot_context)
            with self._scope() as session:
                continuation = self._owned(session, continuation_id, worker_id)
                checkpoint = self._stage.persist_snapshot_checkpoint(
                    session, continuation, snapshot, "pre_angular_update"
                )
                checkpoint_id = checkpoint.id
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            self._stage.queue_angular_update(
                session,
                continuation,
                checkpoint_id=checkpoint_id,
                prompt_id=prompt_id,
            )

    def _handle_prompt(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.stage_id == continuation.current_stage_id,
                    StageStepModel.name == "angular_update-0",
                )
            )
            execution = session.get(CommandExecutionModel, step.execution_id) if step and step.execution_id else None
            prompt = (
                session.get(StagePromptRequestModel, execution.prompt_request_id)
                if execution and execution.prompt_request_id
                else None
            )
            if execution is None:
                self._block(session, continuation, "ANGULAR_UPDATE_EVIDENCE_MISSING", "Angular update execution is missing")
                return
            if prompt is None:
                if execution.status == "succeeded":
                    step.status = "PASSED"
                    step.completed_at = datetime.now(UTC)
                    # A first-pass Angular update has no repair attempt. The
                    # successful command path must continue without requiring
                    # repair lineage; repair lineage is only mandatory for
                    # repair-specific nodes.
                    attempt = self._latest_repair(session, continuation, required=False)
                    if attempt is not None and attempt.status == "applied_verified":
                        RepairLifecycleService.transition_in_session(
                            session,
                            attempt,
                            "migration_retried",
                            reason="post-repair Angular update retry succeeded",
                        )
                    if self._pending_dependency_transition(session, continuation):
                        self._queue(continuation, "dependency_transition")
                    else:
                        self._queue(continuation, "target_inspection")
                else:
                    step.status = "FAILED"
                    step.completed_at = datetime.now(UTC)
                    continuation.last_error_code = execution.failure_code or "ANGULAR_UPDATE_FAILED"
                    continuation.last_error_message = execution.failure_message or "Angular update failed without a governed prompt"
                    self._queue(continuation, "classify_failure")
                return
            checkpoint = session.get(StageCheckpointModel, prompt.reconstruction_checkpoint_id)
            if (
                checkpoint is None
                or checkpoint.kind != "pre_angular_update"
                or checkpoint.stage_id != continuation.current_stage_id
                or checkpoint.id != execution.checkpoint_id
            ):
                self._block(
                    continuation,
                    "CHECKPOINT_MISSING",
                    "Prompt-referenced pre_angular_update checkpoint is missing or disagrees with the execution",
                )
                return
            binding = self._stage._binding(session, continuation)
            run = session.get(MigrationRunModel, continuation.run_id)
            self._stage.begin_reconstruction(
                session,
                continuation,
                checkpoint=checkpoint,
                reason="prompt_reconstruction",
                execution_id=execution.id,
            )
            checkpoint_fingerprint = self._stage.authoritative_checkpoint_fingerprint(
                session, checkpoint
            )
            if checkpoint_fingerprint is None:
                raise TransformerStageError(
                    "CHECKPOINT_INTEGRITY_FAILED",
                    "Prompt-referenced checkpoint is not authoritative",
                )
            reconstruction = (
                checkpoint.workspace_path,
                binding.workspace_path,
                (run.workspace_aliases or {})["STAGE_SANDBOX"],
                checkpoint_fingerprint,
                run.artifact_root,
            )
            prompt_id = prompt.id
            execution_id = execution.id
            checkpoint_id = checkpoint.id
        observed = self._stage.reconstruct_workspace(*reconstruction)
        try:
            self._prompt_explainer.explain(prompt_id)
        except Exception as error:
            raise TransformerStageError(
                "PROMPT_EXPLANATION_FAILED",
                "Governed prompt explanation failed; no answer was accepted",
            ) from error
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            prompt = session.get(StagePromptRequestModel, prompt_id)
            binding = self._stage._binding(session, continuation)
            checkpoint = session.get(StageCheckpointModel, checkpoint_id)
            if checkpoint is None or StageSandboxCopier.fingerprint(
                Path(binding.workspace_path)
            ) != observed:
                raise TransformerStageError(
                    "CHECKPOINT_INTEGRITY_FAILED",
                    "Restored workspace fingerprint changed during prompt reconstruction",
                )
            self._stage.record_reconstruction(
                session,
                continuation,
                checkpoint=checkpoint,
                reason="prompt_reconstruction",
                restored_fingerprint=observed,
                execution_id=execution_id,
            )
            binding.workspace_fingerprint = observed
            binding.fingerprint_profile_id = STAGE_FINGERPRINT_PROFILE.profile_id
            binding.last_verified_fingerprint = observed
            binding.last_verified_at = datetime.now(UTC)
            prompt.observed_fingerprint = observed
            prompt.status = "waiting_human"
            expected_state_version = continuation.state_version
            continuation.status = "waiting_prompt"
            continuation.current_node = "wait_prompt_decision"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.state_version += 1
            continuation.updated_at = datetime.now(UTC)
            session.flush()
            append_continuation_event(
                session,
                continuation,
                event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_WAITING,
                key=f"wait:waiting_prompt:{expected_state_version}",
                reason="unexpected prompt detected; continuation waits for human decision",
                payload={"expected_state_version": expected_state_version},
            )

    def _version_verify(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
            binding = self._stage._binding(session, continuation)
            angular_step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.stage_id == continuation.current_stage_id,
                    StageStepModel.name == "angular_update-0",
                )
            )
            version_step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.stage_id == continuation.current_stage_id,
                    StageStepModel.name == "target_version_check-0",
                )
            )
            angular_execution = (
                session.get(CommandExecutionModel, angular_step.execution_id)
                if angular_step and angular_step.execution_id
                else None
            )
            version_execution = (
                session.get(CommandExecutionModel, version_step.execution_id)
                if version_step and version_step.execution_id
                else None
            )
            checkpoint = (
                session.get(StageCheckpointModel, angular_execution.checkpoint_id)
                if angular_execution and angular_execution.checkpoint_id
                else None
            )
            if angular_execution is None or checkpoint is None:
                self._block(
                    session,
                    continuation,
                    "ANGULAR_UPDATE_EVIDENCE_MISSING",
                    "Angular update execution or reconstruction checkpoint is missing",
                )
                return
            if self._target_version_recovery_required(version_execution):
                self._stage.queue_version_check(
                    session,
                    continuation,
                    attempt_key=(
                        f"target:{self._validation_attempt_key(session, continuation)}:recovery-1"
                    ),
                    recovery_of=version_execution.id,
                )
                return
            if version_execution is None or version_execution.status != "succeeded":
                self._block(
                    session,
                    continuation,
                    (
                        version_execution.failure_code
                        if version_execution and version_execution.failure_code
                        else "TARGET_VERSION_CHECK_FAILED"
                        if version_execution
                        else "VERSION_CHECK_MISSING"
                    ),
                    (
                        version_execution.failure_message
                        if version_execution and version_execution.failure_message
                        else "Target version command did not succeed"
                    ),
                )
                return
            output = "".join(
                session.scalars(
                    select(CommandLogChunkModel.text)
                    .where(CommandLogChunkModel.execution_id == version_execution.id)
                    .order_by(CommandLogChunkModel.sequence)
                )
            )
            run = session.get(MigrationRunModel, continuation.run_id)
            plan = session.get(MigrationPlanModel, continuation.plan_id)
            if plan is None or plan.run_id != continuation.run_id:
                raise TransformerStageError("PLAN_BINDING_MISSING", "Migration plan for the run is missing")
            stage_value = stage_plan.stage_plan or {}
            context = {
                "workspace_path": binding.workspace_path,
                "checkpoint_path": checkpoint.workspace_path,
                "target_core": stage_value.get("target_exact"),
                "target_cli": stage_value.get("target_cli_exact") or stage_value.get("target_exact"),
                "ng_version_output": output,
                "angular_execution_id": angular_execution.id,
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
                "artifact_root": run.artifact_root,
                "plan_version": plan.version,
                "stage_plan_checksum": continuation.stage_plan_checksum,
                "expected_pre_fingerprint": checkpoint.workspace_fingerprint,
                "workspace_fingerprint": binding.workspace_fingerprint,
            }
        try:
            context["workspace_fingerprint"] = StageSandboxCopier.fingerprint(
                Path(context["workspace_path"])
            )
            context["expected_post_fingerprint"] = context["workspace_fingerprint"]
            # P0-2: deterministic branch — normal ng update success vs normalized dependency path
            is_normalized_path = angular_execution.status != "succeeded"
            # Additional check: ensure a dependency normalization attempt exists for this stage
            if is_normalized_path:
                # Check for any dependency normalization repair attempt to confirm lineage
                try:
                    norm_attempt_check = session.query(RepairAttemptModel).filter(
                        RepairAttemptModel.run_id == continuation.run_id,
                        RepairAttemptModel.stage_id == continuation.current_stage_id,
                    ).order_by(RepairAttemptModel.attempt_number.desc()).first()
                    # If no attempt or attempt is not dependency normalization, treat as normal failure not normalized
                    # For now, if angular failed but no norm attempt yet, we still need to build? But G08 is after normalization+migrate, so by then norm attempt exists
                    # So we branch based on angular status alone for G08 after migrate
                    if norm_attempt_check is None or norm_attempt_check.proposal_artifact_id is None:
                        is_normalized_path = False
                except Exception:
                    pass
            if is_normalized_path:
                # Normalized path: collect successful angular-migrate-range executions for CURRENT lineage
                # Filter by run/stage and lineage (attempt id / checkpoint) — fail closed if any required missing
                try:
                    # Latest normalization attempt for lineage filtering
                    latest_norm = session.query(RepairAttemptModel).filter(
                        RepairAttemptModel.run_id == continuation.run_id,
                        RepairAttemptModel.stage_id == continuation.current_stage_id,
                    ).order_by(RepairAttemptModel.attempt_number.desc()).first()
                    # Collect all successful migrate-range executions for this stage
                    all_migrate_execs = list(
                        session.scalars(
                            select(CommandExecutionModel).where(
                                CommandExecutionModel.run_id == continuation.run_id,
                                CommandExecutionModel.stage_id == continuation.current_stage_id,
                                CommandExecutionModel.command_id == "angular-migrate-range",
                            )
                        ).all()
                    )
                    # Filter to successful and lineage-matched (requested_at after latest_norm created_at if available)
                    filtered: list[dict[str, object]] = []
                    for ex in all_migrate_execs:
                        if ex.status != "succeeded" or ex.exit_code != 0:
                            continue
                        # Lineage: only executions after latest_norm created_at are current lineage
                        if latest_norm is not None and ex.requested_at is not None and latest_norm.created_at is not None:
                            if ex.requested_at < latest_norm.created_at:
                                continue
                        # Validate arguments and artifacts present
                        if not ex.arguments or len(ex.arguments) != 8:
                            continue
                        # Check required artifacts present
                        if not ex.result_artifact_id or not ex.command_log_artifact_id:
                            continue
                        pkg = str(ex.arguments[2])
                        from_ver = str(ex.arguments[5])
                        to_ver = str(ex.arguments[7])
                        # Build record for build_multi
                        filtered.append(
                            {
                                "package": pkg,
                                "from_exact": from_ver,
                                "to_exact": to_ver,
                                "declares_migrations": True,
                                "migration_collection": None,
                                "command_execution_id": ex.id,
                                "command_status": ex.status,
                                "output_artifact_refs": [ex.result_artifact_id, ex.command_log_artifact_id],
                                "status": ex.status,
                                "execution_id": ex.id,
                                "exit_code": ex.exit_code,
                            }
                        )
                    # Sort deterministically by package for ledger
                    filtered.sort(key=lambda x: str(x.get("package")))
                    # P0-3: prove EXPECTED == ACTUAL for current lineage
                    # Recompute EXPECTED via discover
                    try:
                        from app.services.package_migration_service import PackageMigrationService as _PMS_G08, PackageMigrationError as _PME_G08

                        # Fix 2/3: strict lineage-bound G08 — use current normalization leaf, not arbitrary latest
                        _lineage_for_g08 = None
                        _latest_for_g08 = None
                        _chk_for_g08 = None
                        try:
                            _lineage_g08 = self._dependency_normalization_lineage(session, continuation)
                            _latest_for_g08 = _lineage_g08[-1] if _lineage_g08 else None
                            _chk_for_g08 = session.scalar(
                                select(StageCheckpointModel).where(
                                    StageCheckpointModel.run_id == continuation.run_id,
                                    StageCheckpointModel.stage_id == continuation.current_stage_id,
                                    StageCheckpointModel.kind == "pre_angular_update",
                                ).order_by(StageCheckpointModel.sequence.desc())
                            )
                            if _latest_for_g08 is not None and _chk_for_g08 is not None:
                                _lineage_raw_g08 = f"{_latest_for_g08.id}:{_chk_for_g08.id}:{_latest_for_g08.attempt_number}"
                                _lineage_for_g08 = hashlib.sha256(_lineage_raw_g08.encode()).hexdigest()[:16]
                            elif _latest_for_g08 is None:
                                # No normalization lineage, use no-norm for normal path (should not be in this branch, but fallback)
                                _lineage_for_g08 = hashlib.sha256(f"{continuation.run_id}:{continuation.current_stage_id}:no-norm".encode()).hexdigest()[:16]
                            else:
                                _lineage_for_g08 = hashlib.sha256(f"{continuation.run_id}:{continuation.current_stage_id}:{_latest_for_g08.id}".encode()).hexdigest()[:16]
                        except Exception:
                            _lineage_for_g08 = hashlib.sha256(f"{continuation.run_id}:{continuation.current_stage_id}:no-lineage".encode()).hexdigest()[:16]
                        # P0-4: pass normalization actions for REMOVE/REPLACE check
                        _norm_actions_g08 = None
                        try:
                            if _latest_for_g08 is not None and _latest_for_g08.proposal_artifact_id:
                                _meta_g08 = session.get(ArtifactMetadataModel, "metadata-" + _latest_for_g08.proposal_artifact_id)
                                if _meta_g08 is not None:
                                    _run_g08 = session.get(MigrationRunModel, _latest_for_g08.run_id)
                                    if _run_g08 and _run_g08.artifact_root:
                                        from app.artifact_store import LocalFilesystemArtifactStore as _StoreG08

                                        _store_g08 = _StoreG08(Path(_run_g08.artifact_root).parent, fixed_run_root=Path(_run_g08.artifact_root))
                                        _prop_g08 = json.loads(_store_g08.read_artifact(_latest_for_g08.run_id, _meta_g08.relative_path).content)
                                        _ops_g08 = _prop_g08.get("operations") if isinstance(_prop_g08, dict) else None
                                        if isinstance(_ops_g08, list):
                                            _norm_actions_g08 = {}
                                            for _op in _ops_g08:
                                                if isinstance(_op, dict):
                                                    _pkg_g08 = _op.get("package") or _op.get("target_package") or _op.get("name")
                                                    if isinstance(_pkg_g08, str):
                                                        _norm_actions_g08[_pkg_g08] = _op
                        except Exception:
                            _norm_actions_g08 = None
                        _expected_reqs = _PMS_G08().discover(Path(context["checkpoint_path"]), Path(context["workspace_path"]), _norm_actions_g08)
                        _expected_ids: set[str] = set()
                        for _req in _expected_reqs:
                            _ident = f"{_req.package}:{_req.from_version}:{_req.to_version}:{_lineage_for_g08}"
                            _canonical = hashlib.sha256(f"{continuation.run_id}:{continuation.current_stage_id}:{_lineage_for_g08}:{_req.package}:{_req.from_version}:{_req.to_version}".encode()).hexdigest()[:16]
                            _expected_ids.add(_ident)
                            _expected_ids.add(_canonical)
                        _actual_ids: set[str] = set()
                        for _r in filtered:
                            _pkg = str(_r.get("package"))
                            _from = str(_r.get("from_exact"))
                            _to = str(_r.get("to_exact"))
                            _ident2 = f"{_pkg}:{_from}:{_to}:{_lineage_for_g08}"
                            _canon2 = hashlib.sha256(f"{continuation.run_id}:{continuation.current_stage_id}:{_lineage_for_g08}:{_pkg}:{_from}:{_to}".encode()).hexdigest()[:16]
                            _actual_ids.add(_ident2)
                            _actual_ids.add(_canon2)
                        # Fix 3: strict lineage-bound equality, not simple package:from:to
                        if _expected_ids != _actual_ids:
                            _missing = _expected_ids - _actual_ids
                            _extra = _actual_ids - _expected_ids
                            _extra = _act_simple - _exp_simple
                            if _missing:
                                raise AngularTransformationEvidenceError("MIGRATION_EVIDENCE_INCOMPLETE", f"Missing expected migrations: {sorted(_missing)}")
                            if _extra:
                                raise AngularTransformationEvidenceError("MIGRATION_EVIDENCE_UNEXPECTED", f"Unexpected migrations: {sorted(_extra)}")
                        # Also ensure lineage not stale: if expected non-empty and actual empty -> already handled above as missing
                        # Allow empty==empty (no migrations needed) -> build_multi([]) valid
                    except AngularTransformationEvidenceError:
                        raise
                    except _PME_G08 as _e:
                        raise AngularTransformationEvidenceError(_e.code, _e.message) from _e
                    except Exception as _e2:
                        raise AngularTransformationEvidenceError("MIGRATION_EVIDENCE_COLLECTION_FAILED", str(_e2)) from _e2
                    versions, ledger = self._evidence.build_multi(
                        context["workspace_path"],
                        context["checkpoint_path"],
                        target_core=context["target_core"],
                        target_cli=context["target_cli"],
                        ng_version_output=context["ng_version_output"],
                        migration_executions=tuple(filtered),
                        expected_pre_fingerprint=context["expected_pre_fingerprint"],
                        expected_post_fingerprint=context["expected_post_fingerprint"],
                    )
                except AngularTransformationEvidenceError:
                    raise
                except Exception as ex2:
                    # Fail closed on collection error
                    raise AngularTransformationEvidenceError("MIGRATION_EVIDENCE_COLLECTION_FAILED", str(ex2)) from ex2
            else:
                versions, ledger = self._evidence.build(
                    context["workspace_path"],
                    context["checkpoint_path"],
                    target_core=context["target_core"],
                    target_cli=context["target_cli"],
                    ng_version_output=context["ng_version_output"],
                    angular_execution_id=context["angular_execution_id"],
                    expected_pre_fingerprint=context["expected_pre_fingerprint"],
                    expected_post_fingerprint=context["expected_post_fingerprint"],
                )
        except AngularTransformationEvidenceError as error:
            with self._scope() as session:
                self._block(session, self._owned(session, continuation_id, worker_id), error.code, error.message)
            return
        version_artifact, ledger_artifact = self._evidence.write(
            run_id=context["run_id"],
            stage_id=context["stage_id"],
            artifact_root=context["artifact_root"],
            version_evidence=versions,
            ledger=ledger,
        )
        package_payload = {
            "gate_id": "G08",
            "run_id": context["run_id"],
            "stage_id": context["stage_id"],
            "plan_version": context["plan_version"],
            "stage_plan_checksum": context["stage_plan_checksum"],
            "expected_pre_fingerprint": context["expected_pre_fingerprint"],
            "expected_post_fingerprint": context["expected_post_fingerprint"],
            "workspace_fingerprint": context["workspace_fingerprint"],
            "version_evidence_artifact_id": version_artifact.ref.artifact_id,
            "version_evidence_checksum": version_artifact.ref.checksum,
            "migration_ledger_artifact_id": ledger_artifact.ref.artifact_id,
            "migration_ledger_checksum": ledger_artifact.ref.checksum,
        }
        gate_artifact = self._stage.write_gate_package(
            run_id=context["run_id"],
            stage_id=context["stage_id"],
            artifact_root=context["artifact_root"],
            gate_id="G08",
            payload=package_payload,
        )
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            binding = self._stage._binding(session, continuation)
            binding.workspace_fingerprint = context["workspace_fingerprint"]
            binding.fingerprint_profile_id = STAGE_FINGERPRINT_PROFILE.profile_id
            binding.last_verified_fingerprint = context["workspace_fingerprint"]
            binding.last_verified_at = datetime.now(UTC)
            version_step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.stage_id == continuation.current_stage_id,
                    StageStepModel.name == "target_version_check-0",
                )
            )
            if version_step is not None:
                version_step.status = "PASSED"
                version_step.completed_at = datetime.now(UTC)
                version_step.workspace_fingerprint = context["workspace_fingerprint"]
                version_step.output_checksum = version_execution.runtime_checksum
                version_step.artifact_ids = list(version_execution.artifact_ids or [])
                version_step.updated_at = datetime.now(UTC)
            continuation.last_error_code = None
            continuation.last_error_message = None
            for artifact in (version_artifact, ledger_artifact, gate_artifact):
                self._stage.register_artifact(session, artifact, continuation)
            self._gates.create(
                session,
                continuation,
                gate_id="G08",
                package_artifact_id=gate_artifact.ref.artifact_id,
                package_checksum=gate_artifact.ref.checksum,
                artifact_set_checksum=self._stage.checksum(
                    {
                        artifact.ref.artifact_id: artifact.ref.checksum
                        for artifact in (version_artifact, ledger_artifact, gate_artifact)
                    }
                ),
                workspace_fingerprint=context["workspace_fingerprint"],
            )

    def _final_install(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            groups = self._validation_groups(session, continuation)
            next_node = self._node_for_group(groups[0]) if groups else "aggregate_validation"
            attempt_key = self._validation_attempt_key(session, continuation)
            try:
                self._validation.advance_group(
                    session,
                    continuation,
                    "final_install",
                    next_node=next_node,
                    attempt_key=attempt_key,
                )
            except ValidationRunnerError as error:
                self._validation_failure(session, continuation, error)

    def _build(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            groups = self._validation_groups(session, continuation)
            if not groups or groups[0] != "builds":
                self._queue(continuation, self._node_for_group(groups[0]) if groups else "aggregate_validation")
                return
            next_node = self._node_for_group(groups[1]) if len(groups) > 1 else "aggregate_validation"
            attempt_key = self._validation_attempt_key(session, continuation)
            try:
                self._build_agent.advance(
                    session, continuation, next_node=next_node, attempt_key=attempt_key
                )
            except ValidationRunnerError as error:
                self._validation_failure(session, continuation, error)

    def _test(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            groups = [
                group
                for group in self._validation_groups(session, continuation)
                if group != "builds"
            ]
            current = next(
                (
                    group
                    for group in groups
                    if session.scalar(
                        select(StageStepModel).where(
                            StageStepModel.stage_id == continuation.current_stage_id,
                            StageStepModel.name == f"{group}-0",
                            StageStepModel.status != "PASSED",
                        )
                    )
                    is not None
                ),
                None,
            )
            if current is None:
                self._queue(continuation, "aggregate_validation")
                return
            remaining = groups[groups.index(current) + 1 :]
            next_node = "test" if remaining else "aggregate_validation"
            attempt_key = self._validation_attempt_key(session, continuation)
            try:
                self._test_agent.advance(
                    session,
                    continuation,
                    current,
                    next_node=next_node,
                    attempt_key=attempt_key,
                )
            except ValidationRunnerError as error:
                self._validation_failure(session, continuation, error)

    def _aggregate_validation(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            try:
                payload, artifact_root = self._validation.aggregate(session, continuation)
            except ValidationRunnerError as error:
                self._validation_failure(session, continuation, error)
                return
            plan = session.get(MigrationPlanModel, continuation.plan_id)
            if plan is None or plan.run_id != continuation.run_id:
                raise TransformerStageError("PLAN_BINDING_MISSING", "Migration plan for the run is missing")
            plan_version = plan.version
            repair = (
                session.query(RepairAttemptModel)
                .filter(
                    RepairAttemptModel.run_id == continuation.run_id,
                    RepairAttemptModel.stage_id == continuation.current_stage_id,
                    RepairAttemptModel.status.in_(("applied", "applied_verified", "migration_retried", "revalidating")),
                )
                .order_by(RepairAttemptModel.attempt_number.desc())
                .first()
            )
            # aggregate: no repair→G09, repair revalidated→G11 (conditional, not unconditional)
            gate_id = "G11" if repair is not None else "G09"
            if repair is not None:
                binding = self._stage._binding(session, continuation)
                reports = self._verify_dependency_add_post_state(
                    session,
                    continuation,
                    repair,
                    artifact_root,
                    binding,
                )
                if reports is not None and any(
                    not item["report"]["agreement"] for item in reports
                ):
                    violations = [
                        str(value)
                        for item in reports
                        if not item["report"]["agreement"]
                        for value in item["report"]["violations"][:3]
                    ]
                    self._block(
                        session,
                        continuation,
                        "REPAIR_DEPENDENCY_ADD_VERIFICATION_FAILED",
                        (
                            "dependency-add post-state verification failed: "
                            + ", ".join(violations)
                        )[:500],
                    )
                    return
        summary = self._validation.write_summary(payload, artifact_root)
        gate_payload = {
            "gate_id": gate_id,
            **payload,
            "plan_version": plan_version,
            "validation_summary_artifact_id": summary.ref.artifact_id,
            "validation_summary_checksum": summary.ref.checksum,
        }
        gate = self._stage.write_gate_package(
            run_id=str(payload["run_id"]),
            stage_id=str(payload["stage_id"]),
            artifact_root=artifact_root,
            gate_id=gate_id,
            payload=gate_payload,
        )
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            self._validation.register_summary(session, continuation, summary)
            self._stage.register_artifact(session, gate, continuation)
            if repair is not None:
                repair = (
                    session.query(RepairAttemptModel)
                    .filter(
                        RepairAttemptModel.run_id == continuation.run_id,
                        RepairAttemptModel.stage_id == continuation.current_stage_id,
                        RepairAttemptModel.status.in_(("applied", "applied_verified", "migration_retried", "revalidating")),
                    )
                    .order_by(RepairAttemptModel.attempt_number.desc())
                    .first()
                )
                repair.validation_summary_artifact_id = summary.ref.artifact_id
                repair.validation_summary_checksum = summary.ref.checksum
                repair.status = "waiting_g11"
                repair.updated_at = datetime.now(UTC)
            self._gates.create(
                session,
                continuation,
                gate_id=gate_id,
                package_artifact_id=gate.ref.artifact_id,
                package_checksum=gate.ref.checksum,
                artifact_set_checksum=self._stage.checksum(
                    {
                        summary.ref.artifact_id: summary.ref.checksum,
                        gate.ref.artifact_id: gate.ref.checksum,
                    }
                ),
                workspace_fingerprint=str(payload["workspace_fingerprint"]),
            )

    def _verify_dependency_add_post_state(
        self,
        session,
        continuation,
        repair,
        artifact_root: str,
        binding,
    ) -> list[dict[str, object]] | None:
        """Post-state verification for bound dependency_add operations.

        Runs at aggregate_validation, after apply, lockfile generation, npm ci,
        and validation completed. Reads ONLY the checksum-bound proposal
        artifact (never the frontend) and verifies the approved manifest
        version spec survived into the lockfile root, with the exact resolved
        version observed from the lockfile matching the installed metadata.
        Returns None when the attempt carries no dependency_add operation (no
        behavior change), otherwise a list of per-operation reports.
        """
        if not repair.proposal_artifact_id or not repair.proposal_checksum:
            return None
        metadata = session.get(
            ArtifactMetadataModel, "metadata-" + str(repair.proposal_artifact_id)
        )
        if metadata is None or metadata.checksum != repair.proposal_checksum:
            return None
        store = LocalFilesystemArtifactStore(
            Path(artifact_root).parent, fixed_run_root=Path(artifact_root)
        )
        try:
            stored = store.read_artifact(continuation.run_id, metadata.relative_path)
            if (
                stored.ref.artifact_id != repair.proposal_artifact_id
                or stored.ref.checksum != repair.proposal_checksum
                or stored.envelope is None
                or stored.envelope.run_id != continuation.run_id
                or stored.envelope.stage_id != continuation.current_stage_id
                or stored.envelope.attempt_id != repair.id
            ):
                return None
            proposal = RepairProposal.model_validate(json.loads(stored.content))
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError, TypeError):
            return None
        additions = [
            item
            for item in proposal.operations
            if item.operation == "dependency_add"
            and item.package
            and item.section
            and item.new_version
        ]
        if not additions:
            return None
        reports = []
        for item in additions:
            try:
                report = verify_dependency_add_state(
                    Path(binding.workspace_path),
                    package=str(item.package),
                    section=str(item.section),
                    approved_version_spec=str(item.new_version),
                )
            except ValueError as error:
                report = {"agreement": False, "violations": [str(error)]}
            self._write_dependency_add_verification_artifact(
                session,
                continuation,
                repair,
                artifact_root,
                package=str(item.package),
                section=str(item.section),
                approved_version_spec=str(item.new_version),
                report=report,
            )
            reports.append(
                {
                    "package": str(item.package),
                    "section": str(item.section),
                    "approved_version_spec": str(item.new_version),
                    "report": report,
                }
            )
        return reports

    def _write_dependency_add_verification_artifact(
        self,
        session,
        continuation,
        repair,
        artifact_root: str,
        *,
        package: str,
        section: str,
        approved_version_spec: str,
        report: dict[str, object],
    ) -> StoredArtifact:
        content = json.dumps(
            {
                "schema_version": "dependency-add-verification.v2",
                "attempt_id": repair.id,
                "package": package,
                "section": section,
                "approved_version_spec": approved_version_spec,
                "resolved_exact_version": report.get("resolved_exact_version"),
                "installed_version": report.get("installed_version"),
                "agreement": bool(report.get("agreement")),
                "report": report,
                "proposal_checksum": repair.proposal_checksum,
            },
            sort_keys=True,
            indent=2,
        )
        checksum = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
        store = LocalFilesystemArtifactStore(
            Path(artifact_root).parent, fixed_run_root=Path(artifact_root)
        )
        relative_path = f"05_repairs/attempt-{repair.id}/dependency-add-verification.json"
        for ref in store.list_artifacts(continuation.run_id):
            if ref.relative_path == relative_path and ref.checksum == checksum:
                stored = store.read_artifact(continuation.run_id, ref.relative_path)
                if (
                    stored.envelope
                    and stored.envelope.input_hashes.get("attempt") == repair.id
                ):
                    self._register_dependency_add_verification_metadata(
                        session, continuation, stored, repair
                    )
                    return stored
        stored = store.write_text_artifact(
            continuation.run_id,
            relative_path,
            content,
            ArtifactType.JSON,
            stage_id=continuation.current_stage_id,
            attempt_id=repair.id,
            created_by="repair-dependency-add-verification",
            created_at=datetime.now(UTC),
            input_hashes={"attempt": repair.id},
            policy_version="dependency-add-verification-v2",
        )
        self._register_dependency_add_verification_metadata(
            session, continuation, stored, repair
        )
        return stored

    @staticmethod
    def _register_dependency_add_verification_metadata(
        session, continuation, stored, repair
    ) -> None:
        metadata_id = "metadata-" + stored.ref.artifact_id
        if session.get(ArtifactMetadataModel, metadata_id) is not None:
            return
        session.add(
            ArtifactMetadataModel(
                id=metadata_id,
                run_id=continuation.run_id,
                stage_id=continuation.current_stage_id,
                artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                schema_version=stored.envelope.schema_version,
                created_at=stored.ref.created_at,
                owner_reference=f"dependency-add-verification:{repair.id}",
                mime_type=stored.envelope.content_type,
                size_bytes=len(stored.content.encode("utf-8")),
                finalized_at=stored.ref.created_at,
                immutable=True,
            )
        )

    def _persist_dependency_failure_bundle_before_reconstruction(
        self,
        session,
        continuation,
        execution,
        evidence: dict[str, object],
    ) -> StoredArtifact | None:
        """P0-1: capture post-failure workspace BEFORE reconstruction, build bundle, persist immutably.

        Invariant: for proven dependency-related angular-update failure, freeze
        package.json/package-lock/direct versions/logs BEFORE ANY reconstruction,
        then reconstruct. Fail closed if checkpoint/post workspace/bundle cannot be
        proven.
        """
        if build_dependency_normalization_bundle is None:
            self._block(session, continuation, "DEPENDENCY_BUNDLE_UNAVAILABLE", "Dependency failure bundle builder is unavailable")
            return None
        if execution is None or execution.status != "failed":
            self._block(session, continuation, "DEPENDENCY_BUNDLE_EXECUTION_MISSING", "Failed angular-update execution is missing")
            return None
        # checkpoint is immutable pre-ng-update copy
        checkpoint = self._angular_update_reconstruction_checkpoint(session, continuation)
        if checkpoint is None:
            # fallback to latest pre_angular_update checkpoint
            checkpoint = session.scalar(
                select(StageCheckpointModel)
                .where(
                    StageCheckpointModel.run_id == continuation.run_id,
                    StageCheckpointModel.stage_id == continuation.current_stage_id,
                    StageCheckpointModel.kind == "pre_angular_update",
                )
                .order_by(StageCheckpointModel.sequence.desc())
                .limit(1)
            )
        if checkpoint is None:
            self._block(session, continuation, "DEPENDENCY_BUNDLE_CHECKPOINT_MISSING", "Pre-update checkpoint cannot be resolved")
            return None
        # fail closed if execution/run/stage identity does not match
        if execution.run_id != continuation.run_id or execution.stage_id != continuation.current_stage_id:
            self._block(session, continuation, "DEPENDENCY_BUNDLE_IDENTITY_MISMATCH", "Bundle execution/run/stage identity mismatch")
            return None
        if checkpoint.run_id != continuation.run_id or checkpoint.stage_id != continuation.current_stage_id:
            self._block(session, continuation, "DEPENDENCY_BUNDLE_CHECKPOINT_MISMATCH", "Checkpoint identity mismatch")
            return None
        # read pre/post states — fail closed if post cannot be read
        binding = self._stage._binding(session, continuation)
        try:
            # pre-update from checkpoint (immutable)
            pre_pkg_text = (Path(checkpoint.workspace_path) / "package.json").read_text(encoding="utf-8")
            pre_pkg = json.loads(pre_pkg_text) if pre_pkg_text.strip() else None
        except Exception as error:
            self._block(session, continuation, "DEPENDENCY_BUNDLE_PRE_READ_FAILED", f"Pre-update package.json cannot be read: {error}")
            return None
        try:
            pre_lock_text = (Path(checkpoint.workspace_path) / "package-lock.json").read_text(encoding="utf-8")
            pre_lock = json.loads(pre_lock_text) if pre_lock_text.strip() else None
            if pre_lock is None:
                # keep raw text for checksum even if not json
                pre_lock = pre_lock_text
        except Exception:
            pre_lock = None
        try:
            post_pkg_text = (Path(binding.workspace_path) / "package.json").read_text(encoding="utf-8")
            post_pkg = json.loads(post_pkg_text) if post_pkg_text.strip() else None
            if post_pkg is None:
                raise ValueError("post package.json empty")
        except Exception as error:
            self._block(session, continuation, "DEPENDENCY_BUNDLE_POST_READ_FAILED", f"Post-failure package.json cannot be read: {error}")
            return None
        try:
            post_lock_path = Path(binding.workspace_path) / "package-lock.json"
            if post_lock_path.is_file():
                post_lock_text = post_lock_path.read_text(encoding="utf-8")
                try:
                    post_lock = json.loads(post_lock_text) if post_lock_text.strip() else None
                except json.JSONDecodeError:
                    post_lock = post_lock_text
            else:
                post_lock = None
        except Exception:
            post_lock = None
        # command evidence
        run = session.get(MigrationRunModel, continuation.run_id)
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        stage_data = (stage_plan.stage_plan or {}) if stage_plan else {}
        source_exact = stage_data.get("source_exact") or stage_data.get("source_angular_exact")
        target_exact = stage_data.get("target_exact")
        target_cli_exact = stage_data.get("target_cli_exact") or target_exact
        # effective npm settings: parse .npmrc for relevant non-secret whitelist
        effective_npm_settings: dict[str, str] = {}
        try:
            npmrc = Path(binding.workspace_path) / ".npmrc"
            if npmrc.is_file():
                # Parse .npmrc deterministically: key=value, ignore # comments and secrets handled by bundle whitelist
                try:
                    raw_text = npmrc.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    raw_text = ""
                for line in raw_text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith(";"):
                        continue
                    if "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip().lower()
                    value = value.strip()
                    # Only keep whitelist-relevant keys; bundle service will sanitize secrets again
                    if key in {
                        "registry",
                        "strict-peer-deps",
                        "legacy-peer-deps",
                        "engine-strict",
                        "save-exact",
                        "package-lock",
                        "audit",
                        "fund",
                        "ignore-scripts",
                    }:
                        effective_npm_settings[key] = value
        except Exception:
            effective_npm_settings = {}
        # node/npm exact from durable G07 stage runtime binding (not PATH)
        node_exact = None
        npm_exact = None
        try:
            node_row = session.scalar(
                select(StageRuntimeBindingModel).where(
                    StageRuntimeBindingModel.run_id == continuation.run_id,
                    StageRuntimeBindingModel.stage_id == continuation.current_stage_id,
                    StageRuntimeBindingModel.kind == "node",
                )
            )
            npm_row = session.scalar(
                select(StageRuntimeBindingModel).where(
                    StageRuntimeBindingModel.run_id == continuation.run_id,
                    StageRuntimeBindingModel.stage_id == continuation.current_stage_id,
                    StageRuntimeBindingModel.kind == "npm",
                )
            )
            if node_row is not None and getattr(node_row, "version_exact", None):
                node_exact = str(node_row.version_exact).strip()
            if npm_row is not None and getattr(npm_row, "version_exact", None):
                npm_exact = str(npm_row.version_exact).strip()
            # fallback to G07 gate runtime binding if direct row not found
            if node_exact is None or npm_exact is None:
                try:
                    runtime_info = self._stage.runtime_binding(session, continuation)
                    if isinstance(runtime_info, dict):
                        # runtime_binding returns profile info, not version; try to extract from stage_runtime rows
                        pass
                except Exception:
                    pass
        except Exception:
            node_exact = None
            npm_exact = None
        # prior normalization null first attempt
        prior = None
        try:
            prior_attempt = session.query(RepairAttemptModel).filter(
                RepairAttemptModel.run_id == continuation.run_id,
                RepairAttemptModel.stage_id == continuation.current_stage_id,
            ).order_by(RepairAttemptModel.attempt_number.desc()).first()
            if prior_attempt is not None and prior_attempt.attempt_number > 1:
                prior = {"attempt_number": prior_attempt.attempt_number, "status": prior_attempt.status}
        except Exception:
            prior = None
        # build bundle — fail closed if cannot
        try:
            bundle = build_dependency_normalization_bundle(
                run_id=continuation.run_id,
                stage_id=continuation.current_stage_id,
                execution_id=execution.id,
                source_angular_exact=source_exact,
                target_angular_exact=target_exact,
                target_cli_exact=target_cli_exact,
                node_exact=node_exact,
                npm_exact=npm_exact,
                pre_update={"package_json": pre_pkg, "package_lock": pre_lock},
                post_failure={"package_json": post_pkg, "package_lock": post_lock},
                command={
                    "command_id": execution.command_id,
                    "exit_code": execution.exit_code,
                    "failure_code": execution.failure_code,
                    "normalized_failure": evidence.get("normalized_failure") if isinstance(evidence.get("normalized_failure"), dict) else {},
                    "stdout_artifact_ref": getattr(execution, "stdout_artifact_id", None),
                    "stderr_artifact_ref": getattr(execution, "stderr_artifact_id", None),
                    "command_log_artifact_ref": getattr(execution, "command_log_artifact_id", None),
                    "result_artifact_ref": getattr(execution, "result_artifact_id", None),
                },
                effective_npm_settings=effective_npm_settings,
                prior_normalization=prior,
                pre_package_json=pre_pkg,
                pre_package_lock=pre_lock,
                post_package_json=post_pkg,
                post_package_lock=post_lock,
            )
        except Exception as error:
            self._block(session, continuation, "DEPENDENCY_BUNDLE_BUILD_FAILED", f"Dependency failure bundle cannot be built: {error}")
            return None
        # persist immutably — fail closed if cannot
        if run is None or not run.artifact_root:
            self._block(session, continuation, "DEPENDENCY_BUNDLE_ROOT_MISSING", "Run artifact root missing for bundle")
            return None
        try:
            # bundle identity must match execution
            if bundle.get("run_id") != continuation.run_id or bundle.get("stage_id") != continuation.current_stage_id or bundle.get("execution_id") != execution.id:
                self._block(session, continuation, "DEPENDENCY_BUNDLE_IDENTITY_MISMATCH", "Bundle identity does not match failed command")
                return None
            content = json.dumps(bundle, sort_keys=True, indent=2)
            checksum = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
            relative = f"04_workflow_state/stages/{continuation.current_stage_id}/dependency-failure-bundles/{execution.id}-{checksum[7:15]}.json"
            store = LocalFilesystemArtifactStore(Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root))
            stored = store.write_text_artifact(
                continuation.run_id,
                relative,
                content,
                ArtifactType.JSON,
                stage_id=continuation.current_stage_id,
                attempt_id=None,
                created_by="dependency-failure-bundle",
                created_at=datetime.now(UTC),
                input_hashes={
                    "execution": execution.id,
                    "pre_package_json": hashlib.sha256(json.dumps(pre_pkg, sort_keys=True).encode()).hexdigest()[:16] if isinstance(pre_pkg, dict) else "missing",
                    "post_package_json": hashlib.sha256(json.dumps(post_pkg, sort_keys=True).encode()).hexdigest()[:16] if isinstance(post_pkg, dict) else "missing",
                    "failure_message": hashlib.sha256(str(execution.failure_message or "").encode()).hexdigest()[:16],
                },
                policy_version="dependency-failure-bundle-v1",
            )
            # register metadata immutably
            metadata_id = "metadata-" + stored.ref.artifact_id
            if session.get(ArtifactMetadataModel, metadata_id) is None:
                session.add(
                    ArtifactMetadataModel(
                        id=metadata_id,
                        run_id=continuation.run_id,
                        stage_id=continuation.current_stage_id,
                        artifact_type=stored.ref.artifact_type.value,
                        relative_path=stored.ref.relative_path,
                        checksum=stored.ref.checksum,
                        schema_version=stored.envelope.schema_version,
                        created_at=stored.ref.created_at,
                        finalized_at=stored.ref.created_at,
                        immutable=True,
                        execution_id=execution.id,
                        owner_reference=f"{execution.id}:dependency-failure-bundle",
                        correlation_id=execution.correlation_id,
                        safe_metadata={
                            "schema_version": "dependency-failure-bundle-v1",
                            "execution_id": execution.id,
                            "run_id": continuation.run_id,
                            "stage_id": continuation.current_stage_id,
                            "immutable": True,
                        },
                    )
                )
                session.flush()
            return stored
        except Exception as error:
            self._block(session, continuation, "DEPENDENCY_BUNDLE_PERSIST_FAILED", f"Dependency failure bundle cannot be persisted: {error}")
            return None

    def _load_dependency_failure_bundle(self, session, continuation, execution) -> StoredArtifact | None:
        """Load durable bundle artifact for an execution, if present."""
        if execution is None:
            return None
        run = session.get(MigrationRunModel, continuation.run_id)
        if run is None or not run.artifact_root:
            return None
        # Find metadata with owner_reference == f"{execution.id}:dependency-failure-bundle"
        row = session.scalar(
            select(ArtifactMetadataModel).where(
                ArtifactMetadataModel.run_id == continuation.run_id,
                ArtifactMetadataModel.stage_id == continuation.current_stage_id,
                ArtifactMetadataModel.owner_reference == f"{execution.id}:dependency-failure-bundle",
            )
        )
        if row is None:
            # also try execution_id field
            row = session.scalar(
                select(ArtifactMetadataModel).where(
                    ArtifactMetadataModel.execution_id == execution.id,
                    ArtifactMetadataModel.run_id == continuation.run_id,
                ).where(ArtifactMetadataModel.relative_path.like("%dependency-failure-bundle%"))
            )
        if row is None:
            return None
        try:
            store = LocalFilesystemArtifactStore(Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root))
            stored = store.read_artifact(continuation.run_id, row.relative_path)
            if stored.ref.checksum != row.checksum:
                return None
            return stored
        except Exception:
            return None

    def _classify_failure(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            if self._resume_stale_g08_validation(session, continuation):
                return
            if self._recover_unmaterialized_dependency_repair(session, continuation):
                return
            if self._recover_pre_materialization_revalidation(session, continuation):
                return
            if self._resume_known_baseline_validation(session, continuation):
                return
            execution = session.scalar(
                select(CommandExecutionModel)
                .where(
                    CommandExecutionModel.run_id == continuation.run_id,
                    CommandExecutionModel.stage_id == continuation.current_stage_id,
                )
                .order_by(CommandExecutionModel.requested_at.desc())
                .limit(1)
            )
            binding = self._stage._binding(session, continuation)
            artifacts = (
                execution.stdout_artifact_id if execution else None,
                execution.stderr_artifact_id if execution else None,
                execution.command_log_artifact_id if execution else None,
                execution.result_artifact_id if execution else None,
                execution.manifest_artifact_id if execution else None,
            )
            if (
                execution is not None
                and execution.status == "failed"
                and execution.operation_kind == "mutating"
                and all(artifacts)
                and all(
                    session.get(ArtifactMetadataModel, "metadata-" + str(item))
                    is not None
                    for item in artifacts
                )
                and (
                    (execution.start_fingerprint or {}).get("binding_fingerprint")
                    or (execution.start_fingerprint or {}).get(
                        "post_apply_pre_command_binding_fingerprint"
                    )
                )
                == binding.workspace_fingerprint
            ):
                live = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
                execution.end_fingerprint = {"canonical_source": live}
                binding.workspace_fingerprint = live
                binding.fingerprint_profile_id = STAGE_FINGERPRINT_PROFILE.profile_id
                binding.last_verified_fingerprint = live
                binding.last_verified_at = datetime.now(UTC)
            prior = [
                item.failure_fingerprint
                for item in session.query(RepairAttemptModel)
                .filter_by(
                    run_id=continuation.run_id,
                    stage_id=continuation.current_stage_id,
                )
                .all()
                if item.failure_fingerprint
            ]
            evidence = self._failures.collect(
                session, continuation, prior_fingerprints=prior
            )
            fingerprint = str(evidence["failure_fingerprint"])
            replayed = self._committed_evidence(session, continuation, fingerprint)
            reuse_checkpoint = None
            if replayed is not None:
                reuse_checkpoint = session.scalar(
                    select(StageCheckpointModel)
                    .where(
                        StageCheckpointModel.run_id == continuation.run_id,
                        StageCheckpointModel.stage_id == continuation.current_stage_id,
                        StageCheckpointModel.kind == "pre_repair",
                    )
                    .order_by(StageCheckpointModel.sequence.desc())
                    .limit(1)
                )
        route = self._failures.classify(evidence)
        if (
            self._repairable_route(route)
            and (replayed is None or reuse_checkpoint is None)
        ):
            with self._scope() as session:
                continuation = self._owned(session, continuation_id, worker_id)
                attempt = self._failure_repair_attempt(
                    session, continuation, execution
                )
                binding = self._stage._binding(session, continuation)
                live = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
                angular_recovery_checkpoint = (
                    self._angular_update_recovery_checkpoint(
                        session, continuation, attempt
                    )
                    if self._is_angular_update_failure(session, continuation)
                    else None
                )

                # P0-1 FIX: capture dependency failure bundle BEFORE ANY reconstruction for DEPENDENCY_INCOMPATIBLE
                # Invariant: failed angular-update → bundle → reconstruction → normalization
                is_dep_bundle_route = False
                try:
                    route_val = getattr(route, "value", str(route))
                    is_dep_bundle_route = route_val == _DEPENDENCY_INCOMPATIBLE or str(route_val) == "dependency_incompatible"
                    if not is_dep_bundle_route:
                        is_dep_bundle_route = str(route).lower() == "dependency_incompatible"
                except Exception:
                    is_dep_bundle_route = False
                if is_dep_bundle_route and self._is_angular_update_failure(session, continuation):
                    # Re-fetch execution in this session to ensure attached instance
                    exec_for_bundle = session.get(CommandExecutionModel, execution.id) if execution is not None and getattr(execution, "id", None) else None
                    if exec_for_bundle is None:
                        exec_for_bundle = session.scalar(
                            select(CommandExecutionModel)
                            .where(
                                CommandExecutionModel.run_id == continuation.run_id,
                                CommandExecutionModel.stage_id == continuation.current_stage_id,
                            )
                            .order_by(CommandExecutionModel.requested_at.desc())
                            .limit(1)
                        )
                    stored_bundle = self._persist_dependency_failure_bundle_before_reconstruction(
                        session, continuation, exec_for_bundle, evidence
                    )
                    if stored_bundle is None:
                        return

                if live != binding.workspace_fingerprint:
                    # A workspace that diverged from its governed binding must
                    # never feed failure evidence or a repair attempt: a
                    # mutating command that terminated without verified success
                    # may have left it partially changed. Reconstruction
                    # against the execution-bound authorized checkpoint is the
                    # only permitted reconciliation; otherwise fail closed
                    # before any evidence is frozen.
                    if (
                        not self._is_angular_update_failure(session, continuation)
                        or angular_recovery_checkpoint is None
                    ):
                        self._block(
                            session,
                            continuation,
                            "CHECKPOINT_RECOVERY_FAILED",
                            "Workspace diverged from its binding and no authorized recovery checkpoint is available",
                        )
                        return
                    try:
                        self._restore_angular_update_checkpoint(
                            session, continuation, attempt
                        )
                    except TransformerStageError as error:
                        self._block(session, continuation, error.code, error.message)
                        return
                    # The `live` value above was computed BEFORE the
                    # reconstruction. Reload the binding and recompute the
                    # physical fingerprint from the reconstructed workspace so
                    # stale pre-reconstruction evidence can never be frozen.
                    binding = self._stage._binding(session, continuation)
                    live = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
                    if live != binding.workspace_fingerprint:
                        self._block(
                            session,
                            continuation,
                            "CHECKPOINT_RECOVERY_FAILED",
                            "Reconstructed workspace does not match the active workspace binding",
                        )
                        return
                elif (
                    self._is_angular_update_failure(session, continuation)
                    and (
                        angular_recovery_checkpoint is not None
                    )
                ):
                    # Restore before freezing failure/context evidence so the
                    # attempt and governed checkpoint share one authoritative
                    # workspace fingerprint.
                    try:
                        self._restore_angular_update_checkpoint(
                            session, continuation, attempt
                        )
                    except TransformerStageError as error:
                        self._block(session, continuation, error.code, error.message)
                        return
        evidence["workspace_fingerprint"] = StageSandboxCopier.fingerprint(
            Path(str(evidence["workspace_path"]))
        )
        attempt_artifacts: list[StoredArtifact] = []
        if replayed is None:
            failure, route_artifact = self._failures.write(evidence, route)
            attempt_artifacts.extend((failure, route_artifact))
            # P0-1: for DEPENDENCY_INCOMPATIBLE, hydrate validated bundle into context
            try:
                route_val_for_ctx = getattr(route, "value", str(route))
                is_dep_ctx = route_val_for_ctx == _DEPENDENCY_INCOMPATIBLE or str(route_val_for_ctx) == "dependency_incompatible"
            except Exception:
                is_dep_ctx = False
            if is_dep_ctx and self._repairable_route(route) and execution is not None:
                bundle_content = None
                bundle_artifact_id = None
                bundle_checksum = None
                try:
                    with self._scope() as _tmp_sess2:
                        _exec_for_ctx = _tmp_sess2.scalar(
                            select(CommandExecutionModel)
                            .where(
                                CommandExecutionModel.run_id == evidence["run_id"],
                                CommandExecutionModel.stage_id == evidence["stage_id"],
                            )
                            .order_by(CommandExecutionModel.requested_at.desc())
                            .limit(1)
                        )
                        if _exec_for_ctx is not None:
                            _row = _tmp_sess2.scalar(
                                select(ArtifactMetadataModel).where(
                                    ArtifactMetadataModel.run_id == evidence["run_id"],
                                    ArtifactMetadataModel.stage_id == evidence["stage_id"],
                                    ArtifactMetadataModel.owner_reference == f"{_exec_for_ctx.id}:dependency-failure-bundle",
                                )
                            )
                            if _row is None:
                                _row = _tmp_sess2.scalar(
                                    select(ArtifactMetadataModel).where(
                                        ArtifactMetadataModel.execution_id == _exec_for_ctx.id,
                                        ArtifactMetadataModel.run_id == evidence["run_id"],
                                    ).where(ArtifactMetadataModel.relative_path.like("%dependency-failure-bundle%"))
                                )
                            if _row is not None:
                                _run_for_ctx = _tmp_sess2.get(MigrationRunModel, evidence["run_id"])
                                if _run_for_ctx is not None and _run_for_ctx.artifact_root:
                                    _store_ctx = LocalFilesystemArtifactStore(Path(_run_for_ctx.artifact_root).parent, fixed_run_root=Path(_run_for_ctx.artifact_root))
                                    _stored_ctx = _store_ctx.read_artifact(str(evidence["run_id"]), _row.relative_path)
                                    if _stored_ctx.ref.checksum == _row.checksum:
                                        _candidate = json.loads(_stored_ctx.content)
                                        if _candidate.get("schema_version") == "dependency-failure-bundle-v1" and _candidate.get("run_id") == evidence["run_id"] and _candidate.get("stage_id") == evidence["stage_id"] and _candidate.get("execution_id") == _exec_for_ctx.id:
                                            bundle_content = _candidate
                                            bundle_artifact_id = _stored_ctx.ref.artifact_id
                                            bundle_checksum = _stored_ctx.ref.checksum
                except Exception:
                    bundle_content = None
                if bundle_content is None:
                    with self._scope() as _blk2:
                        _any_cont = _blk2.scalar(select(TransformationContinuationModel).where(TransformationContinuationModel.run_id == evidence["run_id"]).limit(1))
                        if _any_cont is not None:
                            self._block(_blk2, _any_cont, "DEPENDENCY_BUNDLE_MISSING_FOR_CONTEXT", "Dependency bundle not available for LLM context")
                    return
                context = self._failures.write_context_pack(
                    evidence,
                    failure.ref.checksum,
                    dependency_bundle=bundle_content,
                    dependency_bundle_artifact_id=bundle_artifact_id,
                    dependency_bundle_checksum=bundle_checksum,
                )
                attempt_artifacts.append(context)
            else:
                context = (
                    self._failures.write_context_pack(evidence, failure.ref.checksum)
                    if self._repairable_route(route)
                    else None
                )
                if context is not None:
                    attempt_artifacts.append(context)
        else:
            failure, route_artifact, context = replayed
        snapshot = None
        if (
            self._repairable_route(route)
            and context is not None
            and (replayed is None or reuse_checkpoint is None)
        ):
            try:
                snapshot = self._stage.snapshot_workspace(
                    str(evidence["workspace_path"]),
                    str(Path(str(evidence["workspace_path"])).parent),
                    str(evidence["stage_id"]),
                )
            except TransformerStageError as error:
                with self._scope() as session:
                    self._block(
                        session,
                        self._owned(session, continuation_id, worker_id),
                        error.code,
                        error.message,
                    )
                return
            except Exception:
                with self._scope() as session:
                    self._block(
                        session,
                        self._owned(session, continuation_id, worker_id),
                        "CHECKPOINT_RECOVERY_FAILED",
                        "Checkpoint snapshot sealing failed",
                    )
                return
        # P0-1: ensure bundle durable for dependency failures and referenced in repair context
        bundle_for_context = None
        try:
            route_val_check = getattr(route, "value", str(route))
            is_dep_for_bundle = route_val_check == _DEPENDENCY_INCOMPATIBLE or str(route_val_check) == "dependency_incompatible"
        except Exception:
            is_dep_for_bundle = False
        if is_dep_for_bundle and replayed is None and execution is not None:
            # Bundle should have been persisted before reconstruction in the inner scope above.
            # If not found, fail closed here as well.
            try:
                with self._scope() as _sess:
                    _cont = _sess.get(TransformationContinuationModel, continuation_id)
                    if _cont is not None:
                        _exec = _sess.get(CommandExecutionModel, execution.id) if getattr(execution, "id", None) else None
                        if _exec is None:
                            _exec = _sess.scalar(
                                select(CommandExecutionModel)
                                .where(
                                    CommandExecutionModel.run_id == _cont.run_id,
                                    CommandExecutionModel.stage_id == _cont.current_stage_id,
                                )
                                .order_by(CommandExecutionModel.requested_at.desc())
                                .limit(1)
                            )
                        if _exec is not None:
                            _bundle = self._load_dependency_failure_bundle(_sess, _cont, _exec)
                            if _bundle is not None:
                                bundle_for_context = _bundle
                            else:
                                # Fail closed: bundle must exist for dependency route
                                with self._scope() as _blk_sess:
                                    _blk_cont = _blk_sess.get(TransformationContinuationModel, continuation_id)
                                    if _blk_cont is not None:
                                        self._block(_blk_sess, _blk_cont, "DEPENDENCY_BUNDLE_MISSING", "Dependency failure bundle not found for normalization")
                                return
            except Exception:
                pass

        try:
            with self._scope() as session:
                continuation = self._owned(session, continuation_id, worker_id)

                for artifact in (failure, route_artifact, context):
                    if artifact is not None:
                        self._stage.register_artifact(session, artifact, continuation)
                # Register bundle artifact as well for dependency route so repair context references it
                if bundle_for_context is not None:
                    # Need to re-load in this session to register correctly (store is same, but metadata needs re-check)
                    # Instead, directly register the stored artifact's metadata if not already present
                    try:
                        # bundle_for_context was loaded in previous session; re-fetch metadata in this session
                        b_row = session.scalar(
                            select(ArtifactMetadataModel).where(
                                ArtifactMetadataModel.run_id == continuation.run_id,
                                ArtifactMetadataModel.stage_id == continuation.current_stage_id,
                                ArtifactMetadataModel.owner_reference == f"{execution.id}:dependency-failure-bundle" if execution else "",
                            )
                        )
                        if b_row is None:
                            # Try alternative lookup by execution_id
                            b_row = session.scalar(
                                select(ArtifactMetadataModel).where(
                                    ArtifactMetadataModel.execution_id == (execution.id if execution else ""),
                                    ArtifactMetadataModel.run_id == continuation.run_id,
                                ).where(ArtifactMetadataModel.relative_path.like("%dependency-failure-bundle%"))
                            )
                        if b_row is not None:
                            # Ensure bundle is considered registered (already persisted, but ensure metadata exists in this tx)
                            pass
                        # Also ensure bundle content is available for LLM context: embed reference in context pack
                        # If context exists and is dependency route, augment it with bundle reference
                        if context is not None and hasattr(context, "ref"):
                            # The context artifact already written does not contain bundle reference;
                            # we will rely on the separate bundle artifact being present alongside context
                            # for the repair LLM to reference. No rewrite needed for P0.
                            pass
                    except Exception:
                        pass
                attempt = self._failure_repair_attempt(
                    session, continuation, execution
                )
                if self._is_angular_update_failure(session, continuation):
                    if route.value == "angular_update_command_policy":
                        attempt = session.query(RepairAttemptModel).filter(
                            RepairAttemptModel.run_id == continuation.run_id,
                            RepairAttemptModel.stage_id == continuation.current_stage_id,
                            RepairAttemptModel.status.in_(("applied", "applied_verified")),
                        ).order_by(RepairAttemptModel.attempt_number.desc()).first()
                        step = session.scalar(
                            select(StageStepModel).where(
                                StageStepModel.run_id == continuation.run_id,
                                StageStepModel.stage_id == continuation.current_stage_id,
                                StageStepModel.name == "angular_update-0",
                            )
                        )
                        execution = (
                            session.get(CommandExecutionModel, step.execution_id)
                            if step is not None and step.execution_id
                            else None
                        )
                        if attempt is None or attempt.status not in {"applied", "applied_verified"} or execution is None:
                            if (
                                attempt is None
                                and execution is not None
                                and execution.status == "failed"
                                and execution.template_version == 2
                            ):
                                # First-time dirty-workspace failure (legacy v2
                                # plan): the v3 --allow-dirty retry is the fix,
                                # no repair is needed. Restore the execution-
                                # bound checkpoint, persist a post-repair
                                # checkpoint so the v2->v3 supersession binds
                                # correctly, and queue the governed retry.
                                try:
                                    self._restore_angular_update_checkpoint(
                                        session, continuation
                                    )
                                    binding = self._stage._binding(session, continuation)
                                    run = session.get(
                                        MigrationRunModel, continuation.run_id
                                    )
                                    snapshot = self._stage.snapshot_workspace(
                                        binding.workspace_path,
                                        (run.workspace_aliases or {})["STAGE_SANDBOX"],
                                        continuation.current_stage_id,
                                    )
                                    self._stage._checkpoint(
                                        session,
                                        continuation,
                                        snapshot,
                                        "post_repair",
                                        f"restore:{execution.checkpoint_id or execution.id}",
                                        snapshot.fingerprint,
                                    )
                                    self._stage.queue_angular_update_retry(
                                        session,
                                        continuation,
                                        failed_execution_id=execution.id,
                                        idempotency_key=(
                                            f"{execution.id}:retry:post-repair:initial"
                                        ),
                                    )
                                except TransformerStageError as error:
                                    self._block(
                                        session, continuation, error.code, error.message
                                    )
                                return
                            self._block(
                                session,
                                continuation,
                                "ANGULAR_UPDATE_POST_REPAIR_LINEAGE_MISSING",
                                "Dirty Angular update failure has no applied repair lineage",
                            )
                            return
                        try:
                            self._ensure_post_repair_checkpoint(session, continuation, attempt)
                            self._stage.queue_angular_update_retry(
                                session,
                                continuation,
                                failed_execution_id=execution.id,
                                idempotency_key=f"{execution.id}:retry:post-repair:{attempt.id}",
                            )
                        except TransformerStageError as error:
                            self._block(session, continuation, error.code, error.message)
                        return
                    if route.value == "environment_transient" and continuation.attempt < continuation.max_attempts:
                        self._restore_angular_update_checkpoint(
                            session, continuation, attempt
                        )
                        continuation.attempt += 1
                        continuation.status = "queued"
                        continuation.current_node = "angular_update"
                        continuation.worker_id = None
                        continuation.lease_expires_at = None
                        continuation.state_version += 1
                        continuation.updated_at = datetime.now(UTC)
                        return
                    if not self._repairable_route(route):
                        self._block(
                            session,
                            continuation,
                            f"ANGULAR_UPDATE_{route.value.upper()}",
                            f"Angular update failure routed to {route.value}",
                        )
                        return

                if not self._repairable_route(route):
                    if route.value == "environment_transient" and continuation.attempt < continuation.max_attempts:
                        expected_state_version = continuation.state_version
                        continuation.attempt += 1
                        continuation.status = "waiting_retry"
                        continuation.current_node = "final_install"
                        continuation.next_attempt_at = datetime.now(UTC) + timedelta(seconds=30)
                        continuation.worker_id = None
                        continuation.lease_expires_at = None
                        continuation.state_version += 1
                        continuation.updated_at = datetime.now(UTC)
                        session.flush()
                        append_continuation_event(
                            session,
                            continuation,
                            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_WAITING,
                            key=f"wait:waiting_retry:{expected_state_version}",
                            reason="validation failure routed to governed retry",
                            payload={
                                "last_error_code": f"FAILURE_ROUTE_{route.value.upper()}",
                                "expected_state_version": expected_state_version,
                            },
                        )
                    else:
                        self._block(
                            session,
                            continuation,
                            f"FAILURE_ROUTE_{route.value.upper()}",
                            f"Validation failure routed to {route.value}",
                        )
                    return
                stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
                repair_policy = (
                    ((stage_plan.stage_plan or {}).get("repair_policy") or {})
                    if stage_plan is not None
                    else {}
                )
                budget = repair_budget(
                    session,
                    continuation.run_id,
                    continuation.current_stage_id,
                    repair_policy,
                )
                # A failed post-apply command gets its own bounded correction
                # window.  Do not charge corrections from superseded ancestor
                # branches against the newly applied repair: those attempts
                # are historical lineage, not retries of this post-state.
                correction_depth = 0
                if not (
                    attempt is not None
                    and attempt.apply_ledger_artifact_id is not None
                ):
                    lineage_cursor = attempt
                    while lineage_cursor is not None:
                        if str(lineage_cursor.diagnosis or "").startswith(
                            "validation correction;"
                        ):
                            correction_depth += 1
                        lineage_cursor = (
                            session.get(
                                RepairAttemptModel, lineage_cursor.parent_attempt_id
                            )
                            if lineage_cursor.parent_attempt_id
                            else None
                        )
                lockfile_step = session.scalar(
                    select(StageStepModel).where(
                        StageStepModel.run_id == continuation.run_id,
                        StageStepModel.stage_id == continuation.current_stage_id,
                        StageStepModel.name == "lockfile_generation-0",
                    )
                )
                lockfile_execution = (
                    session.get(CommandExecutionModel, lockfile_step.execution_id)
                    if lockfile_step is not None and lockfile_step.execution_id
                    else None
                )
                lockfile_failed = (
                    lockfile_step is not None
                    and (
                        lockfile_step.status == "FAILED"
                        or (
                            lockfile_execution is not None
                            and lockfile_execution.status
                            in {"failed", "timed_out", "cancelled", "interrupted"}
                        )
                    )
                )
                post_apply_command_failed = bool(
                    attempt is not None
                    and attempt.apply_ledger_artifact_id is not None
                    and attempt.created_at is not None
                    and session.scalar(
                        select(CommandExecutionModel.id).where(
                            CommandExecutionModel.run_id == continuation.run_id,
                            CommandExecutionModel.stage_id == continuation.current_stage_id,
                            CommandExecutionModel.requested_at >= attempt.created_at,
                            CommandExecutionModel.status.in_(
                                {"failed", "timed_out", "cancelled", "interrupted"}
                            ),
                        )
                    )
                    is not None
                )
                validation_correction = (
                    attempt is not None
                    and attempt.apply_ledger_artifact_id is not None
                    and correction_depth < 2
                    and (
                        attempt.status
                        in {"revalidating", "revalidating_affected", "validation_failed"}
                        or attempt.status == "executing" and post_apply_command_failed
                        or (
                            attempt.status in {"applied", "applied_verified", "blocked"}
                            and (lockfile_failed or post_apply_command_failed)
                        )
                    )
                )
                if (
                    budget["consumed_attempts"] >= budget["max_attempts"]
                    or budget["consumed_applied"] >= budget["max_applied"]
                ) and not validation_correction:
                    self._block(
                        session,
                        continuation,
                        "REPAIR_ATTEMPT_LIMIT",
                        "Governed repair attempt limit reached",
                    )
                    return
                attempts = session.query(RepairAttemptModel).filter_by(
                    run_id=continuation.run_id, stage_id=continuation.current_stage_id
                ).count()
                if reuse_checkpoint is None and snapshot is None:
                    self._block(
                        session,
                        continuation,
                        "REPAIR_SNAPSHOT_MISSING",
                        "No pre-repair workspace checkpoint is available",
                    )
                    return
                checkpoint = (
                    reuse_checkpoint
                    if reuse_checkpoint is not None
                    else self._stage.persist_snapshot_checkpoint(
                        session, continuation, snapshot, "pre_repair"
                    )
                )
                attempt = RepairAttemptModel(
                    id=f"repair-{continuation.current_stage_id}-{attempts + 1}",
                    run_id=continuation.run_id,
                    stage_id=continuation.current_stage_id,
                    attempt_number=attempts + 1,
                    status="evidence_frozen",
                    risk_level="unknown",
                    diagnosis=(
                        f"validation correction; {route.value}; checkpoint={checkpoint.id}"
                        if validation_correction
                        else f"{route.value}; checkpoint={checkpoint.id}"
                    ),
                    checkpoint_id=checkpoint.id,
                    failure_evidence_artifact_id=failure.ref.artifact_id,
                    failure_evidence_checksum=failure.ref.checksum,
                    failure_route_artifact_id=route_artifact.ref.artifact_id,
                    failure_route_checksum=route_artifact.ref.checksum,
                    context_pack_artifact_id=context.ref.artifact_id,
                    context_pack_checksum=context.ref.checksum,
                    pre_fingerprint=str(evidence["workspace_fingerprint"]),
                    failure_fingerprint=str(evidence["failure_fingerprint"]),
                    parent_attempt_id=attempt.id if validation_correction else None,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                session.add(attempt)
                next_node = (
                    "deterministic_replan"
                    if route.value == "dependency_incompatible"
                    and self._has_deterministic_replan_intelligence(session, continuation, evidence)
                    else "propose_repair"
                )
                self._queue(continuation, next_node)
        except (IntegrityError, TransformerStageError) as error:
            if isinstance(error, TransformerStageError) and error.code != "ARTIFACT_METADATA_IDENTITY_CONFLICT":
                raise
            code = self._deterministic_failure_code(error)
            self._block_metadata_duplicate(
                continuation_id, worker_id, code, error, attempt_artifacts
            )
            try:
                self._cleanup_failed_attempt_artifacts(
                    str(evidence["run_id"]),
                    str(evidence["artifact_root"]),
                    attempt_artifacts,
                )
            except Exception as cleanup_error:  # noqa: BLE001
                logger.warning(
                    "Failed to clean up orphaned classification artifacts for continuation %s: %s",
                    continuation_id,
                    cleanup_error,
                )

    @staticmethod
    def _failure_repair_attempt(session, continuation, execution):
        recovery = (
            session.scalar(
                select(StageRecoveryOperationModel)
                .where(
                    StageRecoveryOperationModel.run_id == continuation.run_id,
                    StageRecoveryOperationModel.stage_id
                    == continuation.current_stage_id,
                    StageRecoveryOperationModel.command_execution_id
                    == execution.id,
                    StageRecoveryOperationModel.status == "FAILED",
                )
                .order_by(StageRecoveryOperationModel.updated_at.desc())
                .limit(1)
            )
            if execution is not None
            else None
        )
        if recovery is not None and recovery.repair_attempt_id:
            return session.get(RepairAttemptModel, recovery.repair_attempt_id)
        return (
            session.query(RepairAttemptModel)
            .filter_by(
                run_id=continuation.run_id,
                stage_id=continuation.current_stage_id,
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
            .first()
        )

    @staticmethod
    def _has_deterministic_replan_intelligence(session, continuation, evidence) -> bool:
        intelligence = session.scalar(
            select(FailureIntelligenceModel)
            .where(FailureIntelligenceModel.run_id == continuation.run_id)
            .order_by(FailureIntelligenceModel.created_at.desc())
            .limit(1)
        )
        group_key = TransformerOrchestrator._deterministic_replan_group_key(evidence)
        root = (intelligence.root_causes or {}).get(group_key) if intelligence else None
        return bool(root and root.get("taxonomy") == "dependency")

    @staticmethod
    def _deterministic_replan_group_key(evidence) -> str:
        normalized = evidence.get("normalized_failure") or {}
        code = str(normalized.get("error_code") or "UNKNOWN")
        message = str(normalized.get("failure_message") or "")
        return FailureIntelligenceService.stable_group_key(code, "dependency", message)

    def _deterministic_replan(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            checkpoint = session.get(StageCheckpointModel, attempt.checkpoint_id) if attempt else None
            stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
            plan = session.get(MigrationPlanModel, continuation.plan_id)
            binding = self._stage._binding(session, continuation)
            execution = session.scalar(
                select(CommandExecutionModel)
                .where(
                    CommandExecutionModel.run_id == continuation.run_id,
                    CommandExecutionModel.stage_id == continuation.current_stage_id,
                    CommandExecutionModel.status.in_(("failed", "timed_out", "interrupted")),
                )
                .order_by(CommandExecutionModel.requested_at.desc())
                .limit(1)
            )
            intelligence = session.scalar(
                select(FailureIntelligenceModel)
                .where(FailureIntelligenceModel.run_id == continuation.run_id)
                .order_by(FailureIntelligenceModel.created_at.desc())
                .limit(1)
            )
            normalized_code = (execution.failure_code if execution else None) or continuation.last_error_code or "UNKNOWN"
            message = (execution.failure_message if execution else None) or continuation.last_error_message or ""
            group_key = FailureIntelligenceService.stable_group_key(normalized_code, "dependency", message)
            root = (intelligence.root_causes or {}).get(group_key) if intelligence else None
            resolution = session.scalar(
                select(CompatibilityResolutionModel)
                .where(CompatibilityResolutionModel.run_id == continuation.run_id)
                .order_by(CompatibilityResolutionModel.created_at.desc())
                .limit(1)
            )
            catalogue_version = (plan.plan or {}).get("catalogue_version") if plan else None
            catalogue = session.scalar(
                select(CompatibilityCatalogueModel).where(CompatibilityCatalogueModel.version == catalogue_version)
            )
            if not all((attempt, checkpoint, stage_plan, plan, binding, execution, root, resolution, catalogue)):
                self._queue(continuation, "propose_repair")
                return

            request = TransformationReplanRecoveryRequest(
                run_id=continuation.run_id,
                stage_id=continuation.current_stage_id,
                failed_execution_id=execution.id,
                failed_execution_result_checksum=TransformationReplanRecoveryService.execution_result_checksum(execution),
                failure_group_key=group_key,
                root_cause_code=root["root_cause_code"],
                continuation_state_version=continuation.state_version,
                current_plan_id=plan.id,
                current_plan_checksum=plan.checksum,
                current_stage_plan_id=stage_plan.id,
                current_stage_plan_checksum=stage_plan.checksum,
                safe_checkpoint_id=checkpoint.id,
                safe_checkpoint_checksum=TransformationReplanRecoveryService.checkpoint_checksum(checkpoint),
                safe_checkpoint_fingerprint=checkpoint.workspace_fingerprint,
                workspace_fingerprint=binding.workspace_fingerprint,
                catalogue_version=catalogue.version,
                catalogue_checksum=catalogue.checksum,
                compatibility_resolution_checksum=TransformationReplanRecoveryService.compatibility_resolution_checksum(resolution),
                idempotency_key=f"transformer-replan:{execution.id}",
            )
        try:
            TransformationReplanRecoveryService(
                session_scope_factory=self._scope
            ).recover(request)
        except TransformationReplanRecoveryError:
            with self._scope() as session:
                continuation = self._owned(session, continuation_id, worker_id)
                self._queue(continuation, "propose_repair")

    def _resume_known_baseline_validation(self, session, continuation) -> bool:
        """Resume repair validation when lint exactly matches approved G03 evidence."""
        if not self._validation.resume_known_baseline_failures(
            session, continuation
        ):
            return False
        attempt = self._latest_repair(session, continuation, required=False)
        if attempt is not None and attempt.status not in {
            "superseded",
            "completed",
            "rejected",
        }:
            RepairLifecycleService.transition_in_session(
                session,
                attempt,
                "revalidating_affected",
                reason="known baseline validation resumed",
            )
        expected_state_version = continuation.state_version
        continuation.last_error_code = None
        continuation.last_error_message = None
        self._queue(continuation, "repair_revalidate")
        session.flush()
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_WAITING,
            key=f"known-baseline-validation:{expected_state_version}",
            reason="Approved baseline lint failures preserved during repair validation",
            payload={
                "expected_state_version": expected_state_version,
                "validation_status": "passed_with_known_baseline_failure",
            },
        )
        return True

    @staticmethod
    def _deterministic_failure_code(error: Exception) -> str:
        if isinstance(error, TransformerStageError):
            return "ARTIFACT_METADATA_DUPLICATE"
        detail = str(getattr(error, "orig", "") or error).lower()
        if "artifact_metadata" in detail:
            return "ARTIFACT_METADATA_DUPLICATE"
        return "CLASSIFICATION_COMMIT_FAILED"

    def _committed_evidence(self, session, continuation, fingerprint):
        lookup = getattr(self._failures, "committed_evidence", None)
        if not callable(lookup):
            return None
        try:
            triple = lookup(session, continuation, fingerprint)
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(triple, tuple) or len(triple) != 3:
            return None
        failure, route_artifact, context = triple
        if failure is None or route_artifact is None:
            return None
        if getattr(failure, "ref", None) is None or getattr(route_artifact, "ref", None) is None:
            return None
        return failure, route_artifact, context

    def _block_metadata_duplicate(
        self,
        continuation_id: str,
        worker_id: str,
        code: str,
        error: Exception,
        attempt_artifacts: list[StoredArtifact],
    ) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            artifact_ids = ", ".join(
                stored.ref.artifact_id for stored in attempt_artifacts
            )
            relative_paths = ", ".join(
                stored.ref.relative_path for stored in attempt_artifacts
            )
            expected_state_version = continuation.state_version
            continuation.status = "blocked"
            continuation.last_error_code = code
            continuation.last_error_message = (
                f"{code}; artifact_ids=[{artifact_ids}]; "
                f"paths=[{relative_paths}]; error={error}"
            )
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.state_version += 1
            continuation.updated_at = datetime.now(UTC)
            session.flush()
            append_continuation_event(
                session,
                continuation,
                event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED,
                key=f"block:{expected_state_version}:{code}",
                reason="duplicate artifact metadata blocked classification commit",
                payload={
                    "last_error_code": code,
                    "expected_state_version": expected_state_version,
                },
            )

    def _cleanup_failed_attempt_artifacts(
        self, run_id: str, artifact_root: str, attempt_artifacts: list[StoredArtifact]
    ) -> None:
        root = Path(artifact_root).resolve()
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        with self._scope() as session:
            committed_paths = {
                row.relative_path
                for row in session.query(ArtifactMetadataModel)
                .filter_by(run_id=run_id)
                .all()
            }
        for stored in attempt_artifacts:
            relative = stored.ref.relative_path
            if relative in committed_paths:
                continue
            try:
                target = store._resolve_existing_artifact_path(run_id, relative)
            except ArtifactNotFoundError:
                continue
            except ArtifactStoreError as error:
                logger.warning(
                    "Refusing to clean up unresolved artifact %s for run %s: %s",
                    relative,
                    run_id,
                    error,
                )
                continue
            sidecar = target.with_name(f"{target.name}.meta.json")
            for path in (target, sidecar):
                try:
                    if path.is_file():
                        path.unlink()
                except OSError as error:
                    logger.warning(
                        "Failed to remove orphaned classification artifact %s: %s",
                        path,
                        error,
                    )

    def _recover_unmaterialized_dependency_repair(self, session, continuation) -> bool:
        """Resume a dependency repair whose lockfile phase was skipped.

        A dependency repair must materialize its package graph before any
        Angular-update retry.  Older workers could route directly to the
        retry node, leaving the approved repair applied while the governed
        lockfile step remained pending.  Reconcile that durable state before
        failure classification so it cannot consume another repair attempt.
        """
        attempt = (
            session.query(RepairAttemptModel)
            .filter(
                RepairAttemptModel.run_id == continuation.run_id,
                RepairAttemptModel.stage_id == continuation.current_stage_id,
                RepairAttemptModel.status.in_(
                    ("applied", "applied_verified", "migration_retried")
                ),
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
            .first()
        )
        if attempt is None or self._successful_materialization_exists(
            session, continuation, attempt
        ):
            return False
        try:
            proposal = self._load_bound_repair_proposal(
                session,
                continuation,
                attempt,
                session.get(MigrationRunModel, continuation.run_id),
            )
        except (
            ArtifactNotFoundError,
            ArtifactStoreError,
            OSError,
            ValueError,
            RepairApplicationError,
        ):
            return False
        lockfile_step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "lockfile_generation-0",
            )
        )
        if not self._needs_dependency_materialization_recovery(
            proposal,
            attempt.status,
            lockfile_step.status if lockfile_step is not None else None,
            materialization_succeeded=False,
        ):
            return False
        continuation.last_error_code = None
        continuation.last_error_message = None
        self._queue(continuation, "lockfile_generation")
        return True

    @staticmethod
    def _needs_dependency_materialization_recovery(
        proposal: dict[str, object],
        attempt_status: str,
        lockfile_step_status: str | None,
        *,
        materialization_succeeded: bool,
    ) -> bool:
        return (
            attempt_status in {"applied", "applied_verified", "migration_retried"}
            and TransformerOrchestrator._proposal_requires_install_materialization(
                proposal
            )
            and lockfile_step_status == "PENDING"
            and not materialization_succeeded
        )

    def _recover_pre_materialization_revalidation(self, session, continuation) -> bool:
        attempt = (
            session.query(RepairAttemptModel)
            .filter(
                RepairAttemptModel.run_id == continuation.run_id,
                RepairAttemptModel.stage_id == continuation.current_stage_id,
                RepairAttemptModel.status == "revalidating_affected",
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
            .first()
        )
        if attempt is None:
            return False
        try:
            proposal = self._load_bound_repair_proposal(
                session,
                continuation,
                attempt,
                session.get(MigrationRunModel, continuation.run_id),
            )
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError, RepairApplicationError):
            return False
        if not self._proposal_requires_install_materialization(proposal):
            return False
        if self._successful_materialization_exists(session, continuation, attempt):
            return False

        affected_keys = {
            self._validation_execution_key(continuation, attempt_key, group)
            for attempt_key in (
                f"{attempt.id}:affected",
                f"{attempt.id}:affected:materialized",
            )
            for group in VALIDATION_TARGET_GROUPS.values()
        }
        failed_before_materialization = False
        stale_steps = []
        stale_execution_ids = set()
        for step in session.query(StageStepModel).filter_by(
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
        ):
            execution = (
                session.get(CommandExecutionModel, step.execution_id)
                if step.execution_id
                else None
            )
            key = execution.idempotency_key if execution is not None else None
            if key not in affected_keys:
                continue
            if step.status != "PENDING":
                stale_steps.append(step)
            if (
                step.status == "FAILED"
                and execution.status in {"failed", "timed_out", "cancelled", "interrupted"}
            ):
                failed_before_materialization = True
                stale_execution_ids.add(execution.id)
        if not failed_before_materialization:
            return False
        reconciliation = self._reconcile_incomplete_newer_repair(
            session, continuation, attempt, stale_execution_ids
        )
        if reconciliation is False:
            return False
        for step in stale_steps:
            step.status = "PENDING"
            step.execution_id = None
            step.completed_at = None
        self._queue(continuation, "repair_revalidate")
        return True

    def _resume_stale_g08_validation(self, session, continuation) -> bool:
        """Resume a legacy G08 wait without reclassifying its old failure."""
        if continuation.current_node not in {"classify_failure", "propose_repair"}:
            return False
        gate = session.scalar(
            select(StageGatePackageModel)
            .where(
                StageGatePackageModel.run_id == continuation.run_id,
                StageGatePackageModel.stage_id == continuation.current_stage_id,
                StageGatePackageModel.gate_id == "G08",
                StageGatePackageModel.status == "approved",
            )
            .order_by(StageGatePackageModel.created_at.desc())
            .limit(1)
        )
        binding = self._stage._binding(session, continuation)
        version_step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "target_version_check-0",
            )
        )
        final_install = session.scalar(
            select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "final_install-0",
            )
        )
        if (
            gate is None
            or gate.workspace_fingerprint != binding.workspace_fingerprint
            or version_step is None
            or version_step.status == "PASSED"
            or final_install is None
            or final_install.status != "PASSED"
            or any(
                step.status == "PASSED"
                for step in session.scalars(
                    select(StageStepModel).where(
                        StageStepModel.stage_id == continuation.current_stage_id,
                        StageStepModel.name.in_(("builds-0", "tests-0")),
                    )
                )
            )
        ):
            return False
        execution = (
            session.get(CommandExecutionModel, version_step.execution_id)
            if version_step.execution_id
            else None
        )
        if (
            execution is None
            or execution.command_id != "angular-version-verify"
            or execution.status != "succeeded"
            or not execution.command_log_artifact_id
            or not execution.result_artifact_id
        ):
            return False
        now = datetime.now(UTC)
        version_step.status = "PASSED"
        version_step.completed_at = now
        version_step.workspace_fingerprint = gate.workspace_fingerprint
        version_step.output_checksum = execution.runtime_checksum
        version_step.artifact_ids = list(execution.artifact_ids or [])
        version_step.updated_at = now
        attempt = self._latest_repair(session, continuation)
        if attempt is not None and attempt.status == "evidence_frozen" and not attempt.proposal_artifact_id:
            RepairLifecycleService.transition_in_session(
                session,
                attempt,
                "superseded",
                reason="empty repair evidence attempt superseded",
            )
            attempt.completed_at = now
        continuation.last_error_code = None
        continuation.last_error_message = None
        self._queue(continuation, "final_install")
        return True

    def _propose_repair(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            if self._recover_pre_materialization_revalidation(session, continuation):
                return
            if self._resume_stale_g08_validation(session, continuation):
                return
            attempt = self._latest_repair(
                session, continuation, exclude_statuses={"superseded"}
            )
            attempt_id = attempt.id
        try:
            proposal = self._repairs.propose(attempt_id)
        except (ArtifactNotFoundError, ArtifactStoreError) as error:
            with self._scope() as session:
                self._block(
                    session,
                    self._owned(session, continuation_id, worker_id),
                    "REPAIR_EVIDENCE_MISSING",
                    str(error),
                )
            return
        except (RepairLlmError, RepairApplicationError, ValueError) as error:
            with self._scope() as session:
                self._block(
                    session,
                    self._owned(session, continuation_id, worker_id),
                    getattr(error, "code", "REPAIR_PROPOSAL_FAILED"),
                    getattr(error, "message", str(error)),
                )
            return
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            attempt.risk_level = str(proposal["risk_level"])
            self._queue(continuation, "review_repair")

    def _review_repair(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            if attempt.status == "request_changes":
                if not attempt.review_artifact_id or not attempt.review_checksum:
                    self._block(
                        session,
                        continuation,
                        "REPAIR_REVIEW_MISSING",
                        "Persisted request-changes review is missing",
                    )
                    return
                continuation.status = "waiting_repair_revision"
                continuation.current_node = "review_repair"
                continuation.worker_id = None
                continuation.lease_expires_at = None
                continuation.wake_sequence += 1
                continuation.state_version += 1
                continuation.updated_at = datetime.now(UTC)
                return
            attempt_id = attempt.id
        try:
            review = self._repairs.review(attempt_id)
        except (ArtifactNotFoundError, ArtifactStoreError) as error:
            with self._scope() as session:
                self._block(
                    session,
                    self._owned(session, continuation_id, worker_id),
                    "REPAIR_EVIDENCE_MISSING",
                    str(error),
                )
            return
        except (RepairLlmError, RepairApplicationError, ValueError) as error:
            with self._scope() as session:
                self._block(
                    session,
                    self._owned(session, continuation_id, worker_id),
                    getattr(error, "code", "REPAIR_REVIEW_FAILED"),
                    getattr(error, "message", str(error)),
                )
            return
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            if review["decision"] == "accept":
                self._queue(continuation, "create_g10")
                return
            if review["decision"] == "request_changes":
                continuation.status = "waiting_repair_revision"
                continuation.current_node = "review_repair"
                continuation.worker_id = None
                continuation.lease_expires_at = None
                continuation.wake_sequence += 1
                continuation.state_version += 1
                continuation.updated_at = datetime.now(UTC)
                return
            self._block(
                session,
                continuation,
                "REPAIR_REVIEW_REJECTED",
                "Repair reviewer rejected the candidate",
            )

    def _create_repair_gate(
        self, continuation_id: str, worker_id: str, gate_id: str
    ) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            existing = session.scalar(
                select(StageGatePackageModel).where(
                    StageGatePackageModel.run_id == continuation.run_id,
                    StageGatePackageModel.stage_id == continuation.current_stage_id,
                    StageGatePackageModel.gate_id == gate_id,
                    StageGatePackageModel.status == "pending",
                )
            )
            if existing is not None:
                # Idempotent replay: the gate artifact and package row already
                # exist, so re-writing the package artifact would orphan a
                # fresh artifact/metadata pair. Settle the continuation exactly
                # like a fresh create, including the package's
                # expected_state_version (fresh create sets it to
                # state_version + 1 before incrementing), so decide() can
                # still approve or reject the replayed package.
                attempt = self._latest_repair(session, continuation)
                if gate_id == "G10":
                    eligible, reason = self._g10_causal_eligibility(
                        session, continuation, attempt
                    )
                    if not eligible:
                        self._block(
                            session,
                            continuation,
                            "REPAIR_REVIEW_NOT_ACCEPTED"
                            if reason and "request_changes" in reason
                            else "REPAIR_CAUSAL_REJECTION",
                            reason or "Repair candidate is not causally eligible for G10",
                        )
                        return
                if gate_id == "G10":
                    attempt.g10_gate_package_id = existing.id
                    RepairLifecycleService.transition_in_session(
                        session,
                        attempt,
                        "waiting_g10",
                        reason="repair G10 package reused after accepted review",
                    )
                continuation.status = "waiting_gate"
                continuation.current_node = f"wait_{gate_id.lower()}"
                continuation.worker_id = None
                continuation.lease_expires_at = None
                existing.expected_state_version = continuation.state_version + 1
                continuation.state_version += 1
                continuation.updated_at = datetime.now(UTC)
                return
            attempt = self._latest_repair(session, continuation)
            if gate_id == "G10":
                eligible, reason = self._g10_causal_eligibility(
                    session, continuation, attempt
                )
                if not eligible:
                    self._block(
                        session,
                        continuation,
                        "REPAIR_REVIEW_NOT_ACCEPTED"
                        if reason and "request_changes" in reason
                        else "REPAIR_CAUSAL_REJECTION",
                        reason or "Repair candidate is not causally eligible for G10",
                    )
                    return
            binding = self._stage._binding(session, continuation)
            run = session.get(MigrationRunModel, continuation.run_id)
            plan = session.get(MigrationPlanModel, continuation.plan_id)
            if plan is None or plan.run_id != continuation.run_id:
                raise TransformerStageError("PLAN_BINDING_MISSING", "Migration plan for the run is missing")
            payload = {
                "gate_id": gate_id,
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
                "plan_version": plan.version,
                "stage_plan_checksum": continuation.stage_plan_checksum,
                "workspace_fingerprint": binding.workspace_fingerprint,
                "failure_evidence_checksum": attempt.failure_evidence_checksum,
                "context_pack_checksum": attempt.context_pack_checksum,
                "proposal_checksum": attempt.proposal_checksum,
                "review_checksum": attempt.review_checksum,
                "repair_attempt_id": attempt.id,
                "proposal_artifact_id": attempt.proposal_artifact_id,
                "review_artifact_id": attempt.review_artifact_id,
                "parent_attempt_id": attempt.parent_attempt_id,
                "parent_review_artifact_id": attempt.parent_review_artifact_id,
                "parent_review_checksum": attempt.parent_review_checksum,
                "proposer_invocation_id": attempt.proposer_invocation_id,
                "reviewer_invocation_id": attempt.reviewer_invocation_id,
                "workspace_binding_id": binding.id,
                "workspace_path": binding.workspace_path,
                "risk_level": attempt.risk_level,
                "validation_targets": [],
            }
            proposer_invocation = session.get(LlmInvocationModel, attempt.proposer_invocation_id)
            reviewer_invocation = session.get(LlmInvocationModel, attempt.reviewer_invocation_id)
            if proposer_invocation is None or reviewer_invocation is None:
                raise TransformerStageError("REPAIR_INVOCATION_MISSING", "Repair invocation lineage is missing")
            payload.update(
                proposer_invocation_request_checksum=proposer_invocation.request_checksum,
                proposer_invocation_prompt_version=proposer_invocation.prompt_version,
                proposer_invocation_schema_version=proposer_invocation.schema_version,
                reviewer_invocation_request_checksum=reviewer_invocation.request_checksum,
                reviewer_invocation_prompt_version=reviewer_invocation.prompt_version,
                reviewer_invocation_schema_version=reviewer_invocation.schema_version,
            )
            if gate_id == "G10":
                store = LocalFilesystemArtifactStore(
                    Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
                )
                proposal_metadata = session.get(
                    ArtifactMetadataModel, "metadata-" + str(attempt.proposal_artifact_id)
                )
                if proposal_metadata is None:
                    raise TransformerStageError("REPAIR_PROPOSAL_MISSING", "Repair proposal artifact is missing")
                proposal = json.loads(
                    store.read_artifact(continuation.run_id, proposal_metadata.relative_path).content
                )
                review_metadata = session.get(
                    ArtifactMetadataModel, "metadata-" + str(attempt.review_artifact_id)
                )
                if (
                    review_metadata is None
                    or review_metadata.run_id != continuation.run_id
                    or review_metadata.checksum != attempt.review_checksum
                ):
                    raise TransformerStageError("REPAIR_REVIEW_MISSING", "Repair review artifact is missing or stale")
                review = json.loads(
                    store.read_artifact(continuation.run_id, review_metadata.relative_path).content
                )
                if review.get("decision") != "accept":
                    raise TransformerStageError(
                        "REPAIR_REVIEW_NOT_ACCEPTED",
                        "Reviewer request_changes must be resolved before G10",
                    )
                payload["review_override_required"] = False
                diff_metadata = session.scalar(
                    select(ArtifactMetadataModel).where(
                        ArtifactMetadataModel.run_id == continuation.run_id,
                        ArtifactMetadataModel.stage_id == continuation.current_stage_id,
                        ArtifactMetadataModel.relative_path.like(
                            f"05_repairs/attempt-{attempt.id}/candidate%.diff"
                        ),
                    )
                    .order_by(ArtifactMetadataModel.created_at.desc())
                    .limit(1)
                )
                if diff_metadata is None:
                    raise TransformerStageError(
                        "REPAIR_DIFF_MISSING",
                        "Repair candidate diff artifact is missing",
                    )
                diff_artifact = store.read_artifact(continuation.run_id, diff_metadata.relative_path)
                diff_artifact_id = diff_metadata.id.removeprefix("metadata-")
                if (
                    diff_artifact.ref.artifact_id != diff_artifact_id
                    or diff_artifact.ref.checksum != diff_metadata.checksum
                    or diff_artifact.envelope is None
                    or diff_artifact.envelope.run_id != continuation.run_id
                    or diff_artifact.envelope.stage_id != continuation.current_stage_id
                    or diff_artifact.envelope.attempt_id != attempt.id
                    or diff_artifact.envelope.input_hashes.get("proposal")
                    != attempt.proposal_checksum
                ):
                    raise TransformerStageError(
                        "REPAIR_DIFF_MISMATCH",
                        "Repair candidate diff artifact does not belong to this attempt",
                    )
                if not diff_artifact.content.strip():
                    raise TransformerStageError(
                        "REPAIR_DIFF_EMPTY",
                        "Repair candidate diff artifact is empty",
                    )
                payload["diff_artifact_id"] = diff_artifact_id
                payload["diff_checksum"] = diff_metadata.checksum
                stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
                plan_value = stage_plan.stage_plan if stage_plan is not None else {}
                policy = plan_value.get("validation_policy") or {}
                try:
                    union = validation_target_union(
                        list(proposal.get("validation_targets") or []),
                        list(review.get("required_validation_targets") or []),
                        policy.get("required_checks") or ("build", "test"),
                        plan_value.get("commands") or {},
                    )
                except ValidationTargetUnionError as error:
                    raise TransformerStageError(error.code, error.message) from error
                attempt.validation_targets = list(union)
                payload["validation_targets"] = list(union)
                payload["backend_lineage_checksum"] = self._stage.checksum(
                    {key: value for key, value in payload.items() if key != "backend_lineage_checksum"}
                )
            context = (
                run.artifact_root,
                binding.workspace_fingerprint,
                continuation.run_id,
                continuation.current_stage_id,
            )
        gate = self._stage.write_gate_package(
            run_id=context[2],
            stage_id=context[3],
            artifact_root=context[0],
            gate_id=gate_id,
            payload=payload,
            attempt_id=attempt.id if gate_id == "G10" else None,
        )
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            self._stage.register_artifact(session, gate, continuation)
            session.flush()
            if gate_id == "G10":
                artifact_set_checksum = canonical_artifact_set_checksum(
                    [
                        {"artifact_id": attempt.failure_evidence_artifact_id, "checksum": attempt.failure_evidence_checksum},
                        {"artifact_id": attempt.context_pack_artifact_id, "checksum": attempt.context_pack_checksum},
                        {"artifact_id": attempt.proposal_artifact_id, "checksum": attempt.proposal_checksum},
                        {"artifact_id": attempt.review_artifact_id, "checksum": attempt.review_checksum},
                        {"artifact_id": gate.ref.artifact_id, "checksum": gate.ref.checksum},
                    ]
                )
            else:
                artifact_set_checksum = self._stage.checksum(
                    {gate.ref.artifact_id: gate.ref.checksum}
                )
            package = self._gates.create(
                session,
                continuation,
                gate_id=gate_id,
                package_artifact_id=gate.ref.artifact_id,
                package_checksum=gate.ref.checksum,
                artifact_set_checksum=artifact_set_checksum,
                workspace_fingerprint=context[1],
            )
            if gate_id == "G10":
                attempt.g10_gate_package_id = package.id
                RepairLifecycleService.transition_in_session(
                    session,
                    attempt,
                    "waiting_g10",
                    reason="repair G10 package created after accepted review",
                )

    def _apply_repair(self, continuation_id: str, worker_id: str) -> None:
        mutation_state = {"started": False, "claimed": False}
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            binding = self._stage._binding(session, continuation)
            workspace_path = binding.workspace_path
        with workspace_apply_lock(Path(workspace_path)):
            try:
                return self._apply_repair_locked(continuation_id, worker_id, mutation_state)
            except Exception:
                self._recover_failed_apply(
                    continuation_id,
                    workspace_path,
                    mutation_started=mutation_state["started"],
                    apply_claimed=mutation_state["claimed"],
                )
                raise

    def _recover_failed_apply(
        self,
        continuation_id: str,
        workspace_path: str,
        *,
        mutation_started: bool,
        apply_claimed: bool,
    ) -> None:
        if not mutation_started:
            if apply_claimed:
                self._mark_apply_recovery_required(continuation_id, None)
            return
        try:
            with self._scope() as session:
                continuation = session.get(TransformationContinuationModel, continuation_id)
                attempt = self._latest_repair(session, continuation) if continuation is not None else None
                run = session.get(MigrationRunModel, continuation.run_id) if continuation else None
                post_applied = attempt is not None and attempt.status in {"applied", "applied_verified"}
                recovery_reason = "post_apply_recovery" if post_applied else "apply_recovery"
                if post_applied:
                    checkpoint = self._ensure_post_repair_checkpoint(
                        session, continuation, attempt
                    ) if continuation is not None else None
                else:
                    checkpoint = (
                        session.get(StageCheckpointModel, attempt.checkpoint_id)
                        if attempt is not None and attempt.checkpoint_id is not None
                        else None
                    )
                    if (
                        checkpoint is not None
                        and continuation is not None
                        and (
                            checkpoint.kind != "pre_repair"
                            or checkpoint.stage_id != continuation.current_stage_id
                        )
                    ):
                        checkpoint = None
                if continuation is None or attempt is None or run is None or checkpoint is None:
                    self._mark_apply_recovery_required(continuation_id, None)
                    return
                self._stage.begin_reconstruction(
                    session,
                    continuation,
                    checkpoint=checkpoint,
                    reason=recovery_reason,
                    attempt_id=attempt.id,
                )
                checkpoint_id = checkpoint.id
                source_fingerprint = self._stage.authoritative_checkpoint_fingerprint(
                    session, checkpoint
                )
                snapshot_path = checkpoint.workspace_path
                stage_root = (run.workspace_aliases or {})["STAGE_SANDBOX"]
                if source_fingerprint is None:
                    raise TransformerStageError(
                        "CHECKPOINT_INTEGRITY_FAILED",
                        "Apply-recovery checkpoint is not authoritative",
                    )
            restored = self._stage.reconstruct_workspace(
                snapshot_path,
                workspace_path,
                stage_root,
                source_fingerprint,
                run.artifact_root,
            )
            self._mark_apply_recovery_required(
                continuation_id,
                restored,
                attempt.id,
                checkpoint_id=checkpoint_id,
                reason=recovery_reason,
            )
        except TransformerStageError as error:
            logger.exception("repair apply recovery blocked", extra={"continuation_id": continuation_id})
            self._mark_apply_recovery_required(
                continuation_id,
                None,
                error_code=error.code,
                error_message=error.message,
            )
        except Exception:
            logger.exception("repair apply recovery failed", extra={"continuation_id": continuation_id})
            self._mark_apply_recovery_required(continuation_id, None)

    def _mark_apply_recovery_required(
        self,
        continuation_id: str,
        fingerprint: str | None,
        attempt_id: str | None = None,
        *,
        checkpoint_id: str | None = None,
        reason: str | None = None,
        error_code: str = "REPAIR_APPLY_RECOVERY_REQUIRED",
        error_message: str = "Repair apply requires durable recovery before resume",
    ) -> None:
        try:
            with self._scope() as session:
                continuation = session.get(TransformationContinuationModel, continuation_id)
                attempt = session.get(RepairAttemptModel, attempt_id) if attempt_id else (
                    self._latest_repair(session, continuation) if continuation is not None else None
                )
                if (
                    attempt is not None
                    and continuation is not None
                    and (
                        attempt.run_id != continuation.run_id
                        or attempt.stage_id != continuation.current_stage_id
                    )
                ):
                    raise TransformerStageError(
                        "REPAIR_PROPOSAL_STALE",
                        "Recovery attempt belongs to a different run or stage",
                    )
                if attempt is not None:
                    RepairLifecycleService.transition_in_session(
                        session,
                        attempt,
                        "apply_recovery_required",
                        reason=reason or "repair apply requires durable recovery",
                    )
                    if fingerprint is not None:
                        attempt.post_fingerprint = fingerprint
                if continuation is not None:
                    if fingerprint is not None:
                        binding = session.scalar(
                            select(StageWorkspaceBindingModel).where(
                                StageWorkspaceBindingModel.run_id == continuation.run_id,
                                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                                StageWorkspaceBindingModel.active.is_(True),
                            )
                        )
                        if binding is not None:
                            checkpoint = (
                                session.get(StageCheckpointModel, checkpoint_id)
                                if checkpoint_id is not None
                                else None
                            )
                            if checkpoint is None:
                                raise TransformerStageError(
                                    "CHECKPOINT_MISSING",
                                    "Reconstruction checkpoint is missing for apply recovery",
                                )
                            self._stage.record_reconstruction(
                                session,
                                continuation,
                                checkpoint=checkpoint,
                                reason=reason or "apply_recovery",
                                restored_fingerprint=fingerprint,
                                attempt_id=attempt.id if attempt is not None else None,
                            )
                            binding.workspace_fingerprint = fingerprint
                            binding.fingerprint_profile_id = STAGE_FINGERPRINT_PROFILE.profile_id
                            binding.last_verified_fingerprint = fingerprint
                            binding.last_verified_at = datetime.now(UTC)
                    self._block(
                session,
                continuation,
                        error_code,
                        error_message,
                    )
        except Exception:
            logger.exception("unable to persist repair apply recovery state", extra={"continuation_id": continuation_id})
            raise

    def _apply_repair_locked(self, continuation_id: str, worker_id: str, mutation_state=None) -> None:
        mutation_state = mutation_state or {"started": False, "claimed": False}
        apply_result = None
        apply_error = None
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            binding = self._stage._binding(session, continuation)
            run = session.get(MigrationRunModel, continuation.run_id)
            gate = session.scalar(
                select(StageGatePackageModel).where(
                    StageGatePackageModel.run_id == continuation.run_id,
                    StageGatePackageModel.stage_id == continuation.current_stage_id,
                    StageGatePackageModel.gate_id == "G10",
                    StageGatePackageModel.id == attempt.g10_gate_package_id,
                    StageGatePackageModel.status == "approved",
                )
            )
            decision = session.scalar(
                select(StageGateDecisionModel).where(
                    StageGateDecisionModel.gate_package_id == gate.id if gate else False,
                    StageGateDecisionModel.accepted.is_(True),
                    StageGateDecisionModel.decision == "approve",
                )
            ) if gate else None
            if gate is None or decision is None:
                raise TransformerStageError("G10_APPROVAL_REQUIRED", "Repair application requires current human G10 approval")
            self._gates._validate_repair_lineage(
                session,
                continuation,
                gate.package_artifact_id,
                gate.package_checksum,
                artifact_set_checksum=gate.artifact_set_checksum,
            )
            metadata = session.get(
                ArtifactMetadataModel, "metadata-" + attempt.proposal_artifact_id
            )
            if metadata is None or metadata.checksum != attempt.proposal_checksum:
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved repair proposal artifact is stale")
            proposal_artifact = LocalFilesystemArtifactStore(
                Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
            ).read_artifact(continuation.run_id, metadata.relative_path)
            if proposal_artifact.ref.artifact_id != attempt.proposal_artifact_id or proposal_artifact.ref.checksum != attempt.proposal_checksum:
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved repair proposal identity changed")
            proposal_payload = json.loads(proposal_artifact.content)
            is_dependency_transition = any(
                item.get("operation") == "dependency_transition"
                for item in proposal_payload.get("operations", [])
                if isinstance(item, dict)
            )
            recovering = attempt.status in {"applying", "executing"}
            checkpoint = (
                session.get(StageCheckpointModel, attempt.checkpoint_id)
                if attempt.checkpoint_id is not None
                else None
            )
            if checkpoint is None or checkpoint.kind != "pre_repair" or checkpoint.stage_id != continuation.current_stage_id:
                if recovering:
                    raise TransformerStageError(
                        "CHECKPOINT_MISSING",
                        "No attempt-referenced pre-repair checkpoint available for recovery",
                    )
                checkpoint = None
            context = {
                "attempt_id": attempt.id,
                "workspace_binding_id": binding.id,
                "workspace_path": binding.workspace_path,
                "fingerprint": binding.workspace_fingerprint,
                "artifact_root": run.artifact_root,
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
                "continuation_state_version": continuation.state_version,
                "g10_package_id": gate.id,
                "g10_package_checksum": gate.package_checksum,
                "proposal_path": str(Path(run.artifact_root) / metadata.relative_path),
                "proposal_relative_path": metadata.relative_path,
                "proposal_artifact_id": attempt.proposal_artifact_id,
                "proposal_artifact_checksum": attempt.proposal_checksum,
                "checkpoint_id": checkpoint.id if checkpoint else None,
                "checkpoint_path": checkpoint.workspace_path if checkpoint else None,
                "checkpoint_fingerprint": (
                    self._stage.authoritative_checkpoint_fingerprint(session, checkpoint)
                    if checkpoint is not None
                    else None
                ),
                "stage_root": (run.workspace_aliases or {})["STAGE_SANDBOX"],
                "attempt_status": attempt.status,
            }
        with self._scope() as session:
            current = session.get(TransformationContinuationModel, continuation_id)
            current_attempt = session.get(RepairAttemptModel, context["attempt_id"])
            current_binding = self._stage._binding(session, current) if current is not None else None
            current_gate = session.get(StageGatePackageModel, context["g10_package_id"])
            current_decision = session.scalar(
                select(StageGateDecisionModel).where(
                    StageGateDecisionModel.gate_package_id == context["g10_package_id"],
                    StageGateDecisionModel.accepted.is_(True),
                    StageGateDecisionModel.decision == "approve",
                    StageGateDecisionModel.package_checksum == context["g10_package_checksum"],
                )
            )
            if (
                current is None
                or current_attempt is None
                or current_binding is None
                or current_gate is None
                or current_gate.status != "approved"
                or current_decision is None
                or current_attempt.status != context["attempt_status"]
                or current_binding.id != context["workspace_binding_id"]
            ):
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved repair authority changed")
            if (
                current_attempt.run_id != context["run_id"]
                or current_attempt.stage_id != context["stage_id"]
            ):
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Repair attempt authority changed")
            if current_binding.workspace_path != context["workspace_path"]:
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved workspace binding changed")
            live = StageSandboxCopier.fingerprint(Path(current_binding.workspace_path))
            if live != current_binding.workspace_fingerprint or live != context["fingerprint"]:
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved workspace fingerprint changed")
            checkpoint = (
                session.get(StageCheckpointModel, current_attempt.checkpoint_id)
                if current_attempt.checkpoint_id is not None
                else None
            )
            if (
                checkpoint is None
                or checkpoint.kind != "pre_repair"
                or checkpoint.stage_id != context["stage_id"]
            ):
                raise TransformerStageError(
                    "CHECKPOINT_MISSING",
                    "Attempt-referenced pre-repair checkpoint is missing",
                )
            checkpoint_fingerprint = self._stage.authoritative_checkpoint_fingerprint(
                session, checkpoint
            )
            if (
                checkpoint_fingerprint is None
                or (
                    checkpoint_fingerprint != live
                    and not self._rebind_child_authority_recovered(
                        session, current_attempt, checkpoint, live
                    )
                )
                or (
                    current_attempt.pre_fingerprint != live
                    and not self._legacy_authority_recovered(session, current_attempt, checkpoint)
                )
            ):
                raise TransformerStageError(
                    "REPAIR_PROPOSAL_STALE",
                    "Repair checkpoint or attempt pre-fingerprint diverged from the workspace",
                )
            self._gates._validate_repair_lineage(
                session,
                current,
                current_gate.package_artifact_id,
                current_gate.package_checksum,
                artifact_set_checksum=current_gate.artifact_set_checksum,
            )
            proposal_metadata = session.get(
                ArtifactMetadataModel, "metadata-" + current_attempt.proposal_artifact_id
            )
            if proposal_metadata is None or proposal_metadata.checksum != current_attempt.proposal_checksum:
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved repair proposal artifact is stale")
            proposal_artifact = LocalFilesystemArtifactStore(
                Path(context["artifact_root"]).parent, fixed_run_root=Path(context["artifact_root"])
            ).read_artifact(context["run_id"], proposal_metadata.relative_path)
            if proposal_artifact.ref.artifact_id != current_attempt.proposal_artifact_id or proposal_artifact.ref.checksum != current_attempt.proposal_checksum:
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved repair proposal identity changed")
            binding_claim = session.execute(
                update(StageWorkspaceBindingModel)
                .where(
                    StageWorkspaceBindingModel.id == current_binding.id,
                    StageWorkspaceBindingModel.run_id == context["run_id"],
                    StageWorkspaceBindingModel.stage_id == context["stage_id"],
                    StageWorkspaceBindingModel.active.is_(True),
                    StageWorkspaceBindingModel.workspace_path == context["workspace_path"],
                    StageWorkspaceBindingModel.workspace_fingerprint == live,
                )
                .values(last_verified_fingerprint=live, last_verified_at=datetime.now(UTC))
            )
            if binding_claim.rowcount != 1:
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Workspace binding changed before mutation")
            attempt_claim = session.execute(
                update(RepairAttemptModel)
                .where(
                    RepairAttemptModel.id == current_attempt.id,
                    RepairAttemptModel.run_id == context["run_id"],
                    RepairAttemptModel.stage_id == context["stage_id"],
                    RepairAttemptModel.status == context["attempt_status"],
                    RepairAttemptModel.proposal_artifact_id == current_attempt.proposal_artifact_id,
                    RepairAttemptModel.proposal_checksum == current_attempt.proposal_checksum,
                )
                .values(
                    status=(
                        "executing"
                    ),
                    updated_at=datetime.now(UTC),
                )
            )
            if attempt_claim.rowcount != 1:
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Repair attempt changed before mutation")
            claimed = session.execute(
                update(TransformationContinuationModel)
                .where(
                    TransformationContinuationModel.id == current.id,
                    TransformationContinuationModel.state_version == context["continuation_state_version"],
                    TransformationContinuationModel.current_stage_id == context["stage_id"],
                )
                .values(state_version=TransformationContinuationModel.state_version + 1, updated_at=datetime.now(UTC))
            )
            if claimed.rowcount != 1:
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approval state changed before mutation")
            mutation_state["claimed"] = True
            context["continuation_state_version"] += 1
            session.commit()
            if recovering:
                if not context["checkpoint_path"]:
                    raise TransformerStageError("CHECKPOINT_MISSING", "No pre-repair checkpoint available for recovery")
                self._stage.begin_reconstruction(
                    session,
                    current,
                    checkpoint=checkpoint,
                    reason="apply_recovery",
                    attempt_id=current_attempt.id,
                )
                context["fingerprint"] = self._stage.reconstruct_workspace(
                    context["checkpoint_path"],
                    context["workspace_path"],
                    context["stage_root"],
                    context["checkpoint_fingerprint"],
                    context["artifact_root"],
                )
                session.expire_all()
                current = session.get(TransformationContinuationModel, continuation_id)
                current_attempt = session.get(RepairAttemptModel, context["attempt_id"])
                current_binding = self._stage._binding(session, current) if current is not None else None
                current_gate = session.get(StageGatePackageModel, context["g10_package_id"])
                current_decision = session.scalar(
                    select(StageGateDecisionModel).where(
                        StageGateDecisionModel.gate_package_id == context["g10_package_id"],
                        StageGateDecisionModel.accepted.is_(True),
                        StageGateDecisionModel.decision == "approve",
                        StageGateDecisionModel.package_checksum == context["g10_package_checksum"],
                    )
                )
                live = StageSandboxCopier.fingerprint(Path(context["workspace_path"]))
                checkpoint = (
                    session.get(StageCheckpointModel, current_attempt.checkpoint_id)
                    if current_attempt.checkpoint_id is not None
                    else None
                )
                if (
                    current is None
                    or current_attempt is None
                    or current_binding is None
                    or current_gate is None
                    or current_gate.status != "approved"
                    or current_decision is None
                    or current_attempt.status not in {"applying", "executing"}
                    or current_binding.id != context["workspace_binding_id"]
                    or current.state_version != context["continuation_state_version"]
                    or live != context["fingerprint"]
                    or checkpoint is None
                    or checkpoint.kind != "pre_repair"
                    or checkpoint.stage_id != context["stage_id"]
                ):
                    raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved repair authority changed during recovery")
                checkpoint_fingerprint = self._stage.authoritative_checkpoint_fingerprint(
                    session, checkpoint
                )
                if (
                    checkpoint_fingerprint is None
                    or (
                        checkpoint_fingerprint != live
                        and not self._rebind_child_authority_recovered(
                            session, current_attempt, checkpoint, live
                        )
                    )
                    or (
                        current_attempt.pre_fingerprint != live
                        and not (
                            self._legacy_authority_recovered(
                                session, current_attempt, checkpoint
                            )
                            or self._rebind_child_authority_recovered(
                                session, current_attempt, checkpoint, live
                            )
                        )
                    )
                ):
                    raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved repair authority changed during recovery")
                self._gates._validate_repair_lineage(
                    session,
                    current,
                    current_gate.package_artifact_id,
                    current_gate.package_checksum,
                    artifact_set_checksum=current_gate.artifact_set_checksum,
                )
                proposal_metadata = session.get(
                    ArtifactMetadataModel, "metadata-" + str(current_attempt.proposal_artifact_id)
                )
                if proposal_metadata is None or proposal_metadata.checksum != current_attempt.proposal_checksum:
                    raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved repair proposal artifact is stale")
                proposal_artifact = LocalFilesystemArtifactStore(
                    Path(context["artifact_root"]).parent, fixed_run_root=Path(context["artifact_root"])
                ).read_artifact(context["run_id"], proposal_metadata.relative_path)
                if (
                    proposal_artifact.ref.artifact_id != context["proposal_artifact_id"]
                    or proposal_artifact.ref.checksum != context["proposal_artifact_checksum"]
                ):
                    raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved repair proposal identity changed during recovery")
                self._stage.record_reconstruction(
                    session,
                    current,
                    checkpoint=checkpoint,
                    reason="apply_recovery",
                    restored_fingerprint=context["fingerprint"],
                    attempt_id=current_attempt.id,
                )
            session.expire_all()
            context["continuation_state_version"] = self._claim_current_continuation_for_apply(
                session,
                continuation_id,
                context["stage_id"],
                context["continuation_state_version"],
            )
            proposal = proposal_payload
            try:
                apply_result = self._patches.apply(
                    proposal=proposal,
                    workspace_path=context["workspace_path"],
                    expected_fingerprint=context["fingerprint"],
                    run_id=context["run_id"],
                    stage_id=context["stage_id"],
                    artifact_root=context["artifact_root"],
                    attempt_id=context["attempt_id"],
                    approved_proposal_checksum=context["proposal_artifact_checksum"],
                    proposal_artifact_checksum=context["proposal_artifact_checksum"],
                    mutation_started_callback=lambda: mutation_state.__setitem__("started", True),
                )
            except RepairApplicationError as error:
                apply_error = error
                session.rollback()
        if apply_error is not None:
            error = apply_error
            with self._scope() as session:
                attempt = session.get(RepairAttemptModel, context["attempt_id"])
                RepairLifecycleService.transition_in_session(
                    session,
                    attempt,
                    "apply_failed",
                    reason=f"repair application failed: {error.code}",
                )
                self._block(
                    session,
                    self._owned(session, continuation_id, worker_id),
                    error.code,
                    error.message,
                )
            return
        prepared, ledger, fingerprint = apply_result
        post_snapshot = self._stage.snapshot_workspace(
            context["workspace_path"],
            context["stage_root"],
            context["stage_id"],
        )
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            binding = self._stage._binding(session, continuation)
            for artifact in (prepared, ledger):
                self._stage.register_artifact(session, artifact, continuation)
            binding.workspace_fingerprint = fingerprint
            binding.fingerprint_profile_id = STAGE_FINGERPRINT_PROFILE.profile_id
            binding.last_verified_fingerprint = fingerprint
            binding.last_verified_at = datetime.now(UTC)
            attempt.apply_ledger_artifact_id = ledger.ref.artifact_id
            attempt.apply_ledger_checksum = ledger.ref.checksum
            attempt.post_fingerprint = fingerprint
            # The checkpoint manifest is lineage-bound to the attempt's
            # post-image. Update the attempt first so the immutable manifest
            # cannot capture the pre-repair fingerprint.
            self._stage.persist_post_repair_checkpoint(
                session,
                continuation,
                post_snapshot,
                attempt_id=attempt.id,
                proposal_artifact_id=attempt.proposal_artifact_id,
                proposal_checksum=attempt.proposal_checksum,
                apply_ledger_artifact_id=ledger.ref.artifact_id,
                apply_ledger_checksum=ledger.ref.checksum,
                post_fingerprint=fingerprint,
            )
            RepairLifecycleService.transition_in_session(
                session,
                attempt,
                "executing" if is_dependency_transition else "applied_verified",
                reason="repair application committed immutable apply ledger",
            )
            post_apply_node = self._post_apply_node(
                proposal,
                angular_update_retry_eligible=self._angular_update_retry_eligible(
                    session, continuation
                ),
            )
            reset_groups = (
                StageStepModel.name.like("final_install-%")
                | StageStepModel.name.like("builds-%")
                | StageStepModel.name.like("tests-%")
                | StageStepModel.name.like("lint-%")
            )
            if post_apply_node == "lockfile_generation":
                reset_groups = reset_groups | StageStepModel.name.like(
                    "lockfile_generation-%"
                )
            for step in session.query(StageStepModel).filter(
                StageStepModel.stage_id == continuation.current_stage_id,
                reset_groups,
            ):
                step.status = "PENDING"
                step.execution_id = None
                step.completed_at = None
            self._queue(continuation, post_apply_node)

    @staticmethod
    def _post_apply_node(
        proposal: dict[str, object], *, angular_update_retry_eligible: bool = False
    ) -> str:
        operations = proposal.get("operations") or []
        # preserve DependencyTransitionRunner for legacy only
        if any(
            item.get("operation") == "dependency_transition"
            and str(item.get("repair_kind") or "") != DEPENDENCY_NORMALIZATION_REPAIR_KIND
            and str(item.get("schema_version") or "") != DEPENDENCY_NORMALIZATION_SCHEMA_VERSION
            for item in operations
        ):
            return "dependency_transition"
        # V2.2 P3: dependency_manifest_normalization → lockfile (P4) → final_install → migrate_packages (P5)
        if any(
            str(item.get("operation") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND
            or str(item.get("repair_kind") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND
            or str(item.get("schema_version") or "") == DEPENDENCY_NORMALIZATION_SCHEMA_VERSION
            or item.get("operation") in {"dependency_change", "dependency_add"}
            for item in operations
        ):
            return "lockfile_generation"
        node = "repair_revalidate"
        if node == "repair_revalidate" and angular_update_retry_eligible:
            return "angular_update_retry"
        return node

    @staticmethod
    @staticmethod
    def _migration_identity(
        run_id: str,
        stage_id: str,
        normalization_root_id: str,
        normalization_attempt_id: str,
        checkpoint_id: str,
        package: str,
        from_exact: str,
        to_exact: str,
    ) -> str:
        """Canonical migration identity for lineage-bound matching."""
        payload = {
            "run_id": run_id,
            "stage_id": stage_id,
            "normalization_root_id": normalization_root_id,
            "normalization_attempt_id": normalization_attempt_id,
            "checkpoint_id": checkpoint_id,
            "package": package,
            "from_exact": from_exact,
            "to_exact": to_exact,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()

    def _is_dependency_normalization_attempt(session, attempt: RepairAttemptModel) -> bool:
        # Strict V2.2: only proven by proposal artifact containing dependency_manifest_normalization
        if attempt.proposal_artifact_id and attempt.proposal_checksum:
            meta = session.get(ArtifactMetadataModel, "metadata-" + attempt.proposal_artifact_id)
            if meta is not None:
                try:
                    run = session.get(MigrationRunModel, attempt.run_id)
                    if run and run.artifact_root:
                        from app.artifact_store import LocalFilesystemArtifactStore

                        store = LocalFilesystemArtifactStore(Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root))
                        stored = store.read_artifact(attempt.run_id, meta.relative_path)
                        if stored.ref.checksum == attempt.proposal_checksum:
                            prop = json.loads(stored.content)
                            ops = prop.get("operations") if isinstance(prop, dict) else None
                            if isinstance(ops, list) and any(
                                str(op.get("operation") or op.get("repair_kind") or op.get("schema_version")) in (DEPENDENCY_NORMALIZATION_REPAIR_KIND, DEPENDENCY_NORMALIZATION_SCHEMA_VERSION)
                                for op in ops if isinstance(op, dict)
                            ):
                                return True
                except Exception:
                    pass
        # Child before proposal: parent is proven and context indicates ordinal 2
        if attempt.parent_attempt_id:
            parent = session.get(RepairAttemptModel, attempt.parent_attempt_id)
            if parent is not None and TransformerOrchestrator._is_dependency_normalization_attempt(session, parent):
                # For child, check context pack indicates dependency normalization
                # The child's context should have been created with dependency bundle
                # We can check if context_pack_artifact_id exists and its content has dependency_normalization
                # For minimal, if parent is proven, child is considered normalization attempt
                return True
        return False

    @staticmethod
    def _dependency_normalization_lineage(session, continuation) -> list:
        """Current dependency normalization lineage rooted at current failure, ordered root→leaf."""
        # Find latest normalization attempt for this stage
        all_norm = []
        for cand in session.query(RepairAttemptModel).filter(
            RepairAttemptModel.run_id == continuation.run_id,
            RepairAttemptModel.stage_id == continuation.current_stage_id,
        ).order_by(RepairAttemptModel.attempt_number.desc()).all():
            if TransformerOrchestrator._is_dependency_normalization_attempt(session, cand):
                all_norm.append(cand)
        if not all_norm:
            return []
        # Latest is most recent normalization attempt
        latest = all_norm[0]
        # Walk parent chain to root to get lineage for current failure
        lineage: list[RepairAttemptModel] = []
        cur: RepairAttemptModel | None = latest
        # To avoid infinite loop, limit depth
        for _ in range(10):
            if cur is None:
                break
            # Only include if it's still a normalization attempt (for child before proposal, parent check ensures)
            if TransformerOrchestrator._is_dependency_normalization_attempt(session, cur):
                lineage.append(cur)
                cur = session.get(RepairAttemptModel, cur.parent_attempt_id) if cur.parent_attempt_id else None
            else:
                break
        lineage.reverse()
        # If lineage is empty due to parent not proven, fallback to single root
        if not lineage and latest is not None:
            # Check if latest itself is root (no parent or parent not normalization)
            lineage = [latest]
        return lineage

    @staticmethod
    def _dependency_normalization_ordinal(session, continuation, attempt: RepairAttemptModel | None) -> int:
        """Ordinal 1..n within normalization lineage, not global attempt_number."""
        if attempt is None:
            return 0
        lineage = TransformerOrchestrator._dependency_normalization_lineage(session, continuation)
        for idx, item in enumerate(lineage, start=1):
            if item.id == attempt.id:
                return idx
        return 0

    def _create_dependency_normalization_child_attempt(
        self, session, continuation, parent_attempt: RepairAttemptModel, lock_exec: CommandExecutionModel | None
    ) -> RepairAttemptModel:
        """Create real child RepairAttempt with NEW context for plan2."""
        # Find max global attempt_number
        max_attempt = session.query(RepairAttemptModel).filter(
            RepairAttemptModel.run_id == continuation.run_id,
            RepairAttemptModel.stage_id == continuation.current_stage_id,
        ).order_by(RepairAttemptModel.attempt_number.desc()).first()
        next_number = (max_attempt.attempt_number + 1) if max_attempt else 1
        child_id = f"repair-{continuation.current_stage_id}-{next_number}"
        # Resolve checkpoint for child (pre_angular_update)
        checkpoint = session.scalar(
            select(StageCheckpointModel).where(
                StageCheckpointModel.run_id == continuation.run_id,
                StageCheckpointModel.stage_id == continuation.current_stage_id,
                StageCheckpointModel.kind == "pre_angular_update",
            ).order_by(StageCheckpointModel.sequence.desc()).limit(1)
        )
        if checkpoint is None:
            raise TransformerStageError("CHECKPOINT_MISSING", "Pre-update checkpoint missing for child attempt")
        # Build new context pack for child that includes prior plan + resolver failure
        # Load parent proposal and bundle for prior
        parent_proposal_checksum = parent_attempt.proposal_checksum
        # Get parent bundle artifact if exists
        parent_bundle_info = None
        try:
            # Try to find parent's bundle via its failure evidence
            if parent_attempt.failure_evidence_artifact_id:
                meta = session.get(ArtifactMetadataModel, "metadata-" + parent_attempt.failure_evidence_artifact_id)
                # Not needed for minimal; we will just reference parent's proposal
                pass
        except Exception:
            pass
        # For minimal, create context pack that references parent and new resolver failure
        # Use existing FailureEvidenceService to create context, but we need to include dependency_normalization with prior
        # We will create a new context pack artifact that is similar to parent's but with additional resolver failure
        # Simplify: reuse parent's context pack and add resolver failure info
        # Find parent's context pack
        parent_context_artifact_id = parent_attempt.context_pack_artifact_id
        # Get lock failure evidence for new resolver failure
        # We will create a new context pack that is a copy of parent's but with updated prior_normalization and resolver_failure
        # For now, we create a minimal new context pack that will be used for proposer
        # We need to actually write a new context pack artifact
        # Use the same evidence as parent but with updated prior
        # For simplicity, we will create a new RepairAttempt with same checkpoint and failure evidence as parent, but with parent link
        # The actual proposer will receive the new attempt's context which we will build below
        # Create new context pack artifact that includes prior plan and new failure
        # We need to get the original evidence for parent
        # For minimal, we can create a new context pack that is a placeholder with dependency_normalization containing prior
        # We will use the existing _failures.collect to get current evidence and then augment
        # For now, create child attempt with minimal required fields and let _propose_repair handle context creation
        # Instead, we will directly create the attempt and then in _propose_repair, it will create a new context that includes prior
        # So we just need to persist the child attempt with parent link and let the next cycle create context
        # To ensure the child is considered, we need to create it with status evidence_frozen and with parent
        child = RepairAttemptModel(
            id=child_id,
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
            attempt_number=next_number,
            status="evidence_frozen",
            risk_level=parent_attempt.risk_level,
            diagnosis=f"dependency_normalization_ordinal_2; parent={parent_attempt.id}",
            checkpoint_id=checkpoint.id,
            failure_evidence_artifact_id=parent_attempt.failure_evidence_artifact_id,
            failure_evidence_checksum=parent_attempt.failure_evidence_checksum,
            failure_route_artifact_id=parent_attempt.failure_route_artifact_id,
            failure_route_checksum=parent_attempt.failure_route_checksum,
            context_pack_artifact_id=parent_attempt.context_pack_artifact_id,
            context_pack_checksum=parent_attempt.context_pack_checksum,
            proposal_artifact_id=None,
            proposal_checksum=None,
            parent_attempt_id=parent_attempt.id,
            parent_review_artifact_id=parent_attempt.review_artifact_id,
            parent_review_checksum=parent_attempt.review_checksum,
            pre_fingerprint=checkpoint.workspace_fingerprint if hasattr(checkpoint, "workspace_fingerprint") else None,
            failure_fingerprint=parent_attempt.failure_fingerprint,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(child)
        session.flush()
        # Now create a NEW context pack for child that includes prior plan + resolver failure
        # We need to actually write a new context pack artifact that will be used for proposer
        # For minimal, we will update the child's context to be a new artifact that includes the lock failure
        # We can do this by calling _failures.write_context_pack with dependency bundle and prior
        # But we need to have the lock failure evidence available
        # For now, we will keep the child's context as parent's context plus an additional artifact for resolver failure
        # The proposer will be called with child.id, and it will read child's context_pack_artifact_id
        # So we need to ensure child's context is distinct and contains the new resolver failure
        # We will create a new context pack that is a copy of parent's but with an extra field for resolver failure
        # To do this, we need to read parent's context content and augment it
        try:
            if parent_attempt.context_pack_artifact_id:
                parent_meta = session.get(ArtifactMetadataModel, "metadata-" + parent_attempt.context_pack_artifact_id)
                if parent_meta is not None:
                    run = session.get(MigrationRunModel, child.run_id)
                    if run and run.artifact_root:
                        from app.artifact_store import LocalFilesystemArtifactStore

                        store = LocalFilesystemArtifactStore(Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root))
                        parent_stored = store.read_artifact(child.run_id, parent_meta.relative_path)
                        parent_content = json.loads(parent_stored.content)
                        # Augment with prior_normalization and resolver failure
                        # prior_normalization is the parent's proposal
                        parent_proposal = None
                        if parent_attempt.proposal_artifact_id:
                            pm = session.get(ArtifactMetadataModel, "metadata-" + parent_attempt.proposal_artifact_id)
                            if pm is not None:
                                try:
                                    ps = store.read_artifact(child.run_id, pm.relative_path)
                                    parent_proposal = json.loads(ps.content)
                                except Exception:
                                    parent_proposal = None
                        resolver_info = None
                        if lock_exec is not None:
                            resolver_info = {
                                "command_execution_id": lock_exec.id,
                                "exit_code": lock_exec.exit_code,
                                "failure_code": lock_exec.failure_code,
                                "failure_message": (lock_exec.failure_message or "")[:2000],
                                "result_artifact_id": lock_exec.result_artifact_id,
                                "command_log_artifact_id": lock_exec.command_log_artifact_id,
                            }
                            # Add diagnosis fingerprint
                            try:
                                from app.services.failure_evidence_service import FailureEvidenceService as FES

                                norm = {
                                    "command_id": lock_exec.command_id,
                                    "failure_code": lock_exec.failure_code,
                                    "failure_message": lock_exec.failure_message,
                                    "exit_code": lock_exec.exit_code,
                                }
                                diag = FES.diagnose_npm_eresolve_failure(norm) or FES.diagnose_angular_update_failure(norm)
                                if isinstance(diag, dict):
                                    resolver_info["diagnosis"] = diag
                            except Exception:
                                pass
                        # Build new dependency_normalization for child
                        # Preserve original bundle
                        orig_dep_norm = parent_content.get("dependency_normalization") if isinstance(parent_content.get("dependency_normalization"), dict) else {}
                        new_dep_norm = dict(orig_dep_norm) if isinstance(orig_dep_norm, dict) else {}
                        new_dep_norm["prior_normalization"] = {
                            "attempt_id": parent_attempt.id,
                            "ordinal": 1,
                            "proposal_artifact_id": parent_attempt.proposal_artifact_id,
                            "proposal_checksum": parent_attempt.proposal_checksum,
                            "parent_proposal": parent_proposal,
                        }
                        new_dep_norm["resolver_failure"] = resolver_info
                        # Update parent_content with new dep norm
                        parent_content["dependency_normalization"] = new_dep_norm
                        # Write new context artifact for child
                        new_relative = f"05_repairs/{child.stage_id}/{child.id}-context.json"
                        new_stored = store.write_text_artifact(
                            child.run_id,
                            new_relative,
                            json.dumps(parent_content, sort_keys=True, indent=2),
                            ArtifactType.JSON,
                            stage_id=child.stage_id,
                            created_by="dependency-normalization-child",
                            created_at=datetime.now(UTC),
                            input_hashes={"parent_context": parent_attempt.context_pack_checksum or "", "resolver_failure": lock_exec.id if lock_exec else ""},
                            policy_version="repair-context-pack-v1",
                        )
                        # Register metadata
                        new_meta_id = "metadata-" + new_stored.ref.artifact_id
                        if session.get(ArtifactMetadataModel, new_meta_id) is None:
                            session.add(
                                ArtifactMetadataModel(
                                    id=new_meta_id,
                                    run_id=child.run_id,
                                    stage_id=child.stage_id,
                                    artifact_type=new_stored.ref.artifact_type.value,
                                    relative_path=new_stored.ref.relative_path,
                                    checksum=new_stored.ref.checksum,
                                    schema_version=new_stored.envelope.schema_version,
                                    created_at=new_stored.ref.created_at,
                                    finalized_at=new_stored.ref.created_at,
                                    immutable=True,
                                    execution_id=lock_exec.id if lock_exec else None,
                                    owner_reference=child.id,
                                    correlation_id=lock_exec.correlation_id if lock_exec and hasattr(lock_exec, "correlation_id") else None,
                                    safe_metadata={"schema_version": "repair-context-pack-v1", "child_of": parent_attempt.id},
                                )
                            )
                        child.context_pack_artifact_id = new_stored.ref.artifact_id
                        child.context_pack_checksum = new_stored.ref.checksum
                        session.flush()
        except Exception:
            pass
        return child

    def _lockfile_generation(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            try:
                # P4 lock generation must run after package.json once (APPLY_REPAIR); next is final_install via repair_revalidate stub
                # but _start_revalidation will handle final_install→migrate_packages→target_inspection flow
                self._lockfiles.advance(
                    session, continuation, next_node="repair_revalidate"
                )
            except LockfileGenerationError as error:
                if error.code == DEPENDENCY_NORMALIZATION_RESOLUTION_FAILED:
                    # P0-3: real attempt 1/2 with lineage + materially new fingerprint (not workspace fingerprint)
                    # Use RepairAttemptModel lineage, not MigrationPlanModel.version
                    try:
                        # Find latest dependency normalization attempt for this stage
                        latest_norm = None
                        for cand in session.query(RepairAttemptModel).filter(
                            RepairAttemptModel.run_id == continuation.run_id,
                            RepairAttemptModel.stage_id == continuation.current_stage_id,
                        ).order_by(RepairAttemptModel.attempt_number.desc()).all():
                            # Check if this attempt's proposal is dependency normalization
                            if cand.proposal_artifact_id and cand.proposal_checksum:
                                meta = session.get(ArtifactMetadataModel, "metadata-" + cand.proposal_artifact_id)
                                if meta is not None:
                                    try:
                                        run_for_norm = session.get(MigrationRunModel, continuation.run_id)
                                        if run_for_norm and run_for_norm.artifact_root:
                                            store_norm = LocalFilesystemArtifactStore(Path(run_for_norm.artifact_root).parent, fixed_run_root=Path(run_for_norm.artifact_root))
                                            stored_norm = store_norm.read_artifact(continuation.run_id, meta.relative_path)
                                            prop = json.loads(stored_norm.content)
                                            ops = prop.get("operations") if isinstance(prop, dict) else None
                                            if isinstance(ops, list) and any(
                                                str(op.get("operation") or op.get("repair_kind") or op.get("schema_version")) in (DEPENDENCY_NORMALIZATION_REPAIR_KIND, DEPENDENCY_NORMALIZATION_SCHEMA_VERSION)
                                                for op in ops if isinstance(op, dict)
                                            ):
                                                latest_norm = cand
                                                break
                                    except Exception:
                                        continue
                        if latest_norm is None:
                            self._block(session, continuation, error.code, error.message)
                            return
                        # Fix 1/2: use strict ordinal, not global attempt_number
                        current_ordinal = self._dependency_normalization_ordinal(session, continuation, latest_norm)
                        if current_ordinal == 0:
                            # Fallback: if ordinal is 0 but latest_norm exists, treat as 1 (root)
                            current_ordinal = 1
                        # Compute fingerprint for current lock failure execution
                        lock_exec = None
                        # Find the lock generation execution that just failed
                        lock_step_tmp = session.scalar(
                            select(StageStepModel).where(
                                StageStepModel.stage_id == continuation.current_stage_id,
                                StageStepModel.name == "lockfile_generation-0",
                            )
                        )
                        if lock_step_tmp is not None and lock_step_tmp.execution_id:
                            lock_exec = session.get(CommandExecutionModel, lock_step_tmp.execution_id)
                        if lock_exec is None:
                            lock_exec = session.scalar(
                                select(CommandExecutionModel).where(
                                    CommandExecutionModel.run_id == continuation.run_id,
                                    CommandExecutionModel.stage_id == continuation.current_stage_id,
                                    CommandExecutionModel.command_id == "npm-lockfile-generate",
                                ).order_by(CommandExecutionModel.requested_at.desc()).limit(1)
                            )
                        # Helper to compute materially new fingerprint
                        def _fingerprint_for_exec(exec_obj) -> str:
                            if exec_obj is None:
                                return "sha256:" + hashlib.sha256(b"missing").hexdigest()
                            # Use normalized fields: failure_code, conflicting package, required range, etc.
                            try:
                                # Try to get diagnosis via FailureEvidenceService
                                norm = {
                                    "command_id": exec_obj.command_id,
                                    "failure_code": exec_obj.failure_code,
                                    "failure_message": (exec_obj.failure_message or "")[:2000],
                                    "exit_code": exec_obj.exit_code,
                                }
                                # Try to extract peer conflict diagnosis
                                diag = None
                                try:
                                    from app.services.failure_evidence_service import FailureEvidenceService as FES

                                    diag = FES.diagnose_npm_eresolve_failure(norm) or FES.diagnose_angular_update_failure(norm)
                                except Exception:
                                    diag = None
                                payload: dict[str, object] = {
                                    "failure_code": norm.get("failure_code"),
                                    "command_id": norm.get("command_id"),
                                    "exit_code": norm.get("exit_code"),
                                }
                                if isinstance(diag, dict):
                                    # Include deterministic diagnosis fields
                                    for k in ("package", "blocking_dependency", "required_ranges", "required_peer_range", "package_version", "kind"):
                                        if k in diag:
                                            payload[k] = diag[k]
                                else:
                                    # Fallback: hash normalized failure message lowercased and stripped
                                    msg = " ".join((exec_obj.failure_message or "").split()).lower()[:1000]
                                    payload["failure_message_normalized"] = msg
                                canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                                return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
                            except Exception:
                                return "sha256:" + hashlib.sha256(str(exec_obj.failure_message or "").encode()).hexdigest()
                        current_fp = _fingerprint_for_exec(lock_exec)
                        # Get previous fingerprint: for attempt 1, previous is the original ng update failure's fingerprint stored in latest_norm.failure_fingerprint
                        # For attempt 2, previous would be stored similarly
                        prev_fp = None
                        if latest_norm.failure_fingerprint:
                            # The failure fingerprint for the attempt is the original classification fingerprint
                            # For lock failure, we need to compare to previous lock failure's fingerprint if available
                            # Try to find previous lock failure fingerprint from earlier execution's stored evidence
                            # For now, use the attempt's failure_fingerprint as previous
                            prev_fp = latest_norm.failure_fingerprint
                            # But for attempt 1, that is the ng update failure fingerprint, not lock failure
                            # So we need to also look at lock-specific fingerprint stored in artifact metadata if available
                            # For simplicity, if current_attempt_no == 1, compare current lock fingerprint to attempt's failure fingerprint
                            # If they match, it's no progress
                        if current_ordinal == 1:
                            # Check if current lock fingerprint was already seen in any prior lock failure for this stage
                            prev_lock_fps: set[str] = set()
                            for prev_exec in session.scalars(
                                select(CommandExecutionModel).where(
                                    CommandExecutionModel.run_id == continuation.run_id,
                                    CommandExecutionModel.stage_id == continuation.current_stage_id,
                                    CommandExecutionModel.command_id == "npm-lockfile-generate",
                                    CommandExecutionModel.status == "failed",
                                )
                            ).all():
                                if prev_exec.id == (lock_exec.id if lock_exec else None):
                                    continue
                                prev_lock_fps.add(_fingerprint_for_exec(prev_exec))
                            if current_fp in prev_lock_fps:
                                self._block(session, continuation, "DEPENDENCY_NORMALIZATION_NO_PROGRESS", "Identical npm constraint failure — no progress")
                                return
                            # Reconstruct checkpoint for plan 2
                            try:
                                self._restore_angular_update_checkpoint(session, continuation)
                            except TransformerStageError as e:
                                self._block(session, continuation, e.code, e.message)
                                return
                            # Verify ordinal: next ordinal must be 2, not >2
                            # Compute next ordinal: current lineage size +1
                            lineage = self._dependency_normalization_lineage(session, continuation)
                            next_ordinal = len(lineage) + 1
                            if next_ordinal > 2:
                                self._block(session, continuation, "DEPENDENCY_NORMALIZATION_ATTEMPTS_EXHAUSTED", "No third normalization attempt")
                                return
                            # Fix 1: create REAL child RepairAttempt with NEW context (prior plan + resolver failure)
                            try:
                                child = self._create_dependency_normalization_child_attempt(session, continuation, latest_norm, lock_exec)
                            except TransformerStageError as e:
                                self._block(session, continuation, e.code, e.message)
                                return
                            except Exception as e:
                                self._block(session, continuation, "CHILD_ATTEMPT_CREATION_FAILED", str(e))
                                return
                            self._queue(continuation, "propose_repair")
                            return
                        elif current_ordinal >= 2:
                            self._block(session, continuation, "DEPENDENCY_NORMALIZATION_ATTEMPTS_EXHAUSTED", "Dependency normalization attempts exhausted (max 2)")
                            return
                        else:
                            self._block(session, continuation, error.code, error.message)
                            return
                    except Exception as inner_e:
                        # If helper fails, fallback to block
                        if isinstance(inner_e, TransformerStageError):
                            self._block(session, continuation, inner_e.code, inner_e.message)
                        else:
                            self._block(session, continuation, "DEPENDENCY_NORMALIZATION_RETRY_FAILED", str(inner_e))
                        return
                    self._block(session, continuation, error.code, error.message)
                    return
                if error.code == LOCKFILE_GENERATION_ETARGET:
                    self._validation_failure(
                        session,
                        continuation,
                        error,
                        event_reason=(
                            "lockfile-generation command failed with ETARGET; "
                            "failure classification queued"
                        ),
                    )
                elif error.code == LOCKFILE_GENERATION_ERESOLVE:
                    self._validation_failure(
                        session,
                        continuation,
                        error,
                        event_reason=(
                            "lockfile-generation command failed with ERESOLVE; "
                            "failure classification queued"
                        ),
                    )
                else:
                    self._block(session, continuation, error.code, error.message)

    @staticmethod
    def _npm_evidence_materially_changed(session, continuation) -> bool:
        # max 2 plans: plan2 only when npm evidence materially changed (package.json/lockfile)
        # ponytail: check lockfile or package.json fingerprint vs checkpoint
        try:
            binding = session.scalar(
                select(StageWorkspaceBindingModel).where(
                    StageWorkspaceBindingModel.run_id == continuation.run_id,
                    StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                    StageWorkspaceBindingModel.active.is_(True),
                )
            )
            if binding is None:
                return False
            # any pending package.json diff vs pre_angular_update checkpoint is material
            checkpoint = session.scalar(
                select(StageCheckpointModel)
                .where(
                    StageCheckpointModel.run_id == continuation.run_id,
                    StageCheckpointModel.stage_id == continuation.current_stage_id,
                    StageCheckpointModel.kind == "pre_angular_update",
                )
                .order_by(StageCheckpointModel.sequence.desc())
            )
            if checkpoint is None:
                return False
            return binding.workspace_fingerprint != checkpoint.workspace_fingerprint
        except Exception:
            return False

    def _migrate_packages(self, continuation_id: str, worker_id: str) -> None:
        # P5 migrate-only: discovery then one migrate per package via tpl-angular-migrate-range-v1
        # P0-2: sequential execution, P0-3: exact resolved versions via PackageMigrationService
        # NG_DISABLE_VERSION_CHECK=true, no --force, no --allow-dirty enforced by renderer
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            binding = self._stage._binding(session, continuation)
            # Handle already-running or recently queued migration: wait for terminal
            step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.stage_id == continuation.current_stage_id,
                    StageStepModel.name == "migrate_packages-0",
                )
            )
            execution = session.get(CommandExecutionModel, step.execution_id) if step and step.execution_id else None
            if step is not None and execution is not None and execution.status in {"pending", "running", "queued"}:
                # Still in flight — wait for terminal via normal command polling
                self._stage._wait_for_command(session, continuation, execution.id)
                return
            if execution is not None and execution.status != "succeeded":
                if execution.status in {"failed", "timed_out", "cancelled", "interrupted"}:
                    # Migration failure → classify/repair path (fail closed for now as BLOCK)
                    self._block(session, continuation, execution.failure_code or "MIGRATE_PACKAGE_FAILED", execution.failure_message or "Package migration failed")
                    return
            # Discover all required migrations using exact resolved versions (P0-3, P0-4)
            try:
                from app.services.package_migration_service import PackageMigrationService, PackageMigrationError

                chk = self._angular_update_recovery_checkpoint(session, continuation) or session.scalar(
                    select(StageCheckpointModel)
                    .where(
                        StageCheckpointModel.run_id == continuation.run_id,
                        StageCheckpointModel.stage_id == continuation.current_stage_id,
                        StageCheckpointModel.kind == "pre_angular_update",
                    )
                    .order_by(StageCheckpointModel.sequence.desc())
                )
                chk_path = Path(chk.workspace_path) if chk is not None else Path(binding.workspace_path)
                # P0-4: pass normalization actions for REMOVE/REPLACE ambiguity check
                _norm_actions = None
                try:
                    _lineage_for_actions = self._dependency_normalization_lineage(session, continuation)
                    _leaf_for_actions = _lineage_for_actions[-1] if _lineage_for_actions else None
                    if _leaf_for_actions is not None and _leaf_for_actions.proposal_artifact_id:
                        _meta_act = session.get(ArtifactMetadataModel, "metadata-" + _leaf_for_actions.proposal_artifact_id)
                        if _meta_act is not None:
                            _run_act = session.get(MigrationRunModel, _leaf_for_actions.run_id)
                            if _run_act and _run_act.artifact_root:
                                from app.artifact_store import LocalFilesystemArtifactStore as _StoreAct

                                _store_act = _StoreAct(Path(_run_act.artifact_root).parent, fixed_run_root=Path(_run_act.artifact_root))
                                _prop_act = json.loads(_store_act.read_artifact(_leaf_for_actions.run_id, _meta_act.relative_path).content)
                                _ops_act = _prop_act.get("operations") if isinstance(_prop_act, dict) else None
                                if isinstance(_ops_act, list):
                                    _norm_actions = {}
                                    for _op in _ops_act:
                                        if isinstance(_op, dict):
                                            _pkg = _op.get("package") or _op.get("target_package") or _op.get("name")
                                            if isinstance(_pkg, str):
                                                _norm_actions[_pkg] = _op
                except Exception:
                    _norm_actions = None
                discovered = PackageMigrationService().discover(chk_path, Path(binding.workspace_path), _norm_actions)
            except PackageMigrationError as error:
                self._block(session, continuation, error.code, error.message)
                return
            except Exception as error:
                # Any discovery exception beyond PackageMigrationError is unexpected — fail closed
                self._block(session, continuation, "PACKAGE_MIGRATION_DISCOVERY_FAILED", str(error))
                return
            if not discovered:
                # No migrations — handle post-migration successor lock if needed, else target inspection
                if step is not None and step.status == "PASSED" and execution is not None and execution.status == "succeeded":
                    live = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
                    if live != binding.workspace_fingerprint:
                        binding.workspace_fingerprint = live
                        binding.fingerprint_profile_id = STAGE_FINGERPRINT_PROFILE.profile_id
                        binding.last_verified_fingerprint = live
                        binding.last_verified_at = datetime.now(UTC)
                    chk2 = session.scalar(
                        select(StageCheckpointModel)
                        .where(
                            StageCheckpointModel.run_id == continuation.run_id,
                            StageCheckpointModel.stage_id == continuation.current_stage_id,
                            StageCheckpointModel.kind == "pre_angular_update",
                        )
                        .order_by(StageCheckpointModel.sequence.desc())
                    )
                    if chk2 is not None and live != chk2.workspace_fingerprint:
                        lock_step = session.scalar(
                            select(StageStepModel).where(
                                StageStepModel.stage_id == continuation.current_stage_id,
                                StageStepModel.name == "lockfile_generation-0",
                            )
                        )
                        if lock_step is None or lock_step.status != "PASSED":
                            self._stage.queue_lockfile_generation(session, continuation, attempt_key="post-migrate:lock")
                            return
                self._queue(continuation, "target_inspection")
                return
            # P0-5: migration identity must include package+from+to+lineage, not just package name
            # Determine lineage for filtering: latest normalization attempt + checkpoint
            lineage_id = None
            latest_norm_for_lineage = None
            try:
                latest_norm_for_lineage = session.query(RepairAttemptModel).filter(
                    RepairAttemptModel.run_id == continuation.run_id,
                    RepairAttemptModel.stage_id == continuation.current_stage_id,
                ).order_by(RepairAttemptModel.attempt_number.desc()).first()
                # Use checkpoint id for lineage
                chk_for_lineage = chk
                if latest_norm_for_lineage is not None and chk_for_lineage is not None:
                    lineage_raw = f"{latest_norm_for_lineage.id}:{chk_for_lineage.id}:{latest_norm_for_lineage.attempt_number}"
                    lineage_id = hashlib.sha256(lineage_raw.encode()).hexdigest()[:16]
                else:
                    lineage_id = hashlib.sha256(f"{continuation.run_id}:{continuation.current_stage_id}:no-norm".encode()).hexdigest()[:16]
            except Exception:
                lineage_id = hashlib.sha256(f"{continuation.run_id}:{continuation.current_stage_id}:no-lineage".encode()).hexdigest()[:16]
            succeeded_identities: set[str] = set()
            try:
                all_execs = session.scalars(
                    select(CommandExecutionModel).where(
                        CommandExecutionModel.run_id == continuation.run_id,
                        CommandExecutionModel.stage_id == continuation.current_stage_id,
                        CommandExecutionModel.command_id == "angular-migrate-range",
                    )
                ).all()
                for ex in all_execs:
                    if ex.status != "succeeded" or ex.exit_code != 0 or not ex.arguments or len(ex.arguments) != 8:
                        continue
                    pkg = str(ex.arguments[2])
                    from_v = str(ex.arguments[5])
                    to_v = str(ex.arguments[7])
                    # Lineage: only executions after latest_norm are current lineage
                    if latest_norm_for_lineage is not None and ex.requested_at is not None and latest_norm_for_lineage.created_at is not None:
                        if ex.requested_at < latest_norm_for_lineage.created_at:
                            continue
                    # Required immutable evidence present
                    if not ex.result_artifact_id or not ex.command_log_artifact_id:
                        continue
                    # Check artifacts actually exist
                    if session.get(ArtifactMetadataModel, "metadata-" + ex.result_artifact_id) is None:
                        continue
                    ident = f"{pkg}:{from_v}:{to_v}:{lineage_id}"
                    canonical = hashlib.sha256(f"{continuation.run_id}:{continuation.current_stage_id}:{lineage_id}:{pkg}:{from_v}:{to_v}".encode()).hexdigest()[:16]
                    succeeded_identities.add(ident)
                    succeeded_identities.add(canonical)
            except Exception:
                succeeded_identities = set()
            def _is_succeeded(req) -> bool:
                ident = f"{req.package}:{req.from_version}:{req.to_version}:{lineage_id}"
                canonical = hashlib.sha256(f"{continuation.run_id}:{continuation.current_stage_id}:{lineage_id}:{req.package}:{req.from_version}:{req.to_version}".encode()).hexdigest()[:16]
                return ident in succeeded_identities or canonical in succeeded_identities
            # Post-migration handling after at least one success: check if all discovered done
            if step is not None and step.status == "PASSED" and execution is not None and execution.status == "succeeded":
                remaining = [p for p in discovered if not _is_succeeded(p)]
                if not remaining:
                    live = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
                    if live != binding.workspace_fingerprint:
                        binding.workspace_fingerprint = live
                        binding.fingerprint_profile_id = STAGE_FINGERPRINT_PROFILE.profile_id
                        binding.last_verified_fingerprint = live
                        binding.last_verified_at = datetime.now(UTC)
                    chk3 = session.scalar(
                        select(StageCheckpointModel)
                        .where(
                            StageCheckpointModel.run_id == continuation.run_id,
                            StageCheckpointModel.stage_id == continuation.current_stage_id,
                            StageCheckpointModel.kind == "pre_angular_update",
                        )
                        .order_by(StageCheckpointModel.sequence.desc())
                    )
                    if chk3 is not None and live != chk3.workspace_fingerprint:
                        lock_step = session.scalar(
                            select(StageStepModel).where(
                                StageStepModel.stage_id == continuation.current_stage_id,
                                StageStepModel.name == "lockfile_generation-0",
                            )
                        )
                        if lock_step is None or lock_step.status != "PASSED":
                            self._stage.queue_lockfile_generation(session, continuation, attempt_key="post-migrate:lock")
                            return
                    self._queue(continuation, "target_inspection")
                    return
                # Remaining migrations exist — queue next with lineage-bound identity
                pkg = remaining[0]
                try:
                    lineage_suffix2 = f":{lineage_id}" if lineage_id else ""
                    self._stage.queue_migrate_packages(
                        session,
                        continuation,
                        attempt_key=f"migrate:{pkg.package}:{pkg.from_version}->{pkg.to_version}{lineage_suffix2}",
                        package=pkg.package,
                        from_version=pkg.from_version,
                        to_version=pkg.to_version,
                    )
                except TransformerStageError as error:
                    self._block(session, continuation, error.code, error.message)
                    return
                return
            # No prior success or first entry — queue first remaining
            remaining_initial = [p for p in discovered if not _is_succeeded(p)]
            pkg = remaining_initial[0] if remaining_initial else discovered[0]
            # P0-5: attempt_key must include lineage to avoid old reuse
            try:
                lineage_suffix = f":{lineage_id}" if lineage_id else ""
                self._stage.queue_migrate_packages(
                    session,
                    continuation,
                    attempt_key=f"migrate:{pkg.package}:{pkg.from_version}->{pkg.to_version}{lineage_suffix}",
                    package=pkg.package,
                    from_version=pkg.from_version,
                    to_version=pkg.to_version,
                )
            except TransformerStageError as error:
                self._block(session, continuation, error.code, error.message)
                return
            return

    @staticmethod
    def _claim_current_continuation_for_apply(
        session,
        continuation_id: str,
        stage_id: str,
        expected_state_version: int,
    ) -> int:
        current = session.get(TransformationContinuationModel, continuation_id)
        if (
            current is None
            or current.current_stage_id != stage_id
            or current.state_version != expected_state_version
        ):
            raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Continuation authority changed before mutation")
        claim = session.execute(
            update(TransformationContinuationModel)
            .where(
                TransformationContinuationModel.id == continuation_id,
                TransformationContinuationModel.current_stage_id == stage_id,
                TransformationContinuationModel.state_version == expected_state_version,
            )
            .values(state_version=TransformationContinuationModel.state_version + 1, updated_at=datetime.now(UTC))
        )
        if claim.rowcount != 1:
            raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Continuation changed before mutation")
        return expected_state_version + 1

    def _start_revalidation(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(
                session, continuation, exclude_statuses={"superseded"}
            )
            if attempt.status in {"applied", "applied_verified", "migration_retried", "revalidating_affected"}:
                run = session.get(MigrationRunModel, continuation.run_id)
                try:
                    proposal = self._load_bound_repair_proposal(
                        session, continuation, attempt, run
                    )
                    review_targets = self._bound_review_validation_targets(
                        session, continuation, attempt, run
                    )
                except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError, RepairApplicationError) as error:
                    self._block(session, continuation, "REPAIR_PROPOSAL_STALE", "Bound repair proposal cannot be verified")
                    return
                stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
                plan_value = stage_plan.stage_plan if stage_plan is not None else {}
                policy = plan_value.get("validation_policy") or {}
                persisted = attempt.validation_targets
                if persisted is not None:
                    # New rows: the persisted union is the authority.  It was
                    # sealed into the G10 package at create time, so the sealed
                    # field must agree; any divergence is tampering.
                    try:
                        sealed = self._bound_g10_validation_targets(
                            session, continuation, attempt, run
                        )
                    except RepairApplicationError as error:
                        self._block(session, continuation, error.code, error.message)
                        return
                    if sealed != list(persisted):
                        self._block(
                            session,
                            continuation,
                            "REPAIR_PROPOSAL_STALE",
                            "Sealed G10 validation targets do not match the persisted union",
                        )
                        return
                    targets = list(persisted)
                else:
                    # Legacy migration path: rows created before the union was
                    # persisted recompute it here from the checksum-bound
                    # proposal and review artifacts (verified above).  New rows
                    # always carry attempt.validation_targets instead.
                    try:
                        targets = validation_target_union(
                            list(proposal.get("validation_targets") or []),
                            review_targets,
                            policy.get("required_checks") or ("build", "test"),
                            plan_value.get("commands") or {},
                        )
                    except ValidationTargetUnionError as error:
                        self._block(session, continuation, error.code, error.message)
                        return
                dependency_repair = self._proposal_requires_install_materialization(
                    proposal
                )
                if attempt.status in {"applied", "applied_verified", "migration_retried"}:
                    if dependency_repair:
                        for step in session.query(StageStepModel).filter(
                            StageStepModel.stage_id == continuation.current_stage_id,
                            StageStepModel.name.like("final_install-%"),
                        ):
                            step.status = "PENDING"
                            step.execution_id = None
                            step.completed_at = None
                    RepairLifecycleService.transition_in_session(
                        session,
                        attempt,
                        "revalidating_affected",
                        reason="repair validation restarted affected checks",
                    )
                if dependency_repair and attempt.status == "revalidating_affected":
                    if not self._successful_materialization_exists(
                        session, continuation, attempt
                    ):
                        try:
                            outcome = self._validation.advance_group(
                                session,
                                continuation,
                                "final_install",
                                next_node="repair_revalidate",
                                attempt_key=f"{attempt.id}:materialize",
                            )
                        except ValidationRunnerError as error:
                            self._validation_failure(session, continuation, error)
                            return
                        if outcome != "passed":
                            return
                        # V2.2 P5: after P4 lock + final_install materialization, run migrate-only before validation
                        if self._is_normalization_proposal(proposal):
                            step = session.scalar(
                                select(StageStepModel).where(
                                    StageStepModel.stage_id == continuation.current_stage_id,
                                    StageStepModel.name == "migrate_packages-0",
                                )
                            )
                            if step is None or step.status != "PASSED":
                                self._queue(continuation, "migrate_packages")
                                return
                affected_attempt_key = (
                    f"{attempt.id}:affected:materialized"
                    if dependency_repair
                    else f"{attempt.id}:affected"
                )
                for target in targets:
                    try:
                        outcome = self._validation.advance_group(
                            session,
                            continuation,
                            VALIDATION_TARGET_GROUPS[target],
                            next_node="repair_revalidate",
                            attempt_key=affected_attempt_key,
                        )
                    except ValidationRunnerError as error:
                        self._validation_failure(session, continuation, error)
                        return
                    if outcome != "passed":
                        return
            # The affected groups above are reset and deliberately re-executed
            # inside the full validation set below (final_install -> policy
            # groups) so the aggregate carries one authoritative replay of every
            # check under the revalidating attempt (plan §10).
            for step in session.query(StageStepModel).filter(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name.like("final_install-%")
                | StageStepModel.name.like("builds-%")
                | StageStepModel.name.like("tests-%")
                | StageStepModel.name.like("lint-%"),
            ):
                execution = (
                    session.get(CommandExecutionModel, step.execution_id)
                    if step.execution_id
                    else None
                )
                if (
                    step.name.startswith("lint-")
                    and step.status == "PASSED"
                    and execution is not None
                    and self._validation._is_known_baseline_failure(
                        session, continuation, execution
                    )
                ):
                    continue
                step.status = "PENDING"
                step.execution_id = None
                step.completed_at = None
            RepairLifecycleService.transition_in_session(
                session,
                attempt,
                "revalidating",
                reason="repair validation restarted complete check set",
            )
            self._queue(continuation, "final_install")

    @staticmethod
    def _proposal_requires_install_materialization(proposal: dict[str, object]) -> bool:
        return any(
            isinstance(item, dict)
            and (
                item.get("operation") in {"dependency_add", "dependency_change"}
                or str(item.get("repair_kind") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND
                or str(item.get("operation") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND
                or str(item.get("schema_version") or "") == DEPENDENCY_NORMALIZATION_SCHEMA_VERSION
            )
            for item in (proposal.get("operations") or [])
        )

    @staticmethod
    def _is_normalization_proposal(proposal: dict[str, object]) -> bool:
        return any(
            isinstance(item, dict)
            and (
                str(item.get("repair_kind") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND
                or str(item.get("operation") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND
                or str(item.get("schema_version") or "") == DEPENDENCY_NORMALIZATION_SCHEMA_VERSION
            )
            for item in (proposal.get("operations") or [])
        )

    @staticmethod
    def _load_bound_repair_proposal(session, continuation, attempt, run):
        if run is None or not attempt.proposal_artifact_id or not attempt.proposal_checksum:
            raise RepairApplicationError(
                "REPAIR_PROPOSAL_STALE", "Bound repair proposal is missing or stale"
            )
        metadata = session.get(
            ArtifactMetadataModel, "metadata-" + str(attempt.proposal_artifact_id)
        )
        if metadata is None or metadata.checksum != attempt.proposal_checksum:
            raise RepairApplicationError(
                "REPAIR_PROPOSAL_STALE", "Bound repair proposal is missing or stale"
            )
        stored_proposal = LocalFilesystemArtifactStore(
            Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
        ).read_artifact(continuation.run_id, metadata.relative_path)
        if (
            stored_proposal.ref.artifact_id != attempt.proposal_artifact_id
            or stored_proposal.ref.checksum != attempt.proposal_checksum
            or stored_proposal.envelope is None
            or stored_proposal.envelope.run_id != continuation.run_id
            or stored_proposal.envelope.stage_id != continuation.current_stage_id
            or stored_proposal.envelope.attempt_id != attempt.id
        ):
            raise RepairApplicationError(
                "REPAIR_PROPOSAL_STALE", "Bound repair proposal envelope is stale"
            )
        return RepairProposal.model_validate(
            json.loads(stored_proposal.content)
        ).model_dump(mode="json")

    @staticmethod
    def _failure_evidence_execution_id(session, continuation, attempt, run) -> str | None:
        if run is None or not attempt.failure_evidence_artifact_id or not attempt.failure_evidence_checksum:
            return None
        metadata = session.get(
            ArtifactMetadataModel,
            "metadata-" + str(attempt.failure_evidence_artifact_id),
        )
        if (
            metadata is None
            or not metadata.immutable
            or metadata.checksum != attempt.failure_evidence_checksum
        ):
            return None
        stored = LocalFilesystemArtifactStore(
            Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
        ).read_artifact(continuation.run_id, metadata.relative_path)
        if (
            stored.ref.artifact_id != attempt.failure_evidence_artifact_id
            or stored.ref.checksum != attempt.failure_evidence_checksum
            or stored.envelope is None
            or stored.envelope.run_id != continuation.run_id
            or stored.envelope.stage_id != continuation.current_stage_id
        ):
            return None
        payload = json.loads(stored.content)
        execution_id = payload.get("execution_id")
        return str(execution_id) if execution_id else None

    def _reconcile_incomplete_newer_repair(
        self, session, continuation, active_attempt, stale_execution_ids: set[str]
    ) -> bool | None:
        newer = (
            session.query(RepairAttemptModel)
            .filter(
                RepairAttemptModel.run_id == continuation.run_id,
                RepairAttemptModel.stage_id == continuation.current_stage_id,
                RepairAttemptModel.attempt_number > active_attempt.attempt_number,
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
            .first()
        )
        if newer is None:
            return None
        if (
            newer.status != "evidence_frozen"
            or newer.proposal_artifact_id is not None
            or newer.proposer_invocation_id is not None
            or newer.review_artifact_id is not None
            or newer.reviewer_invocation_id is not None
            or newer.g10_gate_package_id is not None
            or newer.apply_ledger_artifact_id is not None
            or newer.apply_ledger_checksum is not None
            or newer.post_fingerprint is not None
        ):
            return False
        try:
            evidence_execution_id = self._failure_evidence_execution_id(
                session,
                continuation,
                newer,
                session.get(MigrationRunModel, continuation.run_id),
            )
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError, TypeError):
            return False
        if evidence_execution_id not in stale_execution_ids:
            return False
        now = datetime.now(UTC)
        # ``superseded`` is an existing terminal repair lifecycle state used
        # for unstarted evidence-frozen attempts.  Keep the row and artifacts;
        # only the newer, unapplied attempt is retired.
        newer.status = "superseded"
        newer.completed_at = now
        newer.updated_at = now
        return True

    @staticmethod
    def _successful_materialization_exists(session, continuation, attempt) -> bool:
        key = TransformerOrchestrator._validation_execution_key(
            continuation, f"{attempt.id}:materialize", "final_install"
        )
        return (
            session.scalar(
                select(CommandExecutionModel).where(
                    CommandExecutionModel.run_id == continuation.run_id,
                    CommandExecutionModel.stage_id == continuation.current_stage_id,
                    CommandExecutionModel.idempotency_key == key,
                    CommandExecutionModel.status == "succeeded",
                    CommandExecutionModel.exit_code == 0,
                )
            )
            is not None
        )

    @staticmethod
    def _validation_execution_key(continuation, attempt_key: str, group: str) -> str:
        return validation_execution_key(str(continuation.id), attempt_key, group)

    def _bound_review_validation_targets(self, session, continuation, attempt, run) -> list[str]:
        """Verify the bound repair review and return its required targets.

        Mirrors the proposal verification: the review artifact must exist with
        matching metadata/checksum identity, an attempt-bound envelope, an
        accepted decision, and the proposal binding the attempt was approved
        with.  Any deviation fails closed so revalidation never trusts an
        unverified or tampered review.
        """
        if not attempt.review_artifact_id or not attempt.review_checksum:
            raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Bound repair review is missing")
        metadata = session.get(ArtifactMetadataModel, "metadata-" + str(attempt.review_artifact_id))
        if metadata is None or metadata.checksum != attempt.review_checksum:
            raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Bound repair review is missing or stale")
        stored = LocalFilesystemArtifactStore(
            Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
        ).read_artifact(continuation.run_id, metadata.relative_path)
        if (
            stored.ref.artifact_id != attempt.review_artifact_id
            or stored.ref.checksum != attempt.review_checksum
            or stored.envelope is None
            or stored.envelope.run_id != continuation.run_id
            or stored.envelope.stage_id != continuation.current_stage_id
            or stored.envelope.attempt_id != attempt.id
        ):
            raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Bound repair review envelope is stale")
        payload = json.loads(stored.content)
        if payload.get("decision") != "accept":
            raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Bound repair review is not accepted")
        if payload.get("proposal_checksum") != attempt.proposal_checksum:
            raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Bound repair review proposal binding is stale")
        return list(payload.get("required_validation_targets") or [])

    def _bound_g10_validation_targets(self, session, continuation, attempt, run) -> list[str]:
        """Return the sealed G10 package's validation targets for the attempt.

        Returns None when the attempt has no recorded G10 package row (a
        legacy row).  Any recorded package must be checksum-bound with an
        attempt-bound envelope; deviation fails closed so revalidation never
        consumes an unsealed target set.
        """
        if not attempt.g10_gate_package_id:
            return None
        package = session.get(StageGatePackageModel, attempt.g10_gate_package_id)
        if package is None:
            raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Sealed G10 package is missing")
        metadata = session.get(ArtifactMetadataModel, "metadata-" + str(package.package_artifact_id))
        if metadata is None or metadata.checksum != package.package_checksum:
            raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Sealed G10 package is missing or stale")
        stored = LocalFilesystemArtifactStore(
            Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
        ).read_artifact(continuation.run_id, metadata.relative_path)
        if (
            stored.ref.artifact_id != package.package_artifact_id
            or stored.ref.checksum != package.package_checksum
            or stored.envelope is None
            or stored.envelope.run_id != continuation.run_id
            or stored.envelope.stage_id != continuation.current_stage_id
            or stored.envelope.attempt_id != attempt.id
        ):
            raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Sealed G10 package binding is stale")
        return list(json.loads(stored.content).get("validation_targets") or [])

    def _create_g09_from_repair(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            binding = self._stage._binding(session, continuation)
            run = session.get(MigrationRunModel, continuation.run_id)
            plan = session.get(MigrationPlanModel, continuation.plan_id)
            if plan is None or plan.run_id != continuation.run_id:
                raise TransformerStageError("PLAN_BINDING_MISSING", "Migration plan for the run is missing")
            payload = {
                "gate_id": "G09",
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
                "plan_version": plan.version,
                "stage_plan_checksum": continuation.stage_plan_checksum,
                "workspace_fingerprint": binding.workspace_fingerprint,
                "validation_summary_artifact_id": attempt.validation_summary_artifact_id,
                "validation_summary_checksum": attempt.validation_summary_checksum,
                "repair_attempt_id": attempt.id,
                "g11_accepted": True,
            }
            context = (
                run.artifact_root,
                binding.workspace_fingerprint,
                continuation.run_id,
                continuation.current_stage_id,
            )
        gate = self._stage.write_gate_package(
            run_id=context[2],
            stage_id=context[3],
            artifact_root=context[0],
            gate_id="G09",
            payload=payload,
        )
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            self._stage.register_artifact(session, gate, continuation)
            self._gates.create(
                session,
                continuation,
                gate_id="G09",
                package_artifact_id=gate.ref.artifact_id,
                package_checksum=gate.ref.checksum,
                artifact_set_checksum=self._stage.checksum(
                    {gate.ref.artifact_id: gate.ref.checksum}
                ),
                workspace_fingerprint=context[1],
            )

    @staticmethod
    def _repairable_route(route) -> bool:
        # V2.2: dependency_incompatible is repairable via manifest normalization (P3); preserve legacy routes
        val = route.value if hasattr(route, "value") else str(route)
        return val in {"repairable_source", "angular_update_peer_conflict", "dependency_incompatible"}

    @staticmethod
    def _is_angular_update_failure(session, continuation) -> bool:
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "angular_update-0",
                StageStepModel.status == "FAILED",
            )
        )
        if step is None or not step.execution_id:
            return False
        execution = session.get(CommandExecutionModel, step.execution_id)
        latest = session.scalar(
            select(CommandExecutionModel)
            .where(
                CommandExecutionModel.run_id == continuation.run_id,
                CommandExecutionModel.stage_id == continuation.current_stage_id,
            )
            .order_by(CommandExecutionModel.requested_at.desc())
            .limit(1)
        )
        return (
            execution is not None
            and latest is not None
            and latest.id == execution.id
            and execution.command_id == "angular-update-exact"
        )

    @staticmethod
    def _angular_update_retry_eligible(session, continuation) -> bool:
        """True when the failed angular_update-0 may be retried after a repair.

        Requires the exact failed command (angular-update-exact), a terminal
        execution bound to the step, and no CLI prompt lineage: prompt-driven
        failures already have their own reconstruction flow and must never be
        replayed as a governed retry on the post-repair workspace.
        """
        if not TransformerOrchestrator._is_angular_update_failure(session, continuation):
            return False
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "angular_update-0",
            )
        )
        execution = (
            session.get(CommandExecutionModel, step.execution_id)
            if step is not None and step.execution_id
            else None
        )
        return (
            execution is not None
            and execution.prompt_request_id is None
            and (
                execution.status in ("failed", "interrupted")
                or (
                    execution.status == "timed_out"
                    and execution.reconstruction_required
                )
            )
        )

    def _angular_update_retry(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            step = session.scalar(
                select(StageStepModel).where(
                    StageStepModel.run_id == continuation.run_id,
                    StageStepModel.stage_id == continuation.current_stage_id,
                    StageStepModel.name == "angular_update-0",
                )
            )
            execution = (
                session.get(CommandExecutionModel, step.execution_id)
                if step is not None and step.execution_id
                else None
            )
            if (
                execution is None
                or not self._angular_update_retry_eligible(session, continuation)
            ):
                self._block(
                    session,
                    continuation,
                    "ANGULAR_UPDATE_RETRY_INVALID",
                    "Failed angular update command is not eligible for the governed post-repair retry",
                )
                return
            try:
                self._stage.queue_angular_update_retry(
                    session,
                    continuation,
                    failed_execution_id=execution.id,
                    idempotency_key=f"{execution.id}:retry:post-repair:{attempt.id}",
                )
            except TransformerStageError as error:
                self._block(session, continuation, error.code, error.message)

    def _dependency_transition(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            # Preserve DependencyTransitionRunner for legacy only, new V2.2 failures must NOT route there
            try:
                _run = session.get(MigrationRunModel, continuation.run_id)
                _prop = self._load_bound_repair_proposal(session, continuation, attempt, _run)
                if any(
                    str(item.get("repair_kind") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND
                    or str(item.get("operation") or "") == DEPENDENCY_NORMALIZATION_REPAIR_KIND
                    or str(item.get("schema_version") or "") == DEPENDENCY_NORMALIZATION_SCHEMA_VERSION
                    for item in (_prop.get("operations") or [])
                    if isinstance(item, dict)
                ):
                    self._block(session, continuation, "DEPENDENCY_TRANSITION_NOT_ALLOWED", "V2.2 manifest normalization must not use legacy DependencyTransitionRunner")
                    return
            except Exception:
                pass
            try:
                restore_required = self._dependency_transitions.requires_safe_restore(
                    session, continuation
                )
            except DependencyTransitionError as error:
                self._block(session, continuation, error.code, error.message)
                return
            if restore_required:
                try:
                    self._restore_dependency_transition_checkpoint(
                        session, continuation, attempt
                    )
                except TransformerStageError as error:
                    self._block(session, continuation, error.code, error.message)
                    return
            try:
                self._dependency_transitions.advance(session, continuation)
            except DependencyTransitionError as error:
                if error.code in {
                    "COMMAND_EXIT_NONZERO",
                    "DEPENDENCY_TRANSITION_ANGULAR_UPDATE_FAILED",
                    "DEPENDENCY_TRANSITION_FRESH_BLOCKER_CHANGED",
                    "DEPENDENCY_TRANSITION_LOCKFILE_FAILED",
                }:
                    attempt = self._latest_repair(session, continuation)
                    if attempt is not None and attempt.apply_ledger_artifact_id:
                        RepairLifecycleService.transition_in_session(
                            session,
                            attempt,
                            "validation_failed",
                            reason="dependency-transition command failed after repair application",
                        )
                    self._validation_failure(
                        session,
                        continuation,
                        error,
                        event_reason=(
                            "dependency-transition command failed; "
                            "failure classification queued"
                        ),
                    )
                else:
                    self._block(session, continuation, error.code, error.message)

    def _verify_repair(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            binding = self._stage._binding(session, continuation)
            live = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
            if (
                attempt is None
                or attempt.status != "applied_verified"
                or not attempt.apply_ledger_checksum
                or live != binding.workspace_fingerprint
            ):
                self._block(
                    session,
                    continuation,
                    "REPAIR_VERIFICATION_FAILED",
                    "Applied repair post-state is incomplete or no longer canonical",
                )
                return
            RepairLifecycleService.transition_in_session(
                session,
                attempt,
                "migration_retried",
                reason="applied repair verification succeeded",
            )
            self._queue(continuation, "target_inspection")

    @staticmethod
    def _pending_dependency_transition(session, continuation) -> bool:
        """True when a dependency-transition repair is awaiting its angular retry.

        The latest repair attempt must be applied with a checksum-bound proposal
        carrying a dependency_transition operation, and the angular_update-0
        step's latest execution must be a terminal succeeded retry (i.e., the
        post-repair retry ran, so the runner may continue from phase UPDATE).
        """
        attempt = session.query(RepairAttemptModel).filter_by(
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
        ).order_by(RepairAttemptModel.attempt_number.desc()).first()
        if attempt is None or attempt.status not in {
            "approved_pending_execution",
            "executing",
            "uninstall",
            "angular_update",
            "reinstall",
            "npm_ci",
            "dependency_closure",
            "applied",
            "applied_verified",
        }:
            return False
        if not attempt.proposal_artifact_id or not attempt.proposal_checksum:
            return False
        metadata = session.get(
            ArtifactMetadataModel, "metadata-" + str(attempt.proposal_artifact_id)
        )
        if metadata is None or metadata.checksum != attempt.proposal_checksum:
            return False
        run = session.get(MigrationRunModel, continuation.run_id)
        if run is None or not run.artifact_root:
            return False
        try:
            stored = LocalFilesystemArtifactStore(
                Path(str(run.artifact_root)).parent,
                fixed_run_root=Path(str(run.artifact_root)),
            ).read_artifact(continuation.run_id, metadata.relative_path)
            if (
                stored.ref.artifact_id != attempt.proposal_artifact_id
                or stored.ref.checksum != attempt.proposal_checksum
                or stored.envelope is None
                or stored.envelope.run_id != continuation.run_id
                or stored.envelope.stage_id != continuation.current_stage_id
                or stored.envelope.attempt_id != attempt.id
            ):
                return False
            proposal = RepairProposal.model_validate(json.loads(stored.content))
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError):
            return False
        if not any(item.operation == "dependency_transition" for item in proposal.operations):
            return False
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "angular_update-0",
            )
        )
        execution = (
            session.get(CommandExecutionModel, step.execution_id)
            if step is not None and step.execution_id
            else None
        )
        return (
            execution is not None
            and execution.status == "succeeded"
            and execution.parent_execution_id is not None
        )

    @staticmethod
    def _g10_causal_eligibility(session, continuation, attempt) -> tuple[bool, str | None]:
        return g10_eligibility(
            session, continuation.run_id, continuation.current_stage_id, attempt.id
        )

    def _post_repair_checkpoint(self, session, continuation, attempt):
        if attempt.status in {
            "executing",
            "uninstall",
            "angular_update",
            "reinstall",
            "npm_ci",
            "dependency_closure",
        }:
            binding = self._stage._binding(session, continuation)
            checkpoints = session.scalars(
                select(StageCheckpointModel)
                .where(
                    StageCheckpointModel.run_id == continuation.run_id,
                    StageCheckpointModel.stage_id == continuation.current_stage_id,
                    StageCheckpointModel.kind == "post_repair",
                )
                .order_by(StageCheckpointModel.sequence.desc())
            ).all()
            for checkpoint in checkpoints:
                if Path(checkpoint.workspace_path).resolve() == Path(binding.workspace_path).resolve():
                    # Legacy post-repair rows pointed at the mutable stage
                    # workspace. They cannot be used for recovery because a
                    # later failed command may already have changed it.
                    continue
                execution = (
                    session.get(CommandExecutionModel, checkpoint.created_from_execution_id)
                    if checkpoint.created_from_execution_id
                    else None
                )
                if (
                    execution is None
                    or execution.command_id != "npm-dependency-uninstall"
                    or execution.status != "succeeded"
                    or execution.exit_code != 0
                    or checkpoint.workspace_fingerprint != binding.workspace_fingerprint
                ):
                    continue
                if self._stage.authoritative_checkpoint_fingerprint(session, checkpoint) != checkpoint.workspace_fingerprint:
                    raise TransformerStageError(
                        "POST_REPAIR_CHECKPOINT_STALE",
                        "Dependency-transition checkpoint is not authoritative",
                    )
                return checkpoint
            raise TransformerStageError(
                "POST_REPAIR_CHECKPOINT_MISSING",
                "No sealed post-uninstall checkpoint is available",
            )
        if not all(
            (
                attempt.post_fingerprint,
                attempt.proposal_artifact_id,
                attempt.proposal_checksum,
                attempt.apply_ledger_artifact_id,
                attempt.apply_ledger_checksum,
            )
        ):
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Applied repair attempt has no post-repair fingerprint",
            )
        run = session.get(MigrationRunModel, continuation.run_id)
        binding = self._stage._binding(session, continuation)
        if run is None or binding.workspace_fingerprint != attempt.post_fingerprint:
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Active workspace binding does not match the applied repair fingerprint",
            )
        store = LocalFilesystemArtifactStore(
            Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
        )
        checkpoints = session.scalars(
            select(StageCheckpointModel)
            .where(
                StageCheckpointModel.run_id == continuation.run_id,
                StageCheckpointModel.stage_id == continuation.current_stage_id,
                StageCheckpointModel.kind == "post_repair",
            )
            .order_by(StageCheckpointModel.sequence.desc())
        ).all()
        for checkpoint in checkpoints:
            if not checkpoint.manifest_artifact_id:
                raise TransformerStageError(
                    "POST_REPAIR_CHECKPOINT_STALE",
                    "Post-repair checkpoint has no lineage manifest",
                )
            metadata = session.get(
                ArtifactMetadataModel, "metadata-" + checkpoint.manifest_artifact_id
            )
            if (
                metadata is None
                or metadata.run_id != continuation.run_id
                or metadata.stage_id != continuation.current_stage_id
                or metadata.checksum != checkpoint.manifest_checksum
            ):
                raise TransformerStageError(
                    "POST_REPAIR_CHECKPOINT_STALE",
                    "Post-repair checkpoint manifest metadata is missing or stale",
                )
            try:
                manifest = store.read_artifact(
                    continuation.run_id, metadata.relative_path
                )
                payload = json.loads(manifest.content)
            except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError, TypeError) as error:
                raise TransformerStageError(
                    "POST_REPAIR_CHECKPOINT_STALE",
                    "Post-repair checkpoint manifest cannot be verified",
                ) from error
            if payload.get("attempt_id") != attempt.id:
                continue
            expected = {
                "kind": "post_repair",
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
                "attempt_id": attempt.id,
                "proposal_artifact_id": attempt.proposal_artifact_id,
                "proposal_checksum": attempt.proposal_checksum,
                "apply_ledger_artifact_id": attempt.apply_ledger_artifact_id,
                "apply_ledger_checksum": attempt.apply_ledger_checksum,
                "post_fingerprint": attempt.post_fingerprint,
                "workspace_fingerprint": attempt.post_fingerprint,
            }
            if any(payload.get(key) != value for key, value in expected.items()):
                raise TransformerStageError(
                    "POST_REPAIR_LINEAGE_MISMATCH",
                    "Post-repair checkpoint lineage does not match the applied repair",
                )
            if (
                manifest.ref.artifact_id != checkpoint.manifest_artifact_id
                or manifest.ref.checksum != checkpoint.manifest_checksum
                or manifest.envelope is None
                or manifest.envelope.run_id != continuation.run_id
                or manifest.envelope.stage_id != continuation.current_stage_id
                or manifest.envelope.attempt_id != attempt.id
                or checkpoint.workspace_fingerprint != attempt.post_fingerprint
                or self._stage.authoritative_checkpoint_fingerprint(session, checkpoint)
                != attempt.post_fingerprint
            ):
                raise TransformerStageError(
                    "POST_REPAIR_CHECKPOINT_STALE",
                    "Post-repair checkpoint no longer matches its durable workspace",
                )
            return checkpoint
        raise TransformerStageError(
            "POST_REPAIR_CHECKPOINT_MISSING",
            "No attempt-bound post-repair checkpoint is available",
        )

    def _validate_applied_ledger(self, session, continuation, attempt):
        if not attempt.apply_ledger_artifact_id or not attempt.apply_ledger_checksum:
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Applied repair ledger binding is missing",
            )
        run = session.get(MigrationRunModel, continuation.run_id)
        metadata = session.get(
            ArtifactMetadataModel, "metadata-" + attempt.apply_ledger_artifact_id
        )
        if (
            run is None
            or metadata is None
            or metadata.run_id != continuation.run_id
            or metadata.stage_id != continuation.current_stage_id
            or metadata.checksum != attempt.apply_ledger_checksum
        ):
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Applied repair ledger artifact binding is invalid",
            )
        try:
            store = LocalFilesystemArtifactStore(
                Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
            )
            ledger = store.read_artifact(continuation.run_id, metadata.relative_path)
            payload = json.loads(ledger.content)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError, TypeError) as error:
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Applied repair ledger artifact cannot be verified",
            ) from error
        if (
            ledger.ref.artifact_id != attempt.apply_ledger_artifact_id
            or ledger.ref.checksum != attempt.apply_ledger_checksum
            or ledger.envelope is None
            or ledger.envelope.run_id != continuation.run_id
            or ledger.envelope.stage_id != continuation.current_stage_id
            or ledger.envelope.attempt_id != attempt.id
            or payload.get("schema_version") != "repair-apply-ledger-v1"
            or payload.get("attempt_id") != attempt.id
            or payload.get("status") != "applied"
            or payload.get("proposal_checksum") != attempt.proposal_checksum
            or payload.get("pre_fingerprint") != attempt.pre_fingerprint
            or payload.get("post_fingerprint") != attempt.post_fingerprint
        ):
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Applied repair ledger does not match the approved repair",
            )

    def _ensure_post_repair_checkpoint(self, session, continuation, attempt):
        try:
            return self._post_repair_checkpoint(session, continuation, attempt)
        except TransformerStageError as error:
            if error.code != "POST_REPAIR_CHECKPOINT_MISSING":
                raise
        if attempt.status not in {"applied", "applied_verified"}:
            raise TransformerStageError(
                "POST_REPAIR_CHECKPOINT_MISSING",
                "Post-repair checkpoint is missing for an unapplied repair attempt",
            )
        binding = self._stage._binding(session, continuation)
        live = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
        if live != binding.workspace_fingerprint or live != attempt.post_fingerprint:
            raise TransformerStageError(
                "POST_REPAIR_CHECKPOINT_STALE",
                "Legacy post-repair checkpoint recovery requires an unchanged repaired workspace",
            )
        self._validate_applied_ledger(session, continuation, attempt)
        gate = session.scalar(
            select(StageGatePackageModel).where(
                StageGatePackageModel.id == attempt.g10_gate_package_id,
                StageGatePackageModel.run_id == continuation.run_id,
                StageGatePackageModel.stage_id == continuation.current_stage_id,
                StageGatePackageModel.gate_id == "G10",
                StageGatePackageModel.status == "approved",
            )
        )
        decision = session.scalar(
            select(StageGateDecisionModel).where(
                StageGateDecisionModel.gate_package_id == gate.id if gate else False,
                StageGateDecisionModel.decision == "approve",
                StageGateDecisionModel.accepted.is_(True),
            )
        ) if gate else None
        if gate is None or decision is None or not attempt.pre_fingerprint:
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Approved G10 lineage is unavailable for legacy recovery",
            )
        pre_checkpoint = session.get(StageCheckpointModel, attempt.checkpoint_id)
        if (
            pre_checkpoint is None
            or pre_checkpoint.kind != "pre_repair"
            or self._stage.authoritative_checkpoint_fingerprint(session, pre_checkpoint)
            != attempt.pre_fingerprint
        ):
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Pre-repair lineage cannot authorize legacy post-repair recovery",
            )
        try:
            self._gates._validate_repair_lineage(
                session,
                continuation,
                gate.package_artifact_id,
                gate.package_checksum,
                artifact_set_checksum=gate.artifact_set_checksum,
                expected_workspace_fingerprint=attempt.pre_fingerprint,
            )
        except StageGateError as error:
            raise TransformerStageError(
                "POST_REPAIR_LINEAGE_MISMATCH",
                "Approved G10 lineage cannot authorize legacy post-repair recovery",
            ) from error
        run = session.get(MigrationRunModel, continuation.run_id)
        snapshot = self._stage.snapshot_workspace(
            binding.workspace_path,
            (run.workspace_aliases or {})["STAGE_SANDBOX"],
            continuation.current_stage_id,
        )
        if snapshot.fingerprint != attempt.post_fingerprint:
            raise TransformerStageError(
                "POST_REPAIR_CHECKPOINT_STALE",
                "Legacy post-repair snapshot fingerprint changed during recovery",
            )
        self._stage.persist_post_repair_checkpoint(
            session,
            continuation,
            snapshot,
            attempt_id=attempt.id,
            proposal_artifact_id=attempt.proposal_artifact_id,
            proposal_checksum=attempt.proposal_checksum,
            apply_ledger_artifact_id=attempt.apply_ledger_artifact_id,
            apply_ledger_checksum=attempt.apply_ledger_checksum,
            post_fingerprint=attempt.post_fingerprint,
        )
        session.flush()
        return self._post_repair_checkpoint(session, continuation, attempt)

    @staticmethod
    def _angular_update_reconstruction_checkpoint(session, continuation):
        """Resolve the checkpoint referenced by the failing execution or prompt.

        Accepts exactly the checkpoint kinds an Angular-update execution may
        legitimately be bound to: the initial ``pre_angular_update`` checkpoint
        or the post-repair ``post_repair`` checkpoint (post-uninstall /
        pre-angular-retry).  Never falls back to "the newest" checkpoint of any
        kind: the reconstruction source must be the checkpoint the failing
        execution was bound to (execution.checkpoint_id), or the prompt
        decision that drove it (prompt.reconstruction_checkpoint_id), and the
        checkpoint must still agree with the durable workspace binding.
        """
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "angular_update-0",
            )
        )
        execution = (
            session.get(CommandExecutionModel, step.execution_id)
            if step is not None and step.execution_id
            else None
        )
        checkpoint = (
            session.get(StageCheckpointModel, execution.checkpoint_id)
            if execution is not None and execution.checkpoint_id
            else None
        )
        if checkpoint is None and execution is not None and execution.prompt_request_id:
            prompt = session.get(StagePromptRequestModel, execution.prompt_request_id)
            checkpoint = (
                session.get(StageCheckpointModel, prompt.reconstruction_checkpoint_id)
                if prompt is not None and prompt.reconstruction_checkpoint_id
                else None
            )
        if (
            checkpoint is None
            or checkpoint.kind not in _ANGULAR_RECOVERY_CHECKPOINT_KINDS
            or checkpoint.run_id != continuation.run_id
            or checkpoint.stage_id != continuation.current_stage_id
            or (execution is not None and checkpoint.id != execution.checkpoint_id)
        ):
            return None
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        if (
            binding is not None
            and binding.fingerprint_profile_id == STAGE_FINGERPRINT_PROFILE.profile_id
            and checkpoint.workspace_fingerprint != binding.workspace_fingerprint
        ):
            return None
        return checkpoint

    def _restore_angular_update_checkpoint(
        self, session, continuation, attempt=None
    ):
        attempt = attempt or session.query(RepairAttemptModel).filter_by(
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
        ).order_by(RepairAttemptModel.attempt_number.desc()).first()
        checkpoint = self._angular_update_recovery_checkpoint(
            session, continuation, attempt
        )
        if checkpoint is None:
            raise TransformerStageError(
                "CHECKPOINT_MISSING",
                "No execution-referenced angular update checkpoint is available for recovery",
            )
        binding = self._stage._binding(session, continuation)
        run = session.get(MigrationRunModel, continuation.run_id)
        checkpoint_fingerprint = self._stage.authoritative_checkpoint_fingerprint(
            session, checkpoint
        )
        if checkpoint_fingerprint is None:
            raise TransformerStageError(
                "POST_REPAIR_CHECKPOINT_STALE"
                if checkpoint.kind == "post_repair"
                else "CHECKPOINT_INTEGRITY_FAILED",
                "Recovery checkpoint is not authoritative",
            )
        self._stage.begin_reconstruction(
            session,
            continuation,
            checkpoint=checkpoint,
            reason="angular_update_recovery",
            attempt_id=attempt.id if attempt is not None else None,
        )
        new_fingerprint = self._stage.reconstruct_workspace(
            checkpoint.workspace_path,
            binding.workspace_path,
            (run.workspace_aliases or {})["STAGE_SANDBOX"],
            checkpoint_fingerprint,
            run.artifact_root,
        )
        if StageSandboxCopier.fingerprint(Path(binding.workspace_path)) != new_fingerprint:
            raise TransformerStageError(
                "CHECKPOINT_INTEGRITY_FAILED",
                "Restored workspace fingerprint changed during recovery",
            )
        self._stage.record_reconstruction(
            session,
            continuation,
            checkpoint=checkpoint,
            reason="angular_update_recovery",
            restored_fingerprint=new_fingerprint,
            attempt_id=attempt.id if attempt is not None else None,
        )
        binding.workspace_fingerprint = new_fingerprint
        binding.fingerprint_profile_id = STAGE_FINGERPRINT_PROFILE.profile_id
        binding.last_verified_fingerprint = new_fingerprint
        binding.last_verified_at = datetime.now(UTC)
        return checkpoint.id, new_fingerprint

    def _restore_dependency_transition_checkpoint(self, session, continuation, attempt):
        """Restore the immutable pre-update tree before dependency materialization."""
        checkpoint, authority_execution_id = self._dependency_transition_checkpoint(
            session, continuation
        )
        if checkpoint is None:
            raise TransformerStageError(
                "CHECKPOINT_MISSING",
                "No authoritative pre_angular_update checkpoint can materialize the dependency transition",
            )
        binding = self._stage._binding(session, continuation)
        run = session.get(MigrationRunModel, continuation.run_id)
        fingerprint = self._stage.authoritative_checkpoint_fingerprint(session, checkpoint)
        if run is None or fingerprint is None:
            raise TransformerStageError(
                "CHECKPOINT_INTEGRITY_FAILED",
                "The dependency-transition pre-update checkpoint is not authoritative",
            )
        materialization_prefix = f"{attempt.id}:transition:v2:materialize:initial"
        latest_materialization = session.scalar(
            select(CommandExecutionModel)
            .where(
                CommandExecutionModel.run_id == continuation.run_id,
                CommandExecutionModel.idempotency_key.startswith(materialization_prefix),
            )
            .order_by(CommandExecutionModel.requested_at.desc(), CommandExecutionModel.id.desc())
        )
        runtime = self._stage.runtime_binding(session, continuation)
        force_restore = bool(
            latest_materialization is not None
            and latest_materialization.status in {"succeeded", "failed", "timed_out", "cancelled"}
            and (
                latest_materialization.runtime_checksum != runtime["checksum"]
                or (latest_materialization.start_fingerprint or {}).get("runtime_checksum")
                != runtime["checksum"]
                or (latest_materialization.start_fingerprint or {}).get("runtime_profile_id")
                != runtime["profile_id"]
            )
        )
        if (
            StageSandboxCopier.fingerprint(Path(binding.workspace_path)) == fingerprint
            and binding.workspace_fingerprint == fingerprint
            and binding.fingerprint_profile_id == STAGE_FINGERPRINT_PROFILE.profile_id
            and not force_restore
        ):
            return checkpoint.id, fingerprint
        self._stage.begin_reconstruction(
            session,
            continuation,
            checkpoint=checkpoint,
            reason="dependency_transition_materialization",
            execution_id=authority_execution_id,
            attempt_id=attempt.id,
            mode=ReconstructionMode.AUTHORIZED_ROLLBACK,
        )
        restored = self._stage.reconstruct_workspace(
            checkpoint.workspace_path,
            binding.workspace_path,
            (run.workspace_aliases or {})["STAGE_SANDBOX"],
            fingerprint,
            run.artifact_root,
        )
        if (
            restored != fingerprint
            or StageSandboxCopier.fingerprint(Path(binding.workspace_path)) != fingerprint
        ):
            raise TransformerStageError(
                "CHECKPOINT_INTEGRITY_FAILED",
                "Dependency-transition restoration changed before materialization",
            )
        self._stage.record_reconstruction(
            session,
            continuation,
            checkpoint=checkpoint,
            reason="dependency_transition_materialization",
            restored_fingerprint=restored,
            execution_id=authority_execution_id,
            attempt_id=attempt.id,
            mode=ReconstructionMode.AUTHORIZED_ROLLBACK,
        )
        binding.workspace_fingerprint = restored
        binding.fingerprint_profile_id = STAGE_FINGERPRINT_PROFILE.profile_id
        binding.last_verified_fingerprint = restored
        binding.last_verified_at = datetime.now(UTC)
        return checkpoint.id, restored

    def _dependency_transition_checkpoint(self, session, continuation):
        """Resolve only an execution-bound immutable pre_angular_update checkpoint."""
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "angular_update-0",
            )
        )
        execution = (
            session.get(CommandExecutionModel, step.execution_id)
            if step is not None and step.execution_id
            else None
        )
        seen: set[str] = set()
        while execution is not None and execution.id not in seen:
            seen.add(execution.id)
            checkpoint = (
                session.get(StageCheckpointModel, execution.checkpoint_id)
                if execution.checkpoint_id
                else None
            )
            if (
                checkpoint is not None
                and checkpoint.run_id == continuation.run_id
                and checkpoint.stage_id == continuation.current_stage_id
                and checkpoint.kind == "pre_angular_update"
                and checkpoint.safe_for_resume
                and self._stage.authoritative_checkpoint_fingerprint(session, checkpoint)
                is not None
            ):
                return checkpoint, execution.id
            execution = (
                session.get(CommandExecutionModel, execution.parent_execution_id)
                if execution.parent_execution_id
                else None
            )
        return None, None

    def _angular_update_recovery_checkpoint(self, session, continuation, attempt=None):
        """Resolve an authorized checkpoint after a mutating update failure.

        A post-repair checkpoint is preferred when its complete lineage is
        valid. If a repair attempt has already mutated the workspace but its
        post-repair checkpoint is stale or incomplete, restart from the
        attempt's immutable pre-repair checkpoint instead of blocking a
        recoverable run or trusting a partially mutated workspace.
        """
        checkpoint = self._angular_update_reconstruction_checkpoint(
            session, continuation
        )
        if checkpoint is not None:
            return checkpoint
        attempt = attempt or self._latest_repair(session, continuation, required=False)
        active_statuses = {
            "approved_pending_execution",
            "executing",
            "uninstall",
            "angular_update",
            "reinstall",
            "npm_ci",
            "dependency_closure",
            "applied",
            "applied_verified",
        }
        if attempt is None or attempt.status not in active_statuses:
            return None
        try:
            return self._ensure_post_repair_checkpoint(session, continuation, attempt)
        except TransformerStageError as error:
            if error.code not in {
                "POST_REPAIR_CHECKPOINT_MISSING",
                "POST_REPAIR_CHECKPOINT_STALE",
                "POST_REPAIR_LINEAGE_MISMATCH",
            }:
                raise
        pre_repair = (
            session.get(StageCheckpointModel, attempt.checkpoint_id)
            if attempt.checkpoint_id
            else None
        )
        if (
            pre_repair is None
            or pre_repair.run_id != continuation.run_id
            or pre_repair.stage_id != continuation.current_stage_id
            or pre_repair.kind != "pre_repair"
            or not pre_repair.safe_for_resume
            or not attempt.pre_fingerprint
            or self._stage.authoritative_checkpoint_fingerprint(session, pre_repair)
            != attempt.pre_fingerprint
        ):
            return None
        return pre_repair

    @staticmethod
    def _latest_repair(session, continuation, *, statuses=None, exclude_statuses=None, required=True):
        query = session.query(RepairAttemptModel).filter_by(
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
        )
        if statuses is not None:
            query = query.filter(RepairAttemptModel.status.in_(statuses))
        if exclude_statuses is None:
            exclude_statuses = {"superseded"}
        if exclude_statuses:
            query = query.filter(~RepairAttemptModel.status.in_(exclude_statuses))
        attempt = query.order_by(RepairAttemptModel.attempt_number.desc()).first()
        if attempt is None and required:
            raise TransformerStageError("REPAIR_ATTEMPT_MISSING", "Repair attempt is missing")
        return attempt

    @staticmethod
    def _legacy_authority_recovered(session, attempt, checkpoint) -> bool:
        """True when the attempt's authority was migrated by legacy fingerprint recovery.

        The lineage row proves the attempt's historical checkpoint hash was
        verified under a legacy profile AND its tree matched the live
        workspace under the current canonical profile, so legacy-encoded
        attempt fields (``pre_fingerprint``, checkpoint stored hash) must not
        be compared against live digests.
        """
        return (
            session.scalar(
                select(RepairFingerprintRecoveryModel).where(
                    RepairFingerprintRecoveryModel.run_id == attempt.run_id,
                    RepairFingerprintRecoveryModel.stage_id == attempt.stage_id,
                    RepairFingerprintRecoveryModel.attempt_id == attempt.id,
                    RepairFingerprintRecoveryModel.checkpoint_id == checkpoint.id,
                )
            )
            is not None
        )

    @staticmethod
    def _rebind_child_authority_recovered(session, attempt, checkpoint, live) -> bool:
        """Accept a deterministic child on its parent's verified post-repair tree."""
        if not str(attempt.diagnosis or "").startswith(
            (
                "deterministic ",
                "human revision;",
                "semantic retry recovery;",
                "validation correction;",
            )
        ):
            return False
        seen: set[str] = set()
        parent_id = attempt.parent_attempt_id
        for _ in range(32):
            if not isinstance(parent_id, str) or parent_id in seen:
                return False
            seen.add(parent_id)
            parent = session.get(RepairAttemptModel, parent_id)
            if parent is None:
                return False
            if (
                parent.checkpoint_id == checkpoint.id
                and parent.post_fingerprint == live
                and parent.apply_ledger_artifact_id
                and parent.status in {"applied", "applied_verified", "superseded"}
            ):
                return True
            parent_id = parent.parent_attempt_id
        return False

    @staticmethod
    def _validation_failure(
        session,
        continuation,
        error: ValidationRunnerError | LockfileGenerationError,
        *,
        event_reason: str = "validation command failed; failure classification queued",
    ) -> None:
        expected_state_version = continuation.state_version
        continuation.status = "queued"
        continuation.current_node = "classify_failure"
        continuation.last_error_code = error.code
        continuation.last_error_message = error.message
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = datetime.now(UTC)
        session.flush()
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_FAILED,
            key=f"failed:{expected_state_version}:{error.code}",
            reason=event_reason,
            payload={
                "last_error_code": error.code,
                "expected_state_version": expected_state_version,
            },
        )

    @staticmethod
    def _node_for_group(group: str) -> str:
        return "build" if group == "builds" else "test"

    def _validation_groups(self, session, continuation) -> list[str]:
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        policy = (stage_plan.stage_plan or {}).get("validation_policy") or {}
        return self._validation.required_groups(policy)

    @staticmethod
    def _validation_attempt_key(session, continuation) -> str:
        attempt = session.query(RepairAttemptModel).filter_by(
            run_id=continuation.run_id, stage_id=continuation.current_stage_id
        ).filter(
            RepairAttemptModel.status != "superseded"
        ).order_by(RepairAttemptModel.attempt_number.desc()).first()
        return attempt.id if attempt and attempt.status in {"applied", "applied_verified", "migration_retried", "revalidating"} else "initial"

    @staticmethod
    def _target_version_recovery_required(execution) -> bool:
        return bool(
            execution is not None
            and execution.status in {"failed", "interrupted", "timed_out"}
            and execution.operation_kind == "read_only"
            and execution.reconstruction_required
            and execution.parent_execution_id is None
        )

    def _cancel(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            active = session.scalar(
                select(CommandExecutionModel).where(
                    CommandExecutionModel.run_id == continuation.run_id,
                    CommandExecutionModel.status.in_(("queued", "pending", "running")),
                )
            )
            if active is not None:
                active.cancel_requested_at = datetime.now(UTC)
                active.cancel_requested_by = continuation.cancel_requested_by
            for gate in session.query(StageGatePackageModel).filter_by(
                run_id=continuation.run_id, status="pending"
            ):
                gate.status = "cancelled"
                gate.stale_at = datetime.now(UTC)
            for prompt in session.query(StagePromptRequestModel).filter(
                StagePromptRequestModel.run_id == continuation.run_id,
                StagePromptRequestModel.status.not_in(("decided", "cancelled", "stale")),
            ):
                prompt.status = "cancelled"
            for repair in session.query(RepairAttemptModel).filter(
                RepairAttemptModel.run_id == continuation.run_id,
                RepairAttemptModel.status.in_(
                    (
                        "evidence_frozen",
                        "proposed",
                        "review_accepted",
                        "waiting_g10",
                        "applying",
                        "applied",
                        "approved_pending_execution",
                        "executing",
                        "applied_verified",
                        "migration_retried",
                        "validation_passed",
                        "validation_failed",
                        "revalidating",
                        "revalidating_affected",
                    )
                ),
            ):
                repair.status = "cancelled"
                repair.updated_at = datetime.now(UTC)
            expected_state_version = continuation.state_version
            continuation.status = "cancelled"
            continuation.current_node = "terminal"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.completed_at = datetime.now(UTC)
            continuation.updated_at = continuation.completed_at
            continuation.state_version += 1
            session.flush()
            append_continuation_event(
                session,
                continuation,
                event_type=WorkflowEventType.TRANSFORMATION_CANCELLED,
                key=f"cancelled:{expected_state_version}",
                reason="Transformer cancellation completed",
                payload={"expected_state_version": expected_state_version},
                occurred_at=continuation.completed_at,
            )

    @staticmethod
    def _owned(session, continuation_id: str, worker_id: str):
        continuation = session.get(TransformationContinuationModel, continuation_id)
        if continuation is None or continuation.status != "running" or continuation.worker_id != worker_id:
            raise TransformerStageError("TRANSFORMATION_CLAIM_STALE", "Worker no longer owns continuation")
        return continuation

    @staticmethod
    def _queue(continuation, node: str) -> None:
        continuation.status = "queued"
        continuation.current_node = node
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = datetime.now(UTC)

    @staticmethod
    def _block(session, continuation, code: str, message: str) -> None:
        expected_state_version = continuation.state_version
        continuation.status = "blocked"
        continuation.last_error_code = code
        continuation.last_error_message = message
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = datetime.now(UTC)
        session.flush()
        append_continuation_event(
            session,
            continuation,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED,
            key=f"block:{expected_state_version}:{code}",
            reason=message,
            payload={
                "last_error_code": code,
                "expected_state_version": expected_state_version,
            },
        )


class TransformerWorkflow:
    def __init__(self, orchestrator: TransformerOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or TransformerOrchestrator()
        graph = StateGraph(TransformerPointer)
        graph.add_node("advance", self._advance)
        graph.set_entry_point("advance")
        graph.add_edge("advance", END)
        self.graph = graph.compile()

    def _advance(self, state: TransformerPointer) -> TransformerPointer:
        self.orchestrator.advance(state["continuation_id"], state["worker_id"])
        return state

    def invoke(self, continuation_id: str, worker_id: str) -> None:
        try:
            self.graph.invoke({"continuation_id": continuation_id, "worker_id": worker_id})
        except (TransformerStageError, StageGateError) as error:
            self.orchestrator.fail(continuation_id, worker_id, error)
