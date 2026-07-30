"""Read and cancel the authoritative Transformer workflow."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.authentication import authenticated_actor, authorize_run
from app.api.errors import error_response
from app.domain.transformation import (
    StageGateDecisionRequest,
    TransformationCancelRequest,
    TransformationRestartRequest,
)
from app.repositories.models import (
    CommandExecutionModel,
    MigrationStageModel,
    StageCheckpointModel,
    StageGateDecisionModel,
    StageGatePackageModel,
    StagePromptRequestModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.repositories.session import session_scope
from app.services.transformation_continuation_service import (
    TransformationContinuationError,
    TransformationContinuationService,
)
from app.services.stage_gate_service import StageGateError, StageGateService
from app.services.command_executor_service import CommandExecutorService
from app.services.stage_preparation_primitives import StageSandboxCopier

router = APIRouter(prefix="/runs", tags=["transformation"])


def _projection(session, continuation: TransformationContinuationModel) -> dict[str, object]:
    stage = session.get(MigrationStageModel, continuation.current_stage_id)
    checkpoint = session.scalar(
        select(StageCheckpointModel)
        .where(StageCheckpointModel.stage_id == continuation.current_stage_id)
        .order_by(StageCheckpointModel.sequence.desc())
        .limit(1)
    )
    command = session.scalar(
        select(CommandExecutionModel)
        .where(CommandExecutionModel.run_id == continuation.run_id)
        .order_by(CommandExecutionModel.requested_at.desc())
        .limit(1)
    )
    gate = session.scalar(
        select(StageGatePackageModel)
        .where(
            StageGatePackageModel.stage_id == continuation.current_stage_id,
            StageGatePackageModel.status.in_(("pending", "approved", "rejected")),
        )
        .order_by(StageGatePackageModel.gate_version.desc())
        .limit(1)
    )
    prompt = session.scalar(
        select(StagePromptRequestModel)
        .where(
            StagePromptRequestModel.stage_id == continuation.current_stage_id,
            StagePromptRequestModel.status.not_in(("decided", "cancelled", "stale")),
        )
        .order_by(StagePromptRequestModel.created_at.desc())
        .limit(1)
    )
    return {
        "run_id": continuation.run_id,
        "continuation_id": continuation.id,
        "stage_id": continuation.current_stage_id,
        "status": continuation.status,
        "current_node": continuation.current_node,
        "state_version": continuation.state_version,
        "stage_status": stage.status if stage else "missing",
        "source_version": stage.source_version_family if stage else None,
        "target_version": stage.target_version_family if stage else None,
        "checkpoint_kind": checkpoint.kind if checkpoint else None,
        "workspace_fingerprint": checkpoint.workspace_fingerprint if checkpoint else None,
        "active_gate": gate.gate_id if gate else None,
        "active_gate_package_checksum": gate.package_checksum if gate else None,
        "active_command_id": command.id if command else None,
        "active_command_status": command.status if command else None,
        "active_prompt_id": prompt.id if prompt else None,
        "last_error_code": continuation.last_error_code,
        "cancel_requested_at": continuation.cancel_requested_at,
    }


@router.get("/{run_id}/transformation")
def get_transformation(
    run_id: str,
    request: Request,
    actor: str = Depends(authenticated_actor),
):
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        if continuation is None:
            return error_response(
                request,
                status_code=404,
                error_code="TRANSFORMATION_NOT_FOUND",
                message="Transformer continuation has not been created",
            )
        return _projection(session, continuation)


@router.post("/{run_id}/transformation/gates/{gate_id}/decisions")
def decide_stage_gate(
    run_id: str,
    gate_id: str,
    body: StageGateDecisionRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
):
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        if continuation is None:
            return error_response(
                request,
                status_code=404,
                error_code="TRANSFORMATION_NOT_FOUND",
                message="Transformer continuation has not been created",
            )
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        if binding is None:
            return error_response(
                request,
                status_code=409,
                error_code="STAGE_WORKSPACE_MISSING",
                message="Prepared stage workspace binding is missing",
            )
        workspace_path = binding.workspace_path
        replay = session.scalar(
            select(StageGateDecisionModel.id).where(
                StageGateDecisionModel.run_id == run_id,
                StageGateDecisionModel.idempotency_key == body.idempotency_key,
            )
        ) is not None
    try:
        observed_fingerprint = StageSandboxCopier.fingerprint(Path(workspace_path))
    except OSError:
        return error_response(
            request,
            status_code=409,
            error_code="STAGE_WORKSPACE_MISSING",
            message="Prepared stage workspace is unavailable",
        )
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        try:
            decision = StageGateService().decide(
                session,
                continuation,
                gate_id.upper(),
                body,
                actor=actor,
                observed_workspace_fingerprint=observed_fingerprint,
            )
        except (StageGateError, ValueError) as error:
            return error_response(
                request,
                status_code=409,
                error_code=getattr(error, "code", "GATE_ID_INVALID"),
                message=getattr(error, "message", str(error)),
            )
        return {
            "decision_id": decision.id,
            "gate_id": decision.gate_id,
            "decision": decision.decision,
            "accepted": decision.accepted,
            "state_version": continuation.state_version,
            "idempotent_replay": replay,
        }


@router.post("/{run_id}/transformation/cancel")
def cancel_transformation(
    run_id: str,
    body: TransformationCancelRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
):
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        if continuation is None:
            return error_response(
                request,
                status_code=404,
                error_code="TRANSFORMATION_NOT_FOUND",
                message="Transformer continuation has not been created",
            )
        try:
            TransformationContinuationService().request_cancel(
                session,
                continuation.id,
                actor=actor,
                idempotency_key=body.idempotency_key,
                expected_state_version=body.expected_state_version,
            )
            active = session.scalar(
                select(CommandExecutionModel).where(
                    CommandExecutionModel.run_id == run_id,
                    CommandExecutionModel.status.in_(("queued", "pending", "running")),
                )
            )
            if active is not None:
                CommandExecutorService().request_cancel(
                    session,
                    run_id,
                    active.id,
                    actor,
                    idempotency_key=f"{body.idempotency_key}:command",
                )
        except TransformationContinuationError as error:
            return error_response(
                request,
                status_code=409,
                error_code=error.code,
                message=error.message,
            )
        return _projection(session, continuation)


@router.post("/{run_id}/transformation/restart")
def restart_transformation(
    run_id: str,
    body: TransformationRestartRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
):
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        continuation = session.scalar(
            select(TransformationContinuationModel).where(
                TransformationContinuationModel.run_id == run_id
            )
        )
        if continuation is None:
            return error_response(
                request,
                status_code=404,
                error_code="TRANSFORMATION_NOT_FOUND",
                message="Transformer continuation has not been created",
            )
        replay = session.scalar(
            select(WorkflowEventModel).where(
                WorkflowEventModel.run_id == run_id,
                WorkflowEventModel.idempotency_key == body.idempotency_key,
                WorkflowEventModel.event_type == "TRANSFORMATION_CONTINUATION_RESUMED",
            )
        )
        if replay is not None:
            if (replay.payload or {}).get("expected_state_version") != body.expected_state_version:
                return error_response(
                    request,
                    status_code=409,
                    error_code="IDEMPOTENCY_PAYLOAD_MISMATCH",
                    message="Restart key was already used with a different payload",
                )
            return _projection(session, continuation)
        if continuation.state_version != body.expected_state_version:
            return error_response(
                request,
                status_code=409,
                error_code="TRANSFORMATION_STATE_CONFLICT",
                message="Transformer state changed; refresh authoritative state",
            )
        try:
            TransformationContinuationService().wake(session, continuation.id)
        except TransformationContinuationError as error:
            return error_response(
                request,
                status_code=409,
                error_code=error.code,
                message=error.message,
            )
        from app.domain.contracts import WorkflowEventType
        from app.state import StateTransitionService

        StateTransitionService(session).append_audit_event(
            run_id=run_id,
            idempotency_key=body.idempotency_key,
            event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED,
            actor=actor,
            reason="operator restarted Transformer from durable state",
            occurred_at=continuation.updated_at,
            payload={
                "continuation_id": continuation.id,
                "expected_state_version": body.expected_state_version,
            },
        )
        return _projection(session, continuation)
