"""API contracts for the V2 analyzer and planner (F18)."""

from datetime import datetime
from typing import Any

from app.domain.contracts import ContractModel


class V2AnalysisFindingDto(ContractModel):
    finding_id: str
    severity: str
    message: str


class V2PlannedStageDto(ContractModel):
    stage_order: int
    source_major: int
    target_major: int
    source_family: str
    target_family: str
    target_exact: str
    node_minimum: str | None = None
    expected_transforms: list[str]
    validation_expectations: list[str]


class V2MigrationPlanDto(ContractModel):
    run_id: str
    source_major: int
    target_major: int
    catalogue_version: str
    findings: list[V2AnalysisFindingDto]
    stages: list[V2PlannedStageDto]
    checksum: str


class V2PlanRecordDto(ContractModel):
    id: str
    run_id: str
    source_major: int
    target_major: int
    catalogue_version: str
    findings: list[dict[str, Any]]
    stages: list[dict[str, Any]]
    checksum: str
    created_at: datetime


class AnalyzeRequest(ContractModel):
    source_root: str | None = None
