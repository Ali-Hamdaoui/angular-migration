"""S3-F10 stage validation endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from app.api.stage_validation_contracts import StageValidationRequest, StageValidationResponse
from app.services.stage_validation_application_service import (
    StageValidationApplicationError,
    StageValidationApplicationService,
)

router = APIRouter(prefix="/runs", tags=["stage-validation"])


def get_service() -> StageValidationApplicationService:
    return StageValidationApplicationService()


def _raise(error: StageValidationApplicationError):
    raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message})


@router.post("/{run_id}/stages/{stage_id}/validation/install-static", response_model=StageValidationResponse)
def execute_install_static(
    run_id: str,
    stage_id: str,
    request: StageValidationRequest,
    service: StageValidationApplicationService = Depends(get_service),
):
    try:
        return service.execute_install_static(run_id, stage_id, request)
    except StageValidationApplicationError as error:
        _raise(error)


@router.get("/{run_id}/stages/{stage_id}/validation/install-static", response_model=StageValidationResponse)
def get_install_static(
    run_id: str,
    stage_id: str,
    service: StageValidationApplicationService = Depends(get_service),
):
    result = service.get_results(run_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error_code": "STAGE_VALIDATION_NOT_FOUND", "message": "Stage validation was not found."})
    return result
