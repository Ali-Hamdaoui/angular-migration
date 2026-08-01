"""Pointer-only LangGraph for the durable Transformer state machine.

File-size exception: the transition handlers stay together so restart routing,
gate bindings, and transaction/IO boundaries can be audited as one state
machine. Command execution, evidence, validation, repair, and sealing logic
remain in dedicated services.
"""

from __future__ import annotations

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
from app.orchestration.transformer_sealing_flow import TransformerSealingFlow
from app.repositories.models import (
    ActivePlanVersionModel,
    ArtifactMetadataModel,
    CommandExecutionModel,
    CommandLogChunkModel,
    G06ApprovalModel,
    LlmInvocationModel,
    MigrationRunModel,
    RepairAttemptModel,
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
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.patch_apply_service import PatchApplyService
from app.services.prompt_explanation_service import PromptExplanationService
from app.services.repair_application_service import (
    RepairApplicationError,
    RepairApplicationService,
    RepairLlmError,
    RepairProposal,
)
from app.services.stage_gate_service import StageGateService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService
from app.services.validation_runner import (
    BuildAgent,
    TestAgent,
    ValidationRunner,
    ValidationRunnerError,
)

logger = logging.getLogger(__name__)


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
                self._block(continuation, error.code, error.message)

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
                self._block(continuation, "G06_BINDING_STALE", "Approved G06 binding changed")
                return
            self._queue(continuation, "prepare_workspace")

    def _resolve_runtime(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            try:
                self._stage.runtime_binding(session, continuation)
            except TransformerStageError as error:
                self._block(continuation, error.code, error.message)
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
                self._block(continuation, "BUILD_SYSTEM_DECISION_BLOCKED", "Approved build decision blocks execution")
                return
            self._queue(continuation, "create_g07")

    def _create_g07(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            run = session.get(MigrationRunModel, continuation.run_id)
            stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
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
                stage_plan.version,
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
            package.plan_version = context[4]

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
                self._block(continuation, "ANGULAR_UPDATE_EVIDENCE_MISSING", "Angular update execution is missing")
                return
            if prompt is None:
                if execution.status == "succeeded":
                    step.status = "PASSED"
                    step.completed_at = datetime.now(UTC)
                    self._queue(continuation, "target_inspection")
                else:
                    step.status = "FAILED"
                    step.completed_at = datetime.now(UTC)
                    continuation.last_error_code = execution.failure_code or "ANGULAR_UPDATE_FAILED"
                    continuation.last_error_message = execution.failure_message or "Angular update failed without a governed prompt"
                    self._queue(continuation, "classify_failure")
                return
            checkpoint = session.get(StageCheckpointModel, prompt.reconstruction_checkpoint_id)
            binding = self._stage._binding(session, continuation)
            run = session.get(MigrationRunModel, continuation.run_id)
            reconstruction = (
                checkpoint.workspace_path,
                binding.workspace_path,
                (run.workspace_aliases or {})["STAGE_SANDBOX"],
                checkpoint.workspace_fingerprint,
            )
            prompt_id = prompt.id
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
            binding.workspace_fingerprint = observed
            binding.last_verified_fingerprint = observed
            binding.last_verified_at = datetime.now(UTC)
            prompt.observed_fingerprint = observed
            prompt.status = "waiting_human"
            continuation.status = "waiting_prompt"
            continuation.current_node = "wait_prompt_decision"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.state_version += 1
            continuation.updated_at = datetime.now(UTC)

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
                    continuation,
                    "ANGULAR_UPDATE_EVIDENCE_MISSING",
                    "Angular update execution or reconstruction checkpoint is missing",
                )
                return
            if version_execution is None or version_execution.status != "succeeded":
                self._block(
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
                self._block(self._owned(session, continuation_id, worker_id), error.code, error.message)
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
            binding.last_verified_fingerprint = context["workspace_fingerprint"]
            binding.last_verified_at = datetime.now(UTC)
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
                self._validation_failure(continuation, error)

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
                self._validation_failure(continuation, error)

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
                self._validation_failure(continuation, error)

    def _aggregate_validation(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            try:
                payload, artifact_root = self._validation.aggregate(session, continuation)
            except ValidationRunnerError as error:
                self._validation_failure(continuation, error)
                return
            repair = session.query(RepairAttemptModel).filter_by(
                run_id=continuation.run_id, stage_id=continuation.current_stage_id
            ).order_by(RepairAttemptModel.attempt_number.desc()).first()
            gate_id = "G11" if repair and repair.status in {"applied", "revalidating"} else "G09"
        summary = self._validation.write_summary(payload, artifact_root)
        gate_payload = {
            "gate_id": gate_id,
            **payload,
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
            if gate_id == "G11":
                repair = session.query(RepairAttemptModel).filter_by(
                    run_id=continuation.run_id, stage_id=continuation.current_stage_id
                ).order_by(RepairAttemptModel.attempt_number.desc()).first()
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

    def _classify_failure(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
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
                        StageCheckpointModel.stage_id == continuation.current_stage_id,
                        StageCheckpointModel.kind == "pre_repair",
                    )
                    .order_by(StageCheckpointModel.sequence.desc())
                    .limit(1)
                )
        evidence["workspace_fingerprint"] = StageSandboxCopier.fingerprint(
            Path(str(evidence["workspace_path"]))
        )
        route = self._failures.classify(evidence)
        attempt_artifacts: list[StoredArtifact] = []
        if replayed is None:
            failure, route_artifact = self._failures.write(evidence, route)
            attempt_artifacts.extend((failure, route_artifact))
            context = (
                self._failures.write_context_pack(evidence, failure.ref.checksum)
                if route.value == "repairable_source"
                else None
            )
            if context is not None:
                attempt_artifacts.append(context)
        else:
            failure, route_artifact, context = replayed
        snapshot = None
        if (
            route.value == "repairable_source"
            and context is not None
            and (replayed is None or reuse_checkpoint is None)
        ):
            snapshot = self._stage.snapshot_workspace(
                str(evidence["workspace_path"]),
                str(Path(str(evidence["workspace_path"])).parent),
                str(evidence["stage_id"]),
            )
        try:
            with self._scope() as session:
                continuation = self._owned(session, continuation_id, worker_id)

                for artifact in (failure, route_artifact, context):
                    if artifact is not None:
                        self._stage.register_artifact(session, artifact, continuation)
                if self._is_angular_update_failure(session, continuation):
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
                    if route.value != "repairable_source":
                        self._block(
                            continuation,
                            f"ANGULAR_UPDATE_{route.value.upper()}",
                            f"Angular update failure routed to {route.value}",
                        )
                        return

                if route.value != "repairable_source":
                    if route.value == "environment_transient" and continuation.attempt < continuation.max_attempts:
                        continuation.attempt += 1
                        continuation.status = "waiting_retry"
                        continuation.current_node = "final_install"
                        continuation.next_attempt_at = datetime.now(UTC) + timedelta(seconds=30)
                        continuation.worker_id = None
                        continuation.lease_expires_at = None
                        continuation.state_version += 1
                        continuation.updated_at = datetime.now(UTC)
                    else:
                        self._block(
                            continuation,
                            f"FAILURE_ROUTE_{route.value.upper()}",
                            f"Validation failure routed to {route.value}",
                        )
                    return
                attempts = session.query(RepairAttemptModel).filter_by(
                    run_id=continuation.run_id, stage_id=continuation.current_stage_id
                ).count()
                applied = session.query(RepairAttemptModel).filter(
                    RepairAttemptModel.run_id == continuation.run_id,
                    RepairAttemptModel.stage_id == continuation.current_stage_id,
                    RepairAttemptModel.apply_ledger_artifact_id.is_not(None),
                ).count()
                if attempts >= 3 or applied >= 2:
                    self._block(
                        continuation,
                        "REPAIR_ATTEMPT_LIMIT",
                        "Governed repair attempt limit reached",
                    )
                    return
                if reuse_checkpoint is None and snapshot is None:
                    self._block(
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

    def _propose_repair(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            attempt_id = attempt.id
        try:
            proposal = self._repairs.propose(attempt_id)
        except (ArtifactNotFoundError, ArtifactStoreError) as error:
            with self._scope() as session:
                self._block(
                    self._owned(session, continuation_id, worker_id),
                    "REPAIR_EVIDENCE_MISSING",
                    str(error),
                )
            return
        except (RepairLlmError, RepairApplicationError, ValueError) as error:
            with self._scope() as session:
                self._block(
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
            attempt_id = self._latest_repair(session, continuation).id
        try:
            review = self._repairs.review(attempt_id)
        except (ArtifactNotFoundError, ArtifactStoreError) as error:
            with self._scope() as session:
                self._block(
                    self._owned(session, continuation_id, worker_id),
                    "REPAIR_EVIDENCE_MISSING",
                    str(error),
                )
            return
        except (RepairLlmError, RepairApplicationError, ValueError) as error:
            with self._scope() as session:
                self._block(
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
            if review["decision"] == "request_changes" and attempt.attempt_number < 3:
                next_attempt = RepairAttemptModel(
                    id=f"repair-{continuation.current_stage_id}-{attempt.attempt_number + 1}",
                    run_id=attempt.run_id,
                    stage_id=attempt.stage_id,
                    attempt_number=attempt.attempt_number + 1,
                    status="evidence_frozen",
                    risk_level="unknown",
                    diagnosis=attempt.diagnosis,
                    failure_evidence_artifact_id=attempt.failure_evidence_artifact_id,
                    failure_evidence_checksum=attempt.failure_evidence_checksum,
                    failure_route_artifact_id=attempt.failure_route_artifact_id,
                    failure_route_checksum=attempt.failure_route_checksum,
                    context_pack_artifact_id=attempt.context_pack_artifact_id,
                    context_pack_checksum=attempt.context_pack_checksum,
                    pre_fingerprint=attempt.pre_fingerprint,
                    failure_fingerprint=attempt.failure_fingerprint,
                    parent_attempt_id=attempt.id,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                session.add(next_attempt)
                self._queue(continuation, "propose_repair")
                return
            self._block(
                continuation,
                "REPAIR_REVIEW_REJECTED",
                "Repair reviewer rejected the candidate",
            )

    def _create_repair_gate(
        self, continuation_id: str, worker_id: str, gate_id: str
    ) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            binding = self._stage._binding(session, continuation)
            run = session.get(MigrationRunModel, continuation.run_id)
            payload = {
                "gate_id": gate_id,
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
                "stage_plan_checksum": continuation.stage_plan_checksum,
                "workspace_fingerprint": binding.workspace_fingerprint,
                "failure_evidence_checksum": attempt.failure_evidence_checksum,
                "context_pack_checksum": attempt.context_pack_checksum,
                "proposal_checksum": attempt.proposal_checksum,
                "review_checksum": attempt.review_checksum,
                "repair_attempt_id": attempt.id,
                "proposal_artifact_id": attempt.proposal_artifact_id,
                "review_artifact_id": attempt.review_artifact_id,
                "proposer_invocation_id": attempt.proposer_invocation_id,
                "reviewer_invocation_id": attempt.reviewer_invocation_id,
                "workspace_binding_id": binding.id,
                "workspace_path": binding.workspace_path,
                "risk_level": attempt.risk_level,
                "validation_targets": [],
            }
            if gate_id == "G10":
                proposal_metadata = session.get(
                    ArtifactMetadataModel, "metadata-" + str(attempt.proposal_artifact_id)
                )
                if proposal_metadata is None:
                    raise TransformerStageError("REPAIR_PROPOSAL_MISSING", "Repair proposal artifact is missing")
                proposal = json.loads(
                    LocalFilesystemArtifactStore(
                        Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
                    ).read_artifact(continuation.run_id, proposal_metadata.relative_path).content
                )
                payload["validation_targets"] = list(proposal.get("validation_targets") or [])
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
            package = self._gates.create(
                session,
                continuation,
                gate_id=gate_id,
                package_artifact_id=gate.ref.artifact_id,
                package_checksum=gate.ref.checksum,
                artifact_set_checksum=self._stage.checksum(
                    {gate.ref.artifact_id: gate.ref.checksum}
                ),
                workspace_fingerprint=context[1],
            )
            if gate_id == "G10":
                attempt.g10_gate_package_id = package.id
                attempt.status = "waiting_g10"
                attempt.updated_at = datetime.now(UTC)

    def _apply_repair(self, continuation_id: str, worker_id: str) -> None:
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
                    StageGatePackageModel.status == "approved",
                ).order_by(StageGatePackageModel.gate_version.desc())
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
            self._gates._validate_repair_lineage(session, continuation, gate.package_artifact_id, gate.package_checksum)
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
            checkpoint = session.scalar(
                select(StageCheckpointModel)
                .where(
                    StageCheckpointModel.stage_id == continuation.current_stage_id,
                    StageCheckpointModel.kind == "pre_repair",
                )
                .order_by(StageCheckpointModel.sequence.desc())
            )
            recovering = attempt.status == "applying"
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
                "checkpoint_path": checkpoint.workspace_path,
                "checkpoint_fingerprint": checkpoint.workspace_fingerprint,
                "stage_root": (run.workspace_aliases or {})["STAGE_SANDBOX"],
            }
            attempt.status = "applying"
            attempt.updated_at = datetime.now(UTC)
        if recovering:
            context["fingerprint"] = self._stage.reconstruct_workspace(
                context["checkpoint_path"],
                context["workspace_path"],
                context["stage_root"],
                context["checkpoint_fingerprint"],
            )
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
                or current_attempt.status != "applying"
                or current_binding.id != context["workspace_binding_id"]
            ):
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved repair authority changed")
            if current_binding.workspace_path != context["workspace_path"]:
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved workspace binding changed")
            live = StageSandboxCopier.fingerprint(Path(current_binding.workspace_path))
            if live != current_binding.workspace_fingerprint or live != context["fingerprint"]:
                raise TransformerStageError("REPAIR_PROPOSAL_STALE", "Approved workspace fingerprint changed")
            self._gates._validate_repair_lineage(
                session, current, current_gate.package_artifact_id, current_gate.package_checksum
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
                    RepairAttemptModel.status == "applying",
                    RepairAttemptModel.proposal_artifact_id == current_attempt.proposal_artifact_id,
                    RepairAttemptModel.proposal_checksum == current_attempt.proposal_checksum,
                )
                .values(updated_at=datetime.now(UTC))
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
            proposal = json.loads(proposal_artifact.content)
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
                    self._owned(session, continuation_id, worker_id),
                    error.code,
                    error.message,
                )
            return
        prepared, ledger, fingerprint = apply_result
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            binding = self._stage._binding(session, continuation)
            for artifact in (prepared, ledger):
                self._stage.register_artifact(session, artifact, continuation)
            attempt.apply_ledger_artifact_id = ledger.ref.artifact_id
            attempt.apply_ledger_checksum = ledger.ref.checksum
            attempt.post_fingerprint = fingerprint
            attempt.status = "applied"
            attempt.updated_at = datetime.now(UTC)
            binding.workspace_fingerprint = fingerprint
            binding.last_verified_fingerprint = fingerprint
            binding.last_verified_at = datetime.now(UTC)
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
            self._queue(continuation, "repair_revalidate")

    def _start_revalidation(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            if attempt.status in {"applied", "revalidating_affected"}:
                run = session.get(MigrationRunModel, continuation.run_id)
                metadata = session.get(ArtifactMetadataModel, "metadata-" + str(attempt.proposal_artifact_id))
                if run is None or metadata is None or metadata.checksum != attempt.proposal_checksum:
                    self._block(continuation, "REPAIR_PROPOSAL_STALE", "Bound repair proposal is missing or stale")
                    return
                try:
                    proposal = RepairProposal.model_validate(
                        json.loads(
                            LocalFilesystemArtifactStore(
                                Path(run.artifact_root).parent, fixed_run_root=Path(run.artifact_root)
                            ).read_artifact(continuation.run_id, metadata.relative_path).content
                        )
                    ).model_dump(mode="json")
                except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError) as error:
                    self._block(continuation, "REPAIR_PROPOSAL_STALE", "Bound repair proposal cannot be verified")
                    return
                targets = list(proposal.get("validation_targets") or [])
                mapping = {"build": "builds", "test": "tests", "lint": "lint"}
                group = mapping.get(targets[0] if targets else "")
                if group is None:
                    self._block(
                        continuation,
                        "REPAIR_VALIDATION_TARGET_INVALID",
                        "Repair proposal has no approved affected validation target",
                    )
                    return
                if attempt.status == "applied":
                    attempt.status = "revalidating_affected"
                    attempt.updated_at = datetime.now(UTC)
                try:
                    outcome = self._validation.advance_group(
                        session,
                        continuation,
                        group,
                        next_node="repair_revalidate",
                        attempt_key=f"{attempt.id}:affected",
                    )
                except ValidationRunnerError as error:
                    self._validation_failure(continuation, error)
                    return
                if outcome != "passed":
                    return
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

    def _create_g09_from_repair(self, continuation_id: str, worker_id: str) -> None:
        with self._scope() as session:
            continuation = self._owned(session, continuation_id, worker_id)
            attempt = self._latest_repair(session, continuation)
            binding = self._stage._binding(session, continuation)
            run = session.get(MigrationRunModel, continuation.run_id)
            payload = {
                "gate_id": "G09",
                "run_id": continuation.run_id,
                "stage_id": continuation.current_stage_id,
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
    def _is_angular_update_failure(session, continuation) -> bool:
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.name == "angular_update-0",
                StageStepModel.status == "FAILED",
            )
        )
        return step is not None

    def _restore_angular_update_checkpoint(self, session, continuation):
        checkpoint = session.scalar(
            select(StageCheckpointModel).where(
                StageCheckpointModel.stage_id == continuation.current_stage_id,
                StageCheckpointModel.kind == "pre_angular_update",
            ).order_by(StageCheckpointModel.sequence.desc())
        )
        if checkpoint is None:
            raise TransformerStageError(
                "CHECKPOINT_MISSING",
                "No pre_angular_update checkpoint available for recovery",
            )
        binding = self._stage._binding(session, continuation)
        run = session.get(MigrationRunModel, continuation.run_id)
        new_fingerprint = self._stage.reconstruct_workspace(
            checkpoint.workspace_path,
            binding.workspace_path,
            (run.workspace_aliases or {})["STAGE_SANDBOX"],
            checkpoint.workspace_fingerprint,
        )
        binding.workspace_fingerprint = new_fingerprint
        binding.last_verified_fingerprint = new_fingerprint
        binding.last_verified_at = datetime.now(UTC)
        return checkpoint.id, new_fingerprint

    @staticmethod
    def _latest_repair(session, continuation):
        attempt = (
            session.query(RepairAttemptModel)
            .filter_by(
                run_id=continuation.run_id,
                stage_id=continuation.current_stage_id,
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
            .first()
        )
        if attempt is None:
            raise TransformerStageError("REPAIR_ATTEMPT_MISSING", "Repair attempt is missing")
        return attempt

    @staticmethod
    def _validation_failure(continuation, error: ValidationRunnerError) -> None:
        continuation.status = "queued"
        continuation.current_node = "classify_failure"
        continuation.last_error_code = error.code
        continuation.last_error_message = error.message
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = datetime.now(UTC)

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
        return attempt.id if attempt and attempt.status in {"applied", "revalidating"} else "initial"

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
                        "revalidating",
                        "revalidating_affected",
                    )
                ),
            ):
                repair.status = "cancelled"
                repair.updated_at = datetime.now(UTC)
            continuation.status = "cancelled"
            continuation.current_node = "terminal"
            continuation.worker_id = None
            continuation.lease_expires_at = None
            continuation.completed_at = datetime.now(UTC)
            continuation.updated_at = continuation.completed_at
            continuation.state_version += 1

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
    def _block(continuation, code: str, message: str) -> None:
        continuation.status = "blocked"
        continuation.last_error_code = code
        continuation.last_error_message = message
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = datetime.now(UTC)


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
