"""S3-F12 stage tests and conditional lint endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from app.api.stage_tests_contracts import StageTestRequest, StageTestResponse
from app.services.stage_tests_application_service import (
    StageTestApplicationError,
    StageTestApplicationService,
)

router = APIRouter(prefix="/runs", tags=["stage-tests"])


def get_service() -> StageTestApplicationService:
    return StageTestApplicationService()


def _raise(error: StageTestApplicationError):
    raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message})


@router.post("/{run_id}/stages/{stage_id}/tests", response_model=StageTestResponse)
def execute_tests(
    run_id: str,
    stage_id: str,
    request: StageTestRequest,
    service: StageTestApplicationService = Depends(get_service),
):
    try:
        return service.execute_tests(run_id, stage_id, request)
    except StageTestApplicationError as error:
        _raise(error)


@router.get("/{run_id}/stages/{stage_id}/tests", response_model=StageTestResponse)
def get_tests(
    run_id: str,
    stage_id: str,
    service: StageTestApplicationService = Depends(get_service),
):
    result = service.get_results(run_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error_code": "STAGE_TESTS_NOT_FOUND", "message": "Stage tests were not found."})
    return result
