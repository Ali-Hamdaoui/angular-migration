"""API contracts for stage validation and sealing (V2 F24)."""

from datetime import datetime
from typing import Literal

from app.domain.contracts import ContractModel


class StageValidationResultDto(ContractModel):
    stage_id: str
    checks: list[str]
    passed: bool
    blockers: list[str]
    workspace_fingerprint: str
    checksum: str


class StageSealDto(ContractModel):
    stage_id: str
    source_major: int
    target_major: int
    validation_checksum: str
    workspace_fingerprint: str
    sealed_at: datetime
    checksum: str


class StageSealRecordDto(ContractModel):
    id: str
    stage_id: str
    run_id: str
    source_major: int
    target_major: int
    validation_checksum: str
    workspace_fingerprint: str
    sealed_at: datetime
    checksum: str
    created_at: datetime


class StageSealListDto(ContractModel):
    seals: list[StageSealRecordDto]


class ValidateStageRequest(ContractModel):
    workspace_path: str
