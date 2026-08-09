"""G02 source-integrity review endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.g02_contracts import G02DecisionRequest, G02ReviewResponse
from app.api.g02_initialization import G02PackageInitializationRequest
from app.services.g02_application_service import G02ApprovalApplicationService, G02ApplicationError

router = APIRouter(prefix="/runs", tags=["approvals"])


def get_g02_service() -> G02ApprovalApplicationService:
    return G02ApprovalApplicationService()


@router.get("/{run_id}/approvals/G02", response_model=G02ReviewResponse)
def inspect_g02(run_id: str, service: G02ApprovalApplicationService = Depends(get_g02_service)):
    result = service.get(run_id, "G02")
    if result is None:
        raise HTTPException(status_code=404, detail="G02 approval package not found")
    return result


@router.post("/{run_id}/approvals/G02/decisions", response_model=G02ReviewResponse)
def decide_g02(run_id: str, request: G02DecisionRequest, service: G02ApprovalApplicationService = Depends(get_g02_service)):
    if request.gate_id != "G02":
        raise HTTPException(status_code=400, detail="gate_id in body does not match path")
    try:
        return service.decide(run_id, request)
    except G02ApplicationError as error:
        raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message}) from error
@router.post("/{run_id}/approvals/G02/package", response_model=G02ReviewResponse)
def initialize_g02(run_id: str, request: G02PackageInitializationRequest, service: G02ApprovalApplicationService = Depends(get_g02_service)):
    if request.gate_id != "G02":
        raise HTTPException(status_code=400, detail="gate_id in body does not match path")
    try:
        return service.initialize(run_id, request)
    except G02ApplicationError as error:
        raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message}) from error
