"""API contracts for project capabilities (V2 F13)."""

from pydantic import Field

from app.domain.contracts import ContractModel


class ProjectCapabilityDto(ContractModel):
    key: str
    value: str
    detail: str = ""


class CapabilitySnapshotDto(ContractModel):
    run_id: str
    stage_id: str | None = None
    source_root: str
    angular_major: int | None = None
    capabilities: list[ProjectCapabilityDto]
    checksum: str


class CapabilitySnapshotListDto(ContractModel):
    snapshots: list[CapabilitySnapshotDto]


class DeriveCapabilitiesRequest(ContractModel):
    run_id: str | None = Field(default=None, min_length=1)
    source_root: str
    stage_id: str | None = None


class ReadinessRequest(ContractModel):
    source_root: str


class ReadinessResponse(ContractModel):
    status: str
    blockers: list[str]

