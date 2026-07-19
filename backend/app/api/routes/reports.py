"""G15 report endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from app.api.report_contracts import ReportRequest, ReportResponse, G15DecisionRequest
from app.services.report_application_service import ReportApplicationService, ReportApplicationError

router = APIRouter(prefix="/runs", tags=["reports"])


def get_service() -> ReportApplicationService:
    return ReportApplicationService()


@router.get("/{run_id}/approvals/G15", response_model=ReportResponse)
def inspect_report(run_id: str, service: ReportApplicationService = Depends(get_service)):
    result = service.get(run_id, "G15")
    if result is None:
        raise HTTPException(status_code=404, detail="Report record not found")
    return result


@router.post("/{run_id}/reports", status_code=201, response_model=None)
def generate_report(run_id: str, request: ReportRequest, service: ReportApplicationService = Depends(get_service)):
    try:
        return service.initialize(run_id, request)
    except ReportApplicationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"error_code": e.code, "message": e.message},
        ) from e


@router.post("/{run_id}/approvals/G15/decisions", response_model=None)
def decide_g15(run_id: str, request: G15DecisionRequest, service: ReportApplicationService = Depends(get_service)):
    if request.gate_id != "G15":
        raise HTTPException(status_code=400, detail="gate_id mismatch")
    try:
        return service.decide(run_id, request)
    except ReportApplicationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"error_code": e.code, "message": e.message},
        ) from e
