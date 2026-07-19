"""S3-F14 stage seal (G12) and copy-forward endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from app.api.stage_seal_contracts import (
    StageSealRequest,
    StageSealResponse,
    G12GateResponse,
    G12DecisionRequest,
)
from app.services.stage_seal_application_service import (
    StageSealApplicationError,
    StageSealApplicationService,
)

router = APIRouter(prefix="/runs", tags=["stage-seal"])


def get_service() -> StageSealApplicationService:
    return StageSealApplicationService()


def _raise(error: StageSealApplicationError):
    raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message})


@router.post("/{run_id}/stages/{stage_id}/seal", response_model=StageSealResponse)
def seal_stage(
    run_id: str,
    stage_id: str,
    request: StageSealRequest,
    service: StageSealApplicationService = Depends(get_service),
):
    try:
        return service.seal_stage(run_id, stage_id, request)
    except StageSealApplicationError as error:
        _raise(error)


@router.get("/{run_id}/stages/{stage_id}/seal", response_model=StageSealResponse)
def get_seal(
    run_id: str,
    stage_id: str,
    service: StageSealApplicationService = Depends(get_service),
):
    result = service.get_seal(run_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error_code": "STAGE_SEAL_NOT_FOUND", "message": "Stage seal was not found."})
    return result


@router.post("/{run_id}/stages/{stage_id}/gates/g12", response_model=G12GateResponse)
def create_g12_gate(
    run_id: str,
    stage_id: str,
    request: StageSealRequest,
    service: StageSealApplicationService = Depends(get_service),
):
    try:
        return service.create_g12_gate(run_id, stage_id, request)
    except StageSealApplicationError as error:
        _raise(error)


@router.get("/{run_id}/stages/{stage_id}/gates/g12", response_model=G12GateResponse)
def get_g12_gate(
    run_id: str,
    stage_id: str,
    service: StageSealApplicationService = Depends(get_service),
):
    result = service.get_g12_gate(run_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error_code": "G12_GATE_NOT_FOUND", "message": "G12 gate was not found."})
    return result


@router.post("/{run_id}/stages/{stage_id}/gates/g12/approve", response_model=G12GateResponse)
def approve_g12(
    run_id: str,
    stage_id: str,
    request: G12DecisionRequest,
    service: StageSealApplicationService = Depends(get_service),
):
    try:
        return service.approve_g12(run_id, stage_id, request)
    except StageSealApplicationError as error:
        _raise(error)


@router.post("/{run_id}/stages/{stage_id}/gates/g12/reject", response_model=G12GateResponse)
def reject_g12(
    run_id: str,
    stage_id: str,
    request: G12DecisionRequest,
    service: StageSealApplicationService = Depends(get_service),
):
    try:
        return service.reject_g12(run_id, stage_id, request)
    except StageSealApplicationError as error:
        _raise(error)


@router.post("/{run_id}/stages/{source_stage_id}/copy-forward/{target_stage_id}", response_model=StageSealResponse)
def copy_forward(
    run_id: str,
    source_stage_id: str,
    target_stage_id: str,
    request: StageSealRequest,
    service: StageSealApplicationService = Depends(get_service),
):
    try:
        return service.copy_forward(run_id, source_stage_id, target_stage_id, request)
    except StageSealApplicationError as error:
        _raise(error)
