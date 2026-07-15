"""S1-F10 baseline workspace and prequalification endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.baseline_contracts import BaselineInstallAuthorizationRequest, BaselinePrequalifyRequest, BaselineResponse, BaselineWorkspaceRequest
from app.services.baseline_application_service import BaselineApplicationError, BaselineApplicationService

router = APIRouter(prefix="/runs", tags=["baseline"])


def get_baseline_service() -> BaselineApplicationService:
    return BaselineApplicationService()


def _raise(error: BaselineApplicationError):
    raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message})


@router.get("/{run_id}/baseline", response_model=BaselineResponse)
def get_baseline(run_id: str, service: BaselineApplicationService = Depends(get_baseline_service)):
    result = service.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error_code": "BASELINE_NOT_FOUND", "message": "Baseline record not found."})
    return result


@router.post("/{run_id}/baseline/workspace", response_model=BaselineResponse)
def create_baseline_workspace(run_id: str, request: BaselineWorkspaceRequest, service: BaselineApplicationService = Depends(get_baseline_service)):
    try:
        return service.create_workspace(run_id, request)
    except BaselineApplicationError as error:
        _raise(error)


@router.post("/{run_id}/baseline/prequalify", response_model=BaselineResponse)
def prequalify_baseline(run_id: str, request: BaselinePrequalifyRequest, service: BaselineApplicationService = Depends(get_baseline_service)):
    try:
        return service.prequalify(run_id, request)
    except BaselineApplicationError as error:
        _raise(error)


@router.post("/{run_id}/baseline/install-authorizations", response_model=BaselineResponse)
def authorize_baseline_install(run_id: str, request: BaselineInstallAuthorizationRequest, service: BaselineApplicationService = Depends(get_baseline_service)):
    try:
        return service.authorize_install(run_id, request)
    except BaselineApplicationError as error:
        _raise(error)
