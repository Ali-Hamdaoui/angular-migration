"""API contracts for stage rollback and resume (V2 F25)."""

from datetime import datetime
from typing import Literal

from app.domain.contracts import ContractModel


class StageRollbackDecisionDto(ContractModel):
    run_id: str
    rollback_point_stage_order: int | None = None
    sealed_stage_count: int
    evidence_preserved: bool
    status: Literal["rolled_back", "no_rollback_point", "not_started"]
    checksum: str


class StageRollbackRecordDto(ContractModel):
    id: str
    run_id: str
    rollback_point_stage_order: int | None = None
    sealed_stage_count: int
    evidence_preserved: bool
    status: str
    created_at: datetime


class StageRollbackListDto(ContractModel):
    rollbacks: list[StageRollbackRecordDto]


class StageResumeDto(ContractModel):
    run_id: str
    rollback_point_stage_order: int | None = None
    next_stage_order: int | None = None
    resume_action: str
