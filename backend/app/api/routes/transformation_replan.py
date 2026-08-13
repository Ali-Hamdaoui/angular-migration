"""Thin API route for governed transformation replan recovery."""

from fastapi import APIRouter, Depends, Request

from app.api.authentication import authenticated_actor
from app.api.errors import error_response
from app.api.transformation_replan_contracts import (
    TransformationReplanRecoveryRequest,
    TransformationReplanRecoveryResponse,
)
from app.services.transformation_replan_recovery_service import (
    TransformationReplanRecoveryError,
    TransformationReplanRecoveryService,
)

router = APIRouter(tags=["transformation-replan"])


def get_service() -> TransformationReplanRecoveryService:
    return TransformationReplanRecoveryService()


@router.post(
    "/runs/{run_id}/transformation/replan-recovery",
    response_model=TransformationReplanRecoveryResponse,
)
def recover(
    run_id: str,
    payload: TransformationReplanRecoveryRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
    service: TransformationReplanRecoveryService = Depends(get_service),
):
    try:
        correlation_id = payload.correlation_id or request.headers.get("x-correlation-id")
        return service.recover(run_id, payload.model_copy(update={"correlation_id": correlation_id}), actor)
    except TransformationReplanRecoveryError as error:
        return error_response(
            request, status_code=error.status_code, error_code=error.code, message=error.message
        )
