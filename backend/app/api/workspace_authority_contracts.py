"""API contracts for workspace authority (V2 F07)."""

from datetime import datetime

from app.domain.contracts import ContractModel


class WorkspaceGenerationDto(ContractModel):
    run_id: str
    stage_id: str | None = None
    alias: str
    generation: int
    workspace_path: str
    fingerprint: str
    input_fingerprint: str | None = None
    status: str
    created_at: datetime


class PromoteWorkspaceRequest(ContractModel):
    generation: int
    workspace_path: str
    fingerprint: str
    input_fingerprint: str | None = None


class PromoteWorkspaceResponse(ContractModel):
    allowed: bool
    reason: str | None = None
    generation: int
    current_active_generation: int | None = None


class ResolveActiveWorkspaceResponse(ContractModel):
    active: WorkspaceGenerationDto | None = None
    current_generation: int | None = None


class WorkspaceGenerationListDto(ContractModel):
    generations: list[WorkspaceGenerationDto]
