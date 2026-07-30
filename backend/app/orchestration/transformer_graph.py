"""Pointer-only LangGraph for the durable Transformer state machine."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import select

from app.repositories.models import (
    ActivePlanVersionModel,
    CommandLogChunkModel,
    CommandExecutionModel,
    G06ApprovalModel,
    MigrationRunModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
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
from app.services.stage_gate_service import StageGateService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.prompt_explanation_service import PromptExplanationService
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService


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
    ) -> None:
        self._scope = scope
        self._stage = stage_service or TransformerStageService(scope=scope)
        self._gates = gate_service or StageGateService()
        self._evidence = transformation_evidence or AngularTransformationEvidenceService()
        self._prompt_explainer = prompt_explainer or PromptExplanationService(scope=scope)

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
                self._stage.queue_bootstrap(session, self._owned(session, continuation_id, worker_id))
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
                    self._block(
                        continuation,
                        execution.failure_code or "ANGULAR_UPDATE_FAILED",
                        execution.failure_message or "Angular update failed without a governed prompt",
                    )
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
