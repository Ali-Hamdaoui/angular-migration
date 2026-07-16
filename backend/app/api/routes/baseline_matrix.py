"""S1-F12 baseline target inventory and validation endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from app.api.baseline_matrix_contracts import BaselineMatrixKind, BaselineTargetInventoryResponse, BaselineValidationRequest, BaselineValidationResponse
from app.services.baseline_validation_application_service import BaselineValidationApplicationError, BaselineValidationApplicationService
router = APIRouter(prefix="/runs", tags=["baseline-validation"])
def get_service() -> BaselineValidationApplicationService: return BaselineValidationApplicationService()
def _raise(error: BaselineValidationApplicationError): raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message})
@router.get("/{run_id}/baseline/targets", response_model=BaselineTargetInventoryResponse)
def get_targets(run_id: str, service: BaselineValidationApplicationService = Depends(get_service)):
    try: return service.get_targets(run_id)
    except BaselineValidationApplicationError as error: _raise(error)
@router.get("/{run_id}/baseline/{kind}", response_model=BaselineValidationResponse)
def get_validation(run_id: str, kind: BaselineMatrixKind, service: BaselineValidationApplicationService = Depends(get_service)):
    result = service.get(run_id, kind)
    if result is None: raise HTTPException(status_code=404, detail={"error_code": "BASELINE_VALIDATION_NOT_FOUND", "message": "Baseline validation was not found."})
    return result
def _execute(run_id: str, kind: BaselineMatrixKind, request: BaselineValidationRequest, service: BaselineValidationApplicationService):
    try: return service.execute(run_id, kind, request)
    except BaselineValidationApplicationError as error: _raise(error)
@router.post("/{run_id}/baseline/{kind}/cancel", response_model=BaselineValidationResponse)
def cancel_validation(run_id: str, kind: BaselineMatrixKind, service: BaselineValidationApplicationService = Depends(get_service)):
    try: return service.cancel(run_id, kind)
    except BaselineValidationApplicationError as error: _raise(error)

@router.post("/{run_id}/baseline/builds", response_model=BaselineValidationResponse)
def execute_builds(run_id: str, request: BaselineValidationRequest, service: BaselineValidationApplicationService = Depends(get_service)): return _execute(run_id, "build", request, service)
@router.post("/{run_id}/baseline/tests", response_model=BaselineValidationResponse)
def execute_tests(run_id: str, request: BaselineValidationRequest, service: BaselineValidationApplicationService = Depends(get_service)): return _execute(run_id, "test", request, service)
@router.post("/{run_id}/baseline/lint", response_model=BaselineValidationResponse)
def execute_lint(run_id: str, request: BaselineValidationRequest, service: BaselineValidationApplicationService = Depends(get_service)): return _execute(run_id, "lint", request, service)
