"""API contracts for stage runtime requirement and binding (V2 F02)."""

from datetime import datetime
from typing import Literal

from app.api.runtime_contracts import RuntimeRequirementBindingDto, RuntimeRequirementDto
from app.domain.contracts import ContractModel


class StageRuntimeRequirementDto(ContractModel):
    stage_id: str
    source_family: str
    target_family: str
    catalogue_version: str
    requirements: list[RuntimeRequirementDto]


class StageRuntimeBindingDto(ContractModel):
    stage_id: str
    requirement: StageRuntimeRequirementDto
    bindings: list[RuntimeRequirementBindingDto]
    status: Literal["bound", "blocked"]
    blocked_reason: str | None = None
    resolved_at: datetime
    checksum: str


class StageRuntimeBindingRowDto(ContractModel):
    id: str
    run_id: str
    stage_id: str
    kind: Literal["node", "npm", "npx"]
    runtime_id: str | None = None
    version_exact: str | None = None
    sha256: str | None = None
    resolved_path: str | None = None
    source: str | None = None
    status: str
    blocked_reason: str | None = None
    created_at: datetime


class ResolveStageRuntimeRequest(ContractModel):
    source_family: str
    target_family: str
    catalogue_version: str | None = None


class RecordStageRuntimeBindingRequest(ContractModel):
    run_id: str
    actor: str | None = None


class StageRuntimeBindingListDto(ContractModel):
    bindings: list[StageRuntimeBindingRowDto]
