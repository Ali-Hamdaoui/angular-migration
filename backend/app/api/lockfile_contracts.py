"""API contracts for lockfile compatibility (V2 F08)."""

from datetime import datetime
from typing import Any

from app.domain.contracts import ContractModel


class LockfileFindingDto(ContractModel):
    package: str
    expected: str | None = None
    resolved: str | None = None
    status: str
    detail: str = ""


class LockfileCompatibilityVerdictDto(ContractModel):
    source_family: str
    target_family: str
    status: str
    findings: list[LockfileFindingDto]
    blockers: list[str]


class LockfileValidationRequest(ContractModel):
    workspace_path: str
    source_family: str
    target_family: str
    catalogue_version: str | None = None
    execution_id: str | None = None
    node_version: str | None = None
    npm_version: str | None = None
    node_sha256: str | None = None
    npm_sha256: str | None = None
    deterministic: bool = True


class LockfileEvidenceDto(ContractModel):
    id: str
    run_id: str
    stage_id: str
    execution_id: str | None = None
    lockfile_checksum: str
    lockfile_version: int | None = None
    source_family: str
    target_family: str
    node_version: str | None = None
    npm_version: str | None = None
    node_sha256: str | None = None
    npm_sha256: str | None = None
    validation_status: str
    blockers: list[str]
    findings: list[dict[str, Any]]
    deterministic: bool
    created_at: datetime


class LockfileEvidenceListDto(ContractModel):
    evidence: list[LockfileEvidenceDto]
