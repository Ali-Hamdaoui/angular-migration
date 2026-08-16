"""API contracts for third-party compatibility scanning (V2 F15)."""

from datetime import datetime
from typing import Literal

from app.domain.contracts import ContractModel


class DependencyInventoryItemDto(ContractModel):
    name: str
    declared: str
    resolved: str | None = None
    scope: Literal["dependency", "devDependency", "peerDependency"]


class DependencyFindingDto(ContractModel):
    name: str
    declared: str
    resolved: str | None = None
    target_major: int
    status: Literal["compatible", "incompatible", "unknown", "peer_conflict"]
    detail: str = ""


class CompatibilityReportDto(ContractModel):
    run_id: str
    stage_id: str
    source_major: int
    target_major: int
    status: str
    blockers: list[str]
    inventory: list[DependencyInventoryItemDto]
    findings: list[DependencyFindingDto]


class CompatibilityReportRecordDto(ContractModel):
    id: str
    run_id: str
    stage_id: str
    source_major: int
    target_major: int
    status: str
    blockers: list[str]
    inventory: list[dict]
    findings: list[dict]
    created_at: datetime


class CompatibilityReportListDto(ContractModel):
    reports: list[CompatibilityReportRecordDto]


class ScanStageRequest(ContractModel):
    workspace_path: str
