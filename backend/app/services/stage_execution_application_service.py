"""Authoritative protected stage-start transition."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json

from sqlalchemy import select

from app.domain.contracts import RunStatus, WorkflowEventType
from app.repositories.models import ActivePlanVersionModel, ArtifactMetadataModel, G06ApprovalModel, MigrationPlanModel, MigrationRunModel, StageExecutionPlanModel, WorkflowEventModel
from app.repositories.session import session_scope
from app.services.planning_review_application_service import PlanRevisionService, PlanningReviewApplicationError
from app.state.transition_service import StateTransitionService, TransitionRequest


class StageExecutionError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        self.code, self.message, self.status_code = code, message, status_code
        super().__init__(message)


class StageExecutionApplicationService:
    def __init__(self, *, scope=session_scope, now_provider=None):
        self._scope = scope
        self._now = now_provider or (lambda: datetime.now(UTC))

    def start(self, run_id: str, stage_id: str, request, actor: str):
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise StageExecutionError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
            if run.actor != actor:
                raise StageExecutionError("RUN_NOT_AUTHORIZED", "The actor is not authorized for this run.", 403)
            existing = session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id, WorkflowEventModel.idempotency_key == request.idempotency_key))
            if existing:
                return self._result(run, stage_id, request, existing.sequence, True)
            pointer = session.scalar(select(ActivePlanVersionModel).where(ActivePlanVersionModel.run_id == run_id, ActivePlanVersionModel.scope == stage_id))
            if pointer is None:
                raise StageExecutionError("STAGE_PLAN_NOT_FOUND", "The requested stage has no active plan.", 404)
            plan = session.get(MigrationPlanModel, pointer.migration_plan_id)
            stage = session.get(StageExecutionPlanModel, pointer.stage_plan_id)
            gate = session.scalar(select(G06ApprovalModel).where(G06ApprovalModel.run_id == run_id, G06ApprovalModel.gate_id == "G06").order_by(G06ApprovalModel.state_version.desc(), G06ApprovalModel.created_at.desc()))
            if not plan or not stage or not gate:
                raise StageExecutionError("G06_APPROVAL_REQUIRED", "An approved current G06 gate is required before stage start.")
            checksums = {}
            for artifact_id in gate.artifact_ids or []:
                metadata = session.get(ArtifactMetadataModel, "metadata-" + artifact_id)
                if metadata is None or metadata.run_id != run_id:
                    raise StageExecutionError("G06_PACKAGE_INTEGRITY_FAILED", "A G06 artifact is unavailable.")
                checksums[artifact_id] = metadata.checksum
            aggregate = self.aggregate_artifact_checksum(checksums)
            if aggregate != request.artifact_set_checksum:
                raise StageExecutionError("ARTIFACT_SET_CHECKSUM_MISMATCH", "The current artifact set checksum is stale.")
            try:
                PlanRevisionService().require_approved_g06(gate, state_version=run.state_version, artifact_set_checksum=gate.artifact_set_checksum, plan_checksum=plan.checksum, stage_plan_checksum=stage.checksum, workspace_fingerprint=request.workspace_fingerprint)
            except PlanningReviewApplicationError as error:
                raise StageExecutionError(error.code, error.message, error.status_code) from error
            if request.expected_state_version != run.state_version:
                raise StageExecutionError("STALE_STATE_VERSION", "The run state version is stale.")
            transition = StateTransitionService(session).apply_transition(TransitionRequest(run_id=run_id, expected_state_version=request.expected_state_version, idempotency_key=request.idempotency_key, event_type=WorkflowEventType.STAGE_CREATED, next_run_status=RunStatus.STAGE_CREATED, actor=actor, reason="current G06 approval accepted for protected stage start", stage_id=stage_id, payload={"plan_checksum": plan.checksum, "stage_plan_checksum": stage.checksum, "artifact_set_checksum": aggregate}, occurred_at=self._now()))
            return self._result(run, stage_id, request, transition.event_sequence, False, transition.next_state_version, plan.checksum, stage.checksum, aggregate)

    @staticmethod
    def aggregate_artifact_checksum(checksums: dict[str, str]) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(dict(sorted(checksums.items())), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _result(run, stage_id, request, event_sequence, replay, state_version=None, plan_checksum=None, stage_checksum=None, aggregate=None):
        return {"run_id": run.id, "stage_id": stage_id, "status": RunStatus.STAGE_CREATED.value, "plan_checksum": plan_checksum or request.plan_checksum, "stage_plan_checksum": stage_checksum or request.stage_plan_checksum, "artifact_set_checksum": aggregate or request.artifact_set_checksum, "state_version": state_version or run.state_version, "event_sequence": event_sequence, "idempotent_replay": replay}
