"""G03 transformation, evidence, and G08 approval API routes."""

from fastapi import APIRouter, Depends, HTTPException, Path

from app.api.authentication import authenticated_actor
from app.api.transformation_contracts import (
    AngularUpdateRequest,
    AngularUpdateResponse,
    G08DecisionRequest,
    G08ReviewResponse,
    TargetVersionResponse,
    TransformationEvidenceRequest,
    TransformationEvidenceResponse,
)
from app.domain.transformation import AngularUpdateVerificationRequest
from app.services.transformation_application_service import (
    AngularUpdateApplicationService,
    G03ApplicationError,
    G08ApprovalApplicationService,
    TransformationEvidenceApplicationService,
)

router = APIRouter(prefix="/runs", tags=["transformations"])


def get_angular_update_service() -> AngularUpdateApplicationService:
    return AngularUpdateApplicationService()


def get_transformation_evidence_service() -> TransformationEvidenceApplicationService:
    return TransformationEvidenceApplicationService()


def get_g08_service() -> G08ApprovalApplicationService:
    return G08ApprovalApplicationService()


# ── S3-F07 — Angular Update ──────────────────────────────────────────────


@router.post("/{run_id}/stages/{stage_id}/angular-update", response_model=AngularUpdateResponse)
def start_angular_update(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    request: AngularUpdateRequest = None,
    service: AngularUpdateApplicationService = Depends(get_angular_update_service),
):
    try:
        return service.start_update(run_id, stage_id, request)
    except G03ApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error


@router.get("/{run_id}/stages/{stage_id}/angular-update", response_model=AngularUpdateResponse)
def get_angular_update(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    service: AngularUpdateApplicationService = Depends(get_angular_update_service),
):
    result = service.get(run_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Angular update record not found")
    return result


@router.get("/{run_id}/stages/{stage_id}/target-version", response_model=TargetVersionResponse)
def get_target_version(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    service: AngularUpdateApplicationService = Depends(get_angular_update_service),
):
    result = service.get_target_version(run_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Target version not found")
    return result


@router.post(
    "/{run_id}/stages/{stage_id}/angular-update/complete",
    response_model=AngularUpdateResponse,
)
def complete_angular_update(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    body: AngularUpdateVerificationRequest = None,
    actor: str = Depends(authenticated_actor),
    service: AngularUpdateApplicationService = Depends(get_angular_update_service),
):
    try:
        return service.complete_update(run_id, stage_id, body.model_copy(update={"actor": actor}))
    except G03ApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error


@router.post(
    "/{run_id}/stages/{stage_id}/target-version/verify",
    response_model=TargetVersionResponse,
)
def verify_target_version(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    body: AngularUpdateVerificationRequest = None,
    actor: str = Depends(authenticated_actor),
    service: AngularUpdateApplicationService = Depends(get_angular_update_service),
):
    try:
        return service.verify_target_version(run_id, stage_id, body.model_copy(update={"actor": actor}))
    except G03ApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error


# ── S3-F08 — Transformation Evidence ────────────────────────────────────


@router.post(
    "/{run_id}/stages/{stage_id}/transformation-evidence",
    response_model=TransformationEvidenceResponse,
)
def generate_transformation_evidence(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    request: TransformationEvidenceRequest = None,
    actor: str = Depends(authenticated_actor),
    service: TransformationEvidenceApplicationService = Depends(get_transformation_evidence_service),
):
    try:
        return service.generate(run_id, stage_id, request.model_copy(update={"actor": actor}))
    except G03ApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error


@router.get(
    "/{run_id}/stages/{stage_id}/transformation-evidence",
    response_model=TransformationEvidenceResponse,
)
def get_transformation_evidence(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    actor: str = Depends(authenticated_actor),
    service: TransformationEvidenceApplicationService = Depends(get_transformation_evidence_service),
):
    result = service.get(run_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Transformation evidence not found")
    return result


# ── S3-F09 — G08 Approval ────────────────────────────────────────────────


@router.get("/{run_id}/stages/{stage_id}/approvals/{gate_id}", response_model=G08ReviewResponse)
def inspect_g08(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    gate_id: str = Path(min_length=1),
    service: G08ApprovalApplicationService = Depends(get_g08_service),
):
    result = service.get(run_id, stage_id, gate_id)
    if result is None:
        raise HTTPException(status_code=404, detail="G08 approval package not found")
    return result


@router.post("/{run_id}/stages/{stage_id}/approvals/{gate_id}/decisions", response_model=G08ReviewResponse)
def decide_g08(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    gate_id: str = Path(min_length=1),
    request: G08DecisionRequest = None,
    service: G08ApprovalApplicationService = Depends(get_g08_service),
):
    if request.gate_id != gate_id:
        raise HTTPException(status_code=400, detail="gate_id in body does not match path")
    try:
        return service.decide(run_id, stage_id, request)
    except G03ApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error


@router.post("/{run_id}/stages/{stage_id}/approvals/{gate_id}/package", response_model=G08ReviewResponse)
def initialize_g08(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    gate_id: str = Path(min_length=1),
    request: G08DecisionRequest = None,
    service: G08ApprovalApplicationService = Depends(get_g08_service),
):
    if request.gate_id != gate_id:
        raise HTTPException(status_code=400, detail="gate_id in body does not match path")
    try:
        return service.initialize(run_id, stage_id, request)
    except G03ApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error
