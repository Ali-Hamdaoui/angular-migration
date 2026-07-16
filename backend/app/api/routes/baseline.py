"""Versioned baseline workspace and installation endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from app.api.baseline_contracts import BaselineInstallAuthorizationRequest, BaselineInstallCancelRequest, BaselineInstallRequest, BaselineInstallResponse, BaselinePrequalifyRequest, BaselineResponse, BaselineWorkspaceRequest
from app.services.baseline_application_service import BaselineApplicationError, BaselineApplicationService
from app.services.baseline_install_application_service import BaselineInstallApplicationError, BaselineInstallApplicationService

router = APIRouter(prefix="/runs", tags=["baseline"])
_install_service = BaselineInstallApplicationService()

def get_baseline_service() -> BaselineApplicationService: return BaselineApplicationService()
def get_baseline_install_service() -> BaselineInstallApplicationService: return _install_service
def _raise(error: BaselineApplicationError): raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message})
def _raise_install(error: BaselineInstallApplicationError): raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message})

@router.get("/{run_id}/baseline", response_model=BaselineResponse)
def get_baseline(run_id: str, service: BaselineApplicationService = Depends(get_baseline_service)):
    result = service.get(run_id)
    if result is None: raise HTTPException(status_code=404, detail={"error_code": "BASELINE_NOT_FOUND", "message": "Baseline record not found."})
    return result

@router.post("/{run_id}/baseline/workspace", response_model=BaselineResponse)
def create_baseline_workspace(run_id: str, request: BaselineWorkspaceRequest, service: BaselineApplicationService = Depends(get_baseline_service)):
    try: return service.create_workspace(run_id, request)
    except BaselineApplicationError as error: _raise(error)

@router.post("/{run_id}/baseline/prequalify", response_model=BaselineResponse)
def prequalify_baseline(run_id: str, request: BaselinePrequalifyRequest, service: BaselineApplicationService = Depends(get_baseline_service)):
    try: return service.prequalify(run_id, request)
    except BaselineApplicationError as error: _raise(error)

@router.post("/{run_id}/baseline/install-authorizations", response_model=BaselineResponse)
def authorize_baseline_install(run_id: str, request: BaselineInstallAuthorizationRequest, service: BaselineApplicationService = Depends(get_baseline_service)):
    try: return service.authorize_install(run_id, request)
    except BaselineApplicationError as error: _raise(error)

@router.post("/{run_id}/baseline/install", response_model=BaselineInstallResponse)
def install_baseline(run_id: str, request: BaselineInstallRequest, service: BaselineInstallApplicationService = Depends(get_baseline_install_service)):
    try: return service.accept(run_id, request)
    except BaselineInstallApplicationError as error: _raise_install(error)

@router.post("/{run_id}/commands/{execution_id}/cancel", response_model=BaselineInstallResponse)
def cancel_baseline(run_id: str, execution_id: str, request: BaselineInstallCancelRequest, service: BaselineInstallApplicationService = Depends(get_baseline_install_service)):
    try: return service.cancel(run_id, execution_id, request)
    except BaselineInstallApplicationError as error: _raise_install(error)

@router.get("/{run_id}/commands/{execution_id}", response_model=BaselineInstallResponse)
def get_baseline_command(run_id: str, execution_id: str, service: BaselineInstallApplicationService = Depends(get_baseline_install_service)):
    result = service.get(run_id, execution_id)
    if result is None: raise HTTPException(status_code=404, detail={"error_code": "COMMAND_EXECUTION_NOT_FOUND", "message": "Command execution was not found."})
    return result