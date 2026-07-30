"""Pointer-only LangGraph for the durable Transformer state machine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import select

from app.repositories.models import (
    ActivePlanVersionModel,
    ArtifactMetadataModel,
    CommandExecutionModel,
    G06ApprovalModel,
    MigrationRunModel,
    StageExecutionPlanModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.session import session_scope
from app.services.stage_gate_service import StageGateService
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService


class TransformerPointer(TypedDict):
    continuation_id: str
    worker_id: str


class TransformerOrchestrator:
    def __init__(self, *, scope=session_scope, stage_service=None, gate_service=None) -> None:
        self._scope = scope
        self._stage = stage_service or TransformerStageService(scope=scope)
        self._gates = gate_service or StageGateService()

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
