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
    ArtifactType,
    LocalFilesystemArtifactStore,
    StoredArtifact,
)
from app.domain.contracts import WorkflowEventType
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
    G06ApprovalModel,
    LlmInvocationModel,
    MigrationPlanModel,
    MigrationRunModel,
    RepairAttemptModel,
    RepairFingerprintRecoveryModel,
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
from app.services.dependency_closure_service import verify_exact_dependency_state
from app.services.dependency_transition_runner import (
    DependencyTransitionError,
    DependencyTransitionRunner,
)
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.lockfile_generation_runner import (
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
from app.services.stage_gate_service import StageGateError, StageGateService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService
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
                self._stage.queue_version_check(
                    session, self._owned(session, continuation_id, worker_id)
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

    def fail(self, continuation_id: str, worker_id: str, error: TransformerStageError) -> None:
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
                self._stage.runtime_binding(session, continuation)
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
                    attempt = self._latest_repair(session, continuation)
                    if attempt is not None and attempt.status == "applied_verified":
                        attempt.status = "migration_retried"
                        attempt.updated_at = datetime.now(UTC)
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
            if version_execution is None or version_execution.status != "succeeded":
                self._block(
                    session,
                    continuation,
                    version_execution.failure_code if version_execution else "VERSION_CHECK_MISSING",
                    "Target version command did not succeed",
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
                "workspace_fingerprint": binding.workspace_fingerprint,
            }
        try:
            context["workspace_fingerprint"] = StageSandboxCopier.fingerprint(
                Path(context["workspace_path"])
            )
            versions, ledger = self._evidence.build(
                context["workspace_path"],
                context["checkpoint_path"],
                target_core=context["target_core"],
                target_cli=context["target_cli"],
                ng_version_output=context["ng_version_output"],
                angular_execution_id=context["angular_execution_id"],
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
            gate_id = "G11"
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
        """Post-state exact verification for bound dependency_add operations.

        Runs at aggregate_validation, after apply, lockfile generation, npm ci,
        and validation completed. Reads ONLY the checksum-bound proposal
        artifact (never the frontend) and verifies manifest, lockfile, and
        installed metadata all carry the backend-bound exact version. Returns
        None when the attempt carries no dependency_add operation (no behavior
        change), otherwise a list of per-operation reports.
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
                report = verify_exact_dependency_state(
                    Path(binding.workspace_path),
                    package=str(item.package),
                    section=str(item.section),
                    exact_version=str(item.new_version),
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
                exact_version=str(item.new_version),
                report=report,
            )
            reports.append(
                {
                    "package": str(item.package),
                    "section": str(item.section),
                    "new_version": str(item.new_version),
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
        exact_version: str,
        report: dict[str, object],
    ) -> StoredArtifact:
        content = json.dumps(
            {
                "schema_version": "dependency-add-verification-v1",
                "attempt_id": repair.id,
                "package": package,
                "section": section,
                "expected_exact": exact_version,
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
            policy_version="dependency-add-verification-v1",
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

    def _classify_failure(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            if self._resume_stale_g08_validation(session, continuation):
                return
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
                attempt = session.query(RepairAttemptModel).filter_by(
                    run_id=continuation.run_id,
                    stage_id=continuation.current_stage_id,
                ).order_by(RepairAttemptModel.attempt_number.desc()).first()
                binding = self._stage._binding(session, continuation)
                live = StageSandboxCopier.fingerprint(Path(binding.workspace_path))
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
                        or self._angular_update_reconstruction_checkpoint(
                            session, continuation
                        )
                        is None
                    ):
                        self._block(
                            session,
                            continuation,
                            "CHECKPOINT_RECOVERY_FAILED",
                            "Workspace diverged from its binding and no authorized recovery checkpoint is available",
                        )
                        return
                    try:
                        self._restore_angular_update_checkpoint(session, continuation)
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
                        (
                            attempt is not None
                            and attempt.status in {"applied", "applied_verified"}
                        )
                        or self._angular_update_reconstruction_checkpoint(session, continuation) is not None
                    )
                ):
                    # Restore before freezing failure/context evidence so the
                    # attempt and governed checkpoint share one authoritative
                    # workspace fingerprint.
                    try:
                        self._restore_angular_update_checkpoint(session, continuation)
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
        try:
            with self._scope() as session:
                continuation = self._owned(session, continuation_id, worker_id)

                for artifact in (failure, route_artifact, context):
                    if artifact is not None:
                        self._stage.register_artifact(session, artifact, continuation)
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
                        self._restore_angular_update_checkpoint(session, continuation)
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
                if (
                    budget["consumed_attempts"] >= budget["max_attempts"]
                    or budget["consumed_applied"] >= budget["max_applied"]
                ):
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
                    diagnosis=f"{route.value}; checkpoint={checkpoint.id}",
                    checkpoint_id=checkpoint.id,
                    failure_evidence_artifact_id=failure.ref.artifact_id,
                    failure_evidence_checksum=failure.ref.checksum,
                    failure_route_artifact_id=route_artifact.ref.artifact_id,
                    failure_route_checksum=route_artifact.ref.checksum,
                    context_pack_artifact_id=context.ref.artifact_id,
                    context_pack_checksum=context.ref.checksum,
                    pre_fingerprint=str(evidence["workspace_fingerprint"]),
                    failure_fingerprint=str(evidence["failure_fingerprint"]),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                session.add(attempt)
                self._queue(continuation, "propose_repair")
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
            attempt.status = "superseded"
            attempt.completed_at = now
            attempt.updated_at = now
        continuation.last_error_code = None
        continuation.last_error_message = None
        self._queue(continuation, "final_install")
        return True

    def _propose_repair(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            if self._resume_stale_g08_validation(session, continuation):
                return
            attempt = self._latest_repair(session, continuation)
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
                self._queue(continuation, "create_g10")
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
                self._queue(continuation, "create_g10")
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
                            "REPAIR_CAUSAL_REJECTION",
                            reason or "Repair candidate is not causally eligible for G10",
                        )
                        return
                if gate_id == "G10":
                    attempt.g10_gate_package_id = existing.id
                    attempt.status = "waiting_g10"
                    attempt.updated_at = datetime.now(UTC)
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
                        "REPAIR_CAUSAL_REJECTION",
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
                if review.get("decision") not in {"accept", "request_changes"}:
                    raise TransformerStageError(
                        "REPAIR_REVIEW_INVALID",
                        "Repair review decision is not eligible for G10",
                    )
                payload["review_override_required"] = review["decision"] == "request_changes"
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
                attempt.status = "waiting_g10"
                attempt.updated_at = datetime.now(UTC)

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
                    attempt.status = "apply_recovery_required"
                    if fingerprint is not None:
                        attempt.post_fingerprint = fingerprint
                    attempt.updated_at = datetime.now(UTC)
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
                or checkpoint_fingerprint != live
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
                    or checkpoint_fingerprint != live
                    or (
                        current_attempt.pre_fingerprint != live
                        and not self._legacy_authority_recovered(
                            session, current_attempt, checkpoint
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
                attempt.status = "apply_failed"
                attempt.updated_at = datetime.now(UTC)
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
            attempt.apply_ledger_artifact_id = ledger.ref.artifact_id
            attempt.apply_ledger_checksum = ledger.ref.checksum
            attempt.post_fingerprint = fingerprint
            attempt.status = "executing" if is_dependency_transition else "applied_verified"
            attempt.updated_at = datetime.now(UTC)
            post_apply_node = self._post_apply_node(proposal)
            if (
                post_apply_node != "dependency_transition"
                and self._angular_update_retry_eligible(session, continuation)
            ):
                post_apply_node = "angular_update_retry"
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
    def _post_apply_node(proposal: dict[str, object]) -> str:
        operations = proposal.get("operations") or []
        if any(
            item.get("operation") == "dependency_transition" for item in operations
        ):
            return "dependency_transition"
        return (
            "lockfile_generation"
            if any(
                item.get("operation") in {"dependency_change", "dependency_add"}
                for item in operations
            )
            else "repair_revalidate"
        )

    def _lockfile_generation(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            try:
                self._lockfiles.advance(
                    session, continuation, next_node="repair_revalidate"
                )
            except LockfileGenerationError as error:
                self._block(session, continuation, error.code, error.message)

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
            attempt = self._latest_repair(session, continuation)
            if attempt.status in {"applied", "applied_verified", "migration_retried", "revalidating_affected"}:
                run = session.get(MigrationRunModel, continuation.run_id)
                metadata = session.get(ArtifactMetadataModel, "metadata-" + str(attempt.proposal_artifact_id))
                if run is None or metadata is None or metadata.checksum != attempt.proposal_checksum:
                    self._block(session, continuation, "REPAIR_PROPOSAL_STALE", "Bound repair proposal is missing or stale")
                    return
                try:
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
                        raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Bound repair proposal envelope is stale")
                    proposal = RepairProposal.model_validate(
                        json.loads(stored_proposal.content)
                    ).model_dump(mode="json")
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
                if attempt.status in {"applied", "applied_verified", "migration_retried"}:
                    attempt.status = "revalidating_affected"
                    attempt.updated_at = datetime.now(UTC)
                for target in targets:
                    try:
                        outcome = self._validation.advance_group(
                            session,
                            continuation,
                            VALIDATION_TARGET_GROUPS[target],
                            next_node="repair_revalidate",
                            attempt_key=f"{attempt.id}:affected",
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
                step.status = "PENDING"
                step.execution_id = None
                step.completed_at = None
            attempt.status = "revalidating"
            attempt.updated_at = datetime.now(UTC)
            self._queue(continuation, "final_install")

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
        return route.value in {"repairable_source", "angular_update_peer_conflict"}

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
        return (
            execution is not None
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
            uninstall = session.scalar(
                select(CommandExecutionModel).where(
                    CommandExecutionModel.run_id == continuation.run_id,
                    CommandExecutionModel.idempotency_key
                    == f"{attempt.id}:transition:uninstall",
                )
            )
            if uninstall is None and attempt.status == "approved_pending_execution":
                try:
                    self._restore_angular_update_checkpoint(session, continuation)
                except TransformerStageError as error:
                    self._block(session, continuation, error.code, error.message)
                    return
            try:
                self._dependency_transitions.advance(session, continuation)
            except DependencyTransitionError as error:
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
            attempt.status = "migration_retried"
            attempt.updated_at = datetime.now(UTC)
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

    def _restore_angular_update_checkpoint(self, session, continuation):
        attempt = session.query(RepairAttemptModel).filter_by(
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
        ).order_by(RepairAttemptModel.attempt_number.desc()).first()
        if attempt is not None and attempt.status in {
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
            checkpoint = self._ensure_post_repair_checkpoint(session, continuation, attempt)
        else:
            checkpoint = self._angular_update_reconstruction_checkpoint(session, continuation)
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
        )
        new_fingerprint = self._stage.reconstruct_workspace(
            checkpoint.workspace_path,
            binding.workspace_path,
            (run.workspace_aliases or {})["STAGE_SANDBOX"],
            checkpoint_fingerprint,
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

    @staticmethod
    def _latest_repair(session, continuation, *, statuses=None):
        query = session.query(RepairAttemptModel).filter_by(
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
        )
        if statuses is not None:
            query = query.filter(RepairAttemptModel.status.in_(statuses))
        attempt = query.order_by(RepairAttemptModel.attempt_number.desc()).first()
        if attempt is None:
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
    def _validation_failure(
        session, continuation, error: ValidationRunnerError
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
            reason="validation failure recorded; failure classification queued",
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
        ).order_by(RepairAttemptModel.attempt_number.desc()).first()
        return attempt.id if attempt and attempt.status in {"applied", "applied_verified", "migration_retried", "revalidating"} else "initial"

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
        except TransformerStageError as error:
            self.orchestrator.fail(continuation_id, worker_id, error)
