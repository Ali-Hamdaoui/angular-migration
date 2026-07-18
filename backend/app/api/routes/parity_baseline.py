from fastapi import APIRouter, Depends, Request
from app.api.errors import error_response
from app.api.parity_baseline_contracts import ParityBaselineCaptureRequest, ParityBaselineResponse
from app.services.parity_baseline_evidence_application_service import (
    ParityBaselineEvidenceApplicationService,
    ParityBaselineEvidenceError,
)

router = APIRouter(prefix="/runs", tags=["parity-baseline"])


def service():
    return ParityBaselineEvidenceApplicationService()


@router.post("/{run_id}/discovery/parity-baseline", response_model=ParityBaselineResponse)
def capture(run_id: str, request: ParityBaselineCaptureRequest, http_request: Request, s=Depends(service)):
    try:
        return s.capture(run_id, request)
    except ParityBaselineEvidenceError as error:
        return error_response(http_request, status_code=error.status_code, error_code=error.code, message=error.message)


@router.get("/{run_id}/discovery/parity-baseline", response_model=ParityBaselineResponse)
def get(run_id: str, http_request: Request, s=Depends(service)):
    return s.get(run_id) or error_response(
        http_request,
        status_code=404,
        error_code="PARITY_BASELINE_NOT_FOUND",
        message="Parity baseline evidence was not found.",
    )
