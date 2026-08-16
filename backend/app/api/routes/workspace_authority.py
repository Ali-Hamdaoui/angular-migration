"""Workspace authority API (V2 F07)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.workspace_authority_contracts import (
    PromoteWorkspaceRequest,
    PromoteWorkspaceResponse,
    ResolveActiveWorkspaceResponse,
    WorkspaceGenerationDto,
    WorkspaceGenerationListDto,
)
from app.domain.workspace_authority import WorkspacePromotionRequest
from app.services.workspace_authority_service import WorkspaceAuthorityError, WorkspaceAuthorityService

router = APIRouter(prefix="/runs/{run_id}/workspaces", tags=["workspace-authority"])


def get_workspace_authority_service() -> WorkspaceAuthorityService:
    return WorkspaceAuthorityService()


def _raise(error: WorkspaceAuthorityError) -> None:
    raise HTTPException(status_code=404 if error.code == "RUN_NOT_FOUND" else 409 if error.code == "STALE_GENERATION" else 422,
                        detail={"error_code": error.code, "message": error.message})


def _generation_dto(row) -> WorkspaceGenerationDto:
    return WorkspaceGenerationDto(
        run_id=row.run_id, stage_id=row.stage_id, alias=row.alias, generation=row.generation,
        workspace_path=row.workspace_path, fingerprint=row.fingerprint,
        input_fingerprint=row.input_fingerprint, status=row.status, created_at=row.created_at,
    )


@router.get("/{alias}/active", response_model=ResolveActiveWorkspaceResponse)
def resolve_active_workspace(
    run_id: str,
    alias: str,
    stage_id: str,
    service: WorkspaceAuthorityService = Depends(get_workspace_authority_service),
) -> ResolveActiveWorkspaceResponse:
    active = service.resolve_active(run_id, stage_id, alias)
    current = service.current_generation(run_id, stage_id, alias)
    return ResolveActiveWorkspaceResponse(
        active=_generation_dto(active) if active else None,
        current_generation=current,
    )


@router.post("/{alias}/promote", response_model=PromoteWorkspaceResponse)
def promote_workspace(
    run_id: str,
    alias: str,
    request: PromoteWorkspaceRequest,
    stage_id: str,
    service: WorkspaceAuthorityService = Depends(get_workspace_authority_service),
) -> PromoteWorkspaceResponse:
    try:
        decision = service.promote(
            WorkspacePromotionRequest(
                run_id=run_id,
                stage_id=stage_id,
                alias=alias,
                generation=request.generation,
                workspace_path=request.workspace_path,
                fingerprint=request.fingerprint,
                input_fingerprint=request.input_fingerprint,
            )
        )
    except WorkspaceAuthorityError as error:
        _raise(error)
    return PromoteWorkspaceResponse(
        allowed=decision.allowed,
        reason=decision.reason,
        generation=decision.generation,
        current_active_generation=decision.current_active_generation,
    )


@router.get("/{alias}/generations", response_model=WorkspaceGenerationListDto)
def list_workspace_generations(
    run_id: str,
    alias: str,
    stage_id: str,
    service: WorkspaceAuthorityService = Depends(get_workspace_authority_service),
) -> WorkspaceGenerationListDto:
    return WorkspaceGenerationListDto(generations=[_generation_dto(row) for row in service.list_generations(run_id, stage_id, alias)])
