from fastapi import APIRouter, Depends, Request

from app.api.authentication import authenticated_actor
from app.api.errors import error_response
from app.api.stage_execution_contracts import StageStartRequest, StageStartResponse
from app.services.stage_execution_application_service import StageExecutionApplicationService, StageExecutionError

router = APIRouter(tags=["stage-execution"])


def get_service():
    return StageExecutionApplicationService()


@router.post("/runs/{run_id}/stages/{stage_id}/start", response_model=StageStartResponse)
def start_stage(run_id: str, stage_id: str, payload: StageStartRequest, request: Request, actor: str = Depends(authenticated_actor), service: StageExecutionApplicationService = Depends(get_service)):
    try:
        return service.start(run_id, stage_id, payload, actor)
    except StageExecutionError as error:
        return error_response(request, status_code=error.status_code, error_code=error.code, message=error.message)
