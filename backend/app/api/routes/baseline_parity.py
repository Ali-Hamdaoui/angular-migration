from fastapi import APIRouter, Depends, HTTPException
from app.api.baseline_parity_contracts import BaselineParityCaptureRequest, BaselineParityResponse
from app.services.baseline_parity_application_service import BaselineParityApplicationError, BaselineParityApplicationService

router = APIRouter(prefix="/runs", tags=["baseline-parity"])


def get_service() -> BaselineParityApplicationService:
    return BaselineParityApplicationService()


def _raise(error: BaselineParityApplicationError):
    raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message})


@router.post("/{run_id}/baseline/parity", response_model=BaselineParityResponse)
def capture(run_id: str, request: BaselineParityCaptureRequest, service: BaselineParityApplicationService = Depends(get_service)):
    try:
        return service.capture(run_id, request)
    except BaselineParityApplicationError as error:
        _raise(error)


def _get(run_id: str, section: str, service: BaselineParityApplicationService):
    result = service.get(run_id, section)
    if result is None:
        raise HTTPException(status_code=404, detail={"error_code": "BASELINE_PARITY_NOT_FOUND", "message": "Baseline parity evidence was not found."})
    return result


@router.get("/{run_id}/baseline/failures", response_model=BaselineParityResponse)
def failures(run_id: str, service: BaselineParityApplicationService = Depends(get_service)):
    return _get(run_id, "failures", service)


@router.get("/{run_id}/baseline/routes", response_model=BaselineParityResponse)
def routes(run_id: str, service: BaselineParityApplicationService = Depends(get_service)):
    return _get(run_id, "routes", service)


@router.get("/{run_id}/baseline/backend-integration", response_model=BaselineParityResponse)
def backend_integration(run_id: str, service: BaselineParityApplicationService = Depends(get_service)):
    return _get(run_id, "backend-integration", service)


@router.get("/{run_id}/baseline/anchors", response_model=BaselineParityResponse)
def anchors(run_id: str, service: BaselineParityApplicationService = Depends(get_service)):
    return _get(run_id, "anchors", service)
