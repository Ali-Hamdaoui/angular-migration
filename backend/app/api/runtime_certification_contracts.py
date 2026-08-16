"""API contracts for bridge runtime certification (V2 F11)."""

from datetime import datetime

from app.domain.contracts import ContractModel


class RuntimeCertificationDto(ContractModel):
    run_id: str
    stage_id: str
    source_family: str
    target_family: str
    runtime_id: str | None = None
    node_exact: str | None = None
    npm_exact: str | None = None
    certified: bool
    allowed: bool = False
    classification: str = "UNSUPPORTED"
    reason: str | None = None
    certified_against: str | None = None
    resolved_at: datetime


class RuntimeCertificationRecordDto(ContractModel):
    id: str
    run_id: str
    stage_id: str
    source_family: str
    target_family: str
    runtime_id: str | None = None
    node_version: str | None = None
    npm_version: str | None = None
    node_sha256: str | None = None
    npm_sha256: str | None = None
    certified: bool
    allowed: bool = False
    classification: str = "UNSUPPORTED"
    reason: str | None = None
    certified_against: str | None = None
    created_at: datetime


class RuntimeCertificationListDto(ContractModel):
    certifications: list[RuntimeCertificationRecordDto]
