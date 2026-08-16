"""API contracts for dynamic stage orchestration (V2 F12)."""

from datetime import datetime
from typing import Any, Literal

from app.domain.contracts import ContractModel


class StageRunRecordDto(ContractModel):
    stage_order: int
    stage_id: str
    source_major: int
    target_major: int
    status: Literal["pending", "running", "sealed", "failed", "repairing"]
    gate_passed: bool
    failure_code: str | None = None


class StageChainStateDto(ContractModel):
    run_id: str
    source_major: int
    target_major: int
    catalogue_version: str
    status: Literal["created", "running", "completed", "failed", "repairing"]
    stages: list[StageRunRecordDto]
    checksum: str


class StageChainRecordDto(ContractModel):
    id: str
    run_id: str
    source_major: int
    target_major: int
    catalogue_version: str
    status: str
    stages: list[dict[str, Any]]
    checksum: str
    created_at: datetime
    updated_at: datetime
