"""S3-F13 stage assurance and G09 gate endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from app.api.stage_assurance_contracts import (
    AssuranceRequest,
    AssuranceResponse,
    G09GateResponse,
    G09DecisionRequest,
)
from app.services.stage_assurance_application_service import (
    StageAssuranceApplicationError,
    StageAssuranceApplicationService,
)

router = APIRouter(prefix="/runs", tags=["stage-assurance"])
approval_router = APIRouter(prefix="/approvals", tags=["stage-approvals"])


def get_service() -> StageAssuranceApplicationService:
    return StageAssuranceApplicationService()


def _raise(error: StageAssuranceApplicationError):
    raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message})


@router.post("/{run_id}/stages/{stage_id}/assurance", response_model=AssuranceResponse)
def execute_assurance(
    run_id: str,
    stage_id: str,
    request: AssuranceRequest,
    service: StageAssuranceApplicationService = Depends(get_service),
):
    try:
        return service.execute_assurance(run_id, stage_id, request)
    except StageAssuranceApplicationError as error:
        _raise(error)


@router.get("/{run_id}/stages/{stage_id}/assurance", response_model=AssuranceResponse)
def get_assurance(
    run_id: str,
    stage_id: str,
    service: StageAssuranceApplicationService = Depends(get_service),
):
    result = service.get_assurance(run_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error_code": "STAGE_ASSURANCE_NOT_FOUND", "message": "Stage assurance was not found."})
    return result


@router.post("/{run_id}/stages/{stage_id}/gates/g09", response_model=G09GateResponse)
def create_g09_gate(
    run_id: str,
    stage_id: str,
    request: AssuranceRequest,
    service: StageAssuranceApplicationService = Depends(get_service),
):
    try:
        return service.create_g09_gate(run_id, stage_id, request)
    except StageAssuranceApplicationError as error:
        _raise(error)


@router.get("/{run_id}/stages/{stage_id}/gates/g09", response_model=G09GateResponse)
def get_g09_gate(
    run_id: str,
    stage_id: str,
    service: StageAssuranceApplicationService = Depends(get_service),
):
    result = service.get_g09_gate(run_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error_code": "G09_GATE_NOT_FOUND", "message": "G09 gate was not found."})
    return result


@router.post("/{run_id}/stages/{stage_id}/gates/g09/approve", response_model=G09GateResponse)
def approve_g09(
    run_id: str,
    stage_id: str,
    request: G09DecisionRequest,
    service: StageAssuranceApplicationService = Depends(get_service),
):
    try:
        return service.approve_g09(run_id, stage_id, request)
    except StageAssuranceApplicationError as error:
        _raise(error)


@router.post("/{run_id}/stages/{stage_id}/gates/g09/reject", response_model=G09GateResponse)
def reject_g09(
    run_id: str,
    stage_id: str,
    request: G09DecisionRequest,
    service: StageAssuranceApplicationService = Depends(get_service),
):
    try:
        return service.reject_g09(run_id, stage_id, request)
    except StageAssuranceApplicationError as error:
        _raise(error)
