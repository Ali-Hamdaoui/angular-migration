"""API contracts for catalogue certification pipeline (V2 F30)."""

from datetime import datetime

from app.domain.contracts import ContractModel


class CatalogueCertificationOutcomeDto(ContractModel):
    case_id: str
    source_family: str
    target_family: str
    status: str
    runtime_proof: list[list[str]]
    evidence: list[str]
    reason: str
    checksum: str


class CatalogueCertificationRunDto(ContractModel):
    run_id: str
    catalogue_version: str
    outcomes: list[CatalogueCertificationOutcomeDto]
    certified_count: int
    rejected_count: int
    deterministic: bool
    ran_at: datetime
    checksum: str


class CatalogueCertificationRecordDto(ContractModel):
    id: str
    run_id: str
    source_family: str
    target_family: str
    status: str
    runtime_proof: list[list[str]]
    evidence: list[str]
    reason: str
    catalogue_version: str
    checksum: str
    ran_at: datetime


class CatalogueCertificationRunRequest(ContractModel):
    fixture_root: str
