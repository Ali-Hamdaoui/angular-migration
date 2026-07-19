"""S3-F11 stage build matrix endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from app.api.stage_build_contracts import StageBuildRequest, StageBuildResponse
from app.services.stage_build_application_service import (
    StageBuildApplicationError,
    StageBuildApplicationService,
)

router = APIRouter(prefix="/runs", tags=["stage-build"])


def get_service() -> StageBuildApplicationService:
    return StageBuildApplicationService()


def _raise(error: StageBuildApplicationError):
    raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message})


@router.post("/{run_id}/stages/{stage_id}/builds", response_model=StageBuildResponse)
def execute_build(
    run_id: str,
    stage_id: str,
    request: StageBuildRequest,
    service: StageBuildApplicationService = Depends(get_service),
):
    try:
        return service.execute_build(run_id, stage_id, request)
    except StageBuildApplicationError as error:
        _raise(error)


@router.get("/{run_id}/stages/{stage_id}/builds", response_model=StageBuildResponse)
def get_build(
    run_id: str,
    stage_id: str,
    service: StageBuildApplicationService = Depends(get_service),
):
    result = service.get_build(run_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error_code": "STAGE_BUILD_NOT_FOUND", "message": "Stage build was not found."})
    return result
