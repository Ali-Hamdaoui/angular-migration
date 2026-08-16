"""Angular update governance API (V2 F14)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.ng_update_governance_contracts import NgUpdateAuthorizationDto, NgUpdateSpecDto
from app.services.ng_update_governance_service import NgUpdateGovernanceError, NgUpdateGovernanceService

router = APIRouter(tags=["ng-update-governance"])


def get_governance_service() -> NgUpdateGovernanceService:
    return NgUpdateGovernanceService()


def _raise(error: NgUpdateGovernanceError) -> None:
    raise HTTPException(status_code=404 if error.code == "CATALOGUE_ENTRY_MISSING" else 422,
                        detail={"error_code": error.code, "message": error.message})


def _spec_dto(spec) -> NgUpdateSpecDto:
    return NgUpdateSpecDto(
        source_major=spec.source_major, target_major=spec.target_major,
        template_id=spec.template_id, executable=spec.executable,
        target_exact=spec.target_exact, target_cli_exact=spec.target_cli_exact,
        rendered_arguments=list(spec.rendered_arguments), checksum=spec.checksum,
    )


def _authz_dto(authz) -> NgUpdateAuthorizationDto:
    return NgUpdateAuthorizationDto(
        source_major=authz.source_major, target_major=authz.target_major,
        spec_checksum=authz.spec_checksum, certified=authz.certified,
        allowed=authz.allowed, reason=authz.reason,
    )


@router.get("/governance/ng-update/{source_major}/{target_major}", response_model=NgUpdateSpecDto)
def resolve_ng_update_spec(
    source_major: int,
    target_major: int,
    service: NgUpdateGovernanceService = Depends(get_governance_service),
) -> NgUpdateSpecDto:
    try:
        spec = service.spec_for_transition(source_major, target_major)
    except NgUpdateGovernanceError as error:
        _raise(error)
    return _spec_dto(spec)


@router.post("/runs/{run_id}/stages/{stage_id}/governance/ng-update/{source_major}/{target_major}", response_model=NgUpdateAuthorizationDto)
def authorize_ng_update(
    run_id: str,
    stage_id: str,
    source_major: int,
    target_major: int,
    service: NgUpdateGovernanceService = Depends(get_governance_service),
) -> NgUpdateAuthorizationDto:
    try:
        authz = service.authorize_update(source_major, target_major, stage_id=stage_id)
    except NgUpdateGovernanceError as error:
        _raise(error)
    except ValueError as error:
        raise HTTPException(status_code=404, detail={"error_code": "STAGE_NOT_FOUND", "message": str(error)})
    return _authz_dto(authz)
