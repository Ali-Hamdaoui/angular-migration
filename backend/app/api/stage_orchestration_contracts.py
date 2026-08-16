"""API contracts for dynamic stage orchestration (V2 F12)."""

from typing import Literal

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

