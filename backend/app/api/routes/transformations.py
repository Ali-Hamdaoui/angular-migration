"""G03 transformation, evidence, and G08 approval API routes."""

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import JSONResponse

from app.api.authentication import authenticated_actor
from app.api.errors import error_response
from app.api.transformation_contracts import (
    AngularUpdateRequest,
    AngularUpdateResponse,
    G08DecisionRequest,
    G08InitializeRequest,
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


def _g08_error(
    request: Request,
    error: G03ApplicationError,
) -> JSONResponse:
    return error_response(
        request,
        status_code=error.status_code,
        error_code=error.code,
        message=error.message,
    )


def _g08_backend_failure(request: Request, message: str) -> JSONResponse:
    return error_response(
        request,
        status_code=500,
        error_code="G08_BACKEND_FAILURE",
        message=message,
    )


def _g08_result_or_404(request: Request, result, detail: str = "G08 approval package not found") -> JSONResponse:
    if result is None:
        return error_response(
            request,
            status_code=404,
            error_code="G08_NOT_FOUND",
            message=detail,
        )
    return result


# ── S3-F07 — Angular Update ──────────────────────────────────────────────


@router.post("/{run_id}/stages/{stage_id}/angular-update", response_model=AngularUpdateResponse)
def start_angular_update(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    request: AngularUpdateRequest = None,
    actor: str = Depends(authenticated_actor),
    service: AngularUpdateApplicationService = Depends(get_angular_update_service),
):
    try:
        return service.start_update(run_id, stage_id, request.model_copy(update={"actor": actor}))
    except G03ApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error


@router.get("/{run_id}/stages/{stage_id}/angular-update", response_model=AngularUpdateResponse)
def get_angular_update(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    actor: str = Depends(authenticated_actor),
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
    actor: str = Depends(authenticated_actor),
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
        return service.generate(run_id, stage_id, request, actor=actor)
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
    try:
        result = service.get(run_id, stage_id, actor=actor)
    except G03ApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error
    if result is None:
        raise HTTPException(status_code=404, detail="Transformation evidence not found")
    return result


# ── S3-F09 — G08 Approval ────────────────────────────────────────────────


@router.get("/{run_id}/stages/{stage_id}/approvals/{gate_id}", response_model=G08ReviewResponse)
def inspect_g08(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    gate_id: str = Path(min_length=1),
    http_request: Request = None,
    actor: str = Depends(authenticated_actor),
    service: G08ApprovalApplicationService = Depends(get_g08_service),
):
    try:
        result = service.get(run_id, stage_id, gate_id, actor=actor)
    except G03ApplicationError as error:
        return _g08_error(http_request, error)
    except Exception:
        return _g08_backend_failure(http_request, "Unexpected backend failure in inspect_g08")
    return _g08_result_or_404(http_request, result)


@router.post("/{run_id}/stages/{stage_id}/approvals/{gate_id}/decisions", response_model=G08ReviewResponse)
def decide_g08(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    gate_id: str = Path(min_length=1),
    request: G08DecisionRequest = None,
    http_request: Request = None,
    actor: str = Depends(authenticated_actor),
    service: G08ApprovalApplicationService = Depends(get_g08_service),
):
    if request.gate_id != gate_id:
        return error_response(
            http_request,
            status_code=400,
            error_code="GATE_ID_MISMATCH",
            message="gate_id in body does not match path",
        )
    try:
        return service.decide(run_id, stage_id, request, actor=actor)
    except G03ApplicationError as error:
        return _g08_error(http_request, error)
    except Exception:
        return _g08_backend_failure(http_request, "Unexpected backend failure in decide_g08")


@router.post("/{run_id}/stages/{stage_id}/approvals/{gate_id}/package", response_model=G08ReviewResponse)
def initialize_g08(
    run_id: str = Path(min_length=1),
    stage_id: str = Path(min_length=1),
    gate_id: str = Path(min_length=1),
    request: G08InitializeRequest = None,
    http_request: Request = None,
    actor: str = Depends(authenticated_actor),
    service: G08ApprovalApplicationService = Depends(get_g08_service),
):
    if request.gate_id != gate_id:
        return error_response(
            http_request,
            status_code=400,
            error_code="GATE_ID_MISMATCH",
            message="gate_id in body does not match path",
        )
    try:
        return service.initialize(run_id, stage_id, request, actor=actor)
    except G03ApplicationError as error:
        return _g08_error(http_request, error)
    except Exception:
        return _g08_backend_failure(http_request, "Unexpected backend failure in initialize_g08")


# ── Source-contract alias routes (fixed G08, no stage_id in path) ────────


@router.get("/{run_id}/approvals/G08", response_model=G08ReviewResponse)
def inspect_current_g08(
    run_id: str = Path(min_length=1),
    http_request: Request = None,
    actor: str = Depends(authenticated_actor),
    service: G08ApprovalApplicationService = Depends(get_g08_service),
):
    try:
        result = service.get(run_id=run_id, stage_id=None, gate_id="G08", actor=actor)
    except G03ApplicationError as error:
        return _g08_error(http_request, error)
    except Exception:
        return _g08_backend_failure(http_request, "Unexpected backend failure in inspect_current_g08")
    return _g08_result_or_404(http_request, result)


@router.post("/{run_id}/approvals/G08/decisions", response_model=G08ReviewResponse)
def decide_current_g08(
    run_id: str = Path(min_length=1),
    request: G08DecisionRequest = None,
    http_request: Request = None,
    actor: str = Depends(authenticated_actor),
    service: G08ApprovalApplicationService = Depends(get_g08_service),
):
    if request.gate_id != "G08":
        return error_response(
            http_request,
            status_code=400,
            error_code="GATE_ID_MISMATCH",
            message="gate_id in body does not match path",
        )
    try:
        return service.decide(run_id, stage_id=None, request=request, actor=actor)
    except G03ApplicationError as error:
        return _g08_error(http_request, error)
    except Exception:
        return _g08_backend_failure(http_request, "Unexpected backend failure in decide_current_g08")


@router.post("/{run_id}/approvals/G08/package", response_model=G08ReviewResponse)
def initialize_current_g08(
    run_id: str = Path(min_length=1),
    request: G08InitializeRequest = None,
    http_request: Request = None,
    actor: str = Depends(authenticated_actor),
    service: G08ApprovalApplicationService = Depends(get_g08_service),
):
    if request.gate_id != "G08":
        return error_response(
            http_request,
            status_code=400,
            error_code="GATE_ID_MISMATCH",
            message="gate_id in body does not match path",
        )
    try:
        return service.initialize(run_id, stage_id=None, request=request, actor=actor)
    except G03ApplicationError as error:
        return _g08_error(http_request, error)
    except Exception:
        return _g08_backend_failure(http_request, "Unexpected backend failure in initialize_current_g08")
