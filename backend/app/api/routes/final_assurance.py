"""G13 final-assurance endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from app.api.final_assurance_contracts import (
    FinalAssuranceRequest,
    FinalAssuranceResponse,
    G13DecisionRequest,
)
from app.services.final_assurance_application_service import (
    FinalAssuranceApplicationError,
    FinalAssuranceApplicationService,
)

router = APIRouter(prefix="/runs", tags=["approvals"])


def get_service() -> FinalAssuranceApplicationService:
    return FinalAssuranceApplicationService()


@router.get("/{run_id}/approvals/G13", response_model=FinalAssuranceResponse)
def inspect_g13(run_id: str, service: FinalAssuranceApplicationService = Depends(get_service)):
    result = service.get(run_id, "G13")
    if result is None:
        raise HTTPException(status_code=404, detail="Final assurance record not found")
    return result


@router.post("/{run_id}/final-assurance", status_code=201, response_model=None)
def run_final_assurance(run_id: str, request: FinalAssuranceRequest, service: FinalAssuranceApplicationService = Depends(get_service)):
    try:
        return service.initialize(run_id, request)
    except FinalAssuranceApplicationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"error_code": e.code, "message": e.message},
        ) from e


@router.post("/{run_id}/approvals/G13/decisions", response_model=None)
def decide_g13(run_id: str, request: G13DecisionRequest, service: FinalAssuranceApplicationService = Depends(get_service)):
    if request.gate_id != "G13":
        raise HTTPException(status_code=400, detail="gate_id mismatch")
    try:
        return service.decide(run_id, request)
    except FinalAssuranceApplicationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"error_code": e.code, "message": e.message},
        ) from e
