"""Read and cancel the authoritative Transformer workflow."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.authentication import authenticated_actor, authorize_run
from app.api.errors import error_response
from app.domain.transformation import TransformationCancelRequest
from app.repositories.models import (
    CommandExecutionModel,
    MigrationStageModel,
    StageCheckpointModel,
    StageGatePackageModel,
    StagePromptRequestModel,
    TransformationContinuationModel,
)
from app.repositories.session import session_scope
from app.services.transformation_continuation_service import (
    TransformationContinuationError,
    TransformationContinuationService,
)

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
        .where(
            CommandExecutionModel.run_id == continuation.run_id,
            CommandExecutionModel.status.in_(("queued", "pending", "running", "interrupted")),
        )
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
        except TransformationContinuationError as error:
            return error_response(
                request,
                status_code=409,
                error_code=error.code,
                message=error.message,
            )
        return _projection(session, continuation)
