"""Stage workspace preparation and G07 approval endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.stage_contracts import (
    G07DecisionRequest,
    G07ReviewResponse,
    StageBootstrapInstallRequest,
    StageBootstrapInstallResponse,
    StageBootstrapStatusResponse,
    StagePrepareRequest,
    StagePrepareResponse,
    StageSandboxRequest,
    StageSandboxResponse,
)
from app.services.stage_preparation_service import StageApplicationError, StagePreparationApplicationService
from app.services.stage_bootstrap_service import StageBootstrapApplicationService

router = APIRouter(prefix="/runs", tags=["stages"])


def get_stage_service() -> StagePreparationApplicationService:
    return StagePreparationApplicationService()


def get_bootstrap_service() -> StageBootstrapApplicationService:
    return StageBootstrapApplicationService()


@router.post("/{run_id}/stages/prepare", response_model=StagePrepareResponse)
def prepare_stage(run_id: str, request: StagePrepareRequest, service: StagePreparationApplicationService = Depends(get_stage_service)):
    try:
        return service.prepare_stage(run_id, request)
    except StageApplicationError as e:
        raise HTTPException(status_code=e.status_code, detail={"error_code": e.code, "message": e.message}) from e


@router.post("/{run_id}/stages/{stage_id}/sandbox", response_model=StageSandboxResponse)
def create_sandbox(run_id: str, stage_id: str, request: StageSandboxRequest, service: StagePreparationApplicationService = Depends(get_stage_service)):
    try:
        return service.create_sandbox(run_id, stage_id, request)
    except StageApplicationError as e:
        raise HTTPException(status_code=e.status_code, detail={"error_code": e.code, "message": e.message}) from e


@router.get("/{run_id}/approvals/G07", response_model=G07ReviewResponse)
def inspect_g07(run_id: str, stage_id: str | None = None, service: StagePreparationApplicationService = Depends(get_stage_service)):
    """Get G07 gate status. Requires stage_id query parameter."""
    if not stage_id:
        raise HTTPException(status_code=400, detail="stage_id query parameter is required")
    result = service.get_g07(run_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail="G07 approval package not found")
    return result


@router.post("/{run_id}/approvals/G07/decisions", response_model=G07ReviewResponse)
def decide_g07(run_id: str, request: G07DecisionRequest, service: StagePreparationApplicationService = Depends(get_stage_service)):
    if request.gate_id != "G07":
        raise HTTPException(status_code=400, detail="gate_id in body does not match path")
    if not request.stage_id:
        raise HTTPException(status_code=400, detail="stage_id is required in the request body")
    try:
        return service.decide_g07(run_id, request.stage_id, request)
    except StageApplicationError as e:
        raise HTTPException(status_code=e.status_code, detail={"error_code": e.code, "message": e.message}) from e


@router.post("/{run_id}/stages/{stage_id}/bootstrap-install", response_model=StageBootstrapInstallResponse)
def bootstrap_install(run_id: str, stage_id: str, request: StageBootstrapInstallRequest, service: StageBootstrapApplicationService = Depends(get_bootstrap_service)):
    try:
        return service.run_bootstrap_install(run_id, stage_id, request)
    except StageApplicationError as e:
        raise HTTPException(status_code=e.status_code, detail={"error_code": e.code, "message": e.message}) from e


@router.get("/{run_id}/stages/{stage_id}/steps/bootstrap-install", response_model=StageBootstrapStatusResponse)
def get_bootstrap_status(run_id: str, stage_id: str, service: StageBootstrapApplicationService = Depends(get_bootstrap_service)):
    result = service.get_bootstrap_status(run_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Bootstrap install step not found")
    return result
