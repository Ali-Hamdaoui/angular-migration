"""API contracts for the V2 runtime execution authority (F01)."""

from datetime import datetime
from typing import Literal

from app.domain.contracts import ContractModel


class RuntimeRequirementDto(ContractModel):
    kind: Literal["node", "npm", "npx"]
    runtime_id: str
    version_exact: str | None = None
    minimum_version: str | None = None
    required_sha256: str | None = None


class RuntimeExecutableDescriptorDto(ContractModel):
    kind: Literal["node", "npm", "npx"]
    executable_name: str
    resolved_path: str
    version_exact: str | None = None
    sha256: str
    operating_system: str
    architecture: str
    installation_root: str | None = None
    source: str
    runtime_id: str | None = None
    probed_at: datetime


class RuntimeRequirementBindingDto(ContractModel):
    requirement: RuntimeRequirementDto
    descriptor: RuntimeExecutableDescriptorDto | None = None
    blocked_reason: str | None = None
    resolved_at: datetime


class ResolveRuntimeRequirementsRequest(ContractModel):
    requirements: list[RuntimeRequirementDto]


class ResolveRuntimeRequirementsResponse(ContractModel):
    bindings: list[RuntimeRequirementBindingDto]


class DiscoverRuntimeDescriptorsResponse(ContractModel):
    descriptors: list[RuntimeExecutableDescriptorDto]


class RecordRuntimeEvidenceRequest(ContractModel):
    requirements: list[RuntimeRequirementDto]
    execution_id: str | None = None
    actor: str | None = None


class RecordRuntimeEvidenceResponse(ContractModel):
    recorded: int
    evidence: list[RuntimeExecutableDescriptorDto]


class ListRuntimeEvidenceResponse(ContractModel):
    evidence: list[RuntimeExecutableDescriptorDto]
