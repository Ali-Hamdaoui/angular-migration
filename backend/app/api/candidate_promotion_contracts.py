"""API contracts for candidate workspace promotion (V2 F22)."""

from datetime import datetime
from typing import Literal

from app.domain.contracts import ContractModel


class CandidatePromotionDecisionDto(ContractModel):
    run_id: str
    stage_id: str
    alias: str
    candidate_fingerprint: str
    generation: int
    status: Literal["candidate_ready", "validated", "promoted", "rejected", "rollback_required"]
    validated: bool
    blockers: list[str]
    previous_generation: int | None = None
    checksum: str


class CandidatePromotionRecordDto(ContractModel):
    id: str
    run_id: str
    stage_id: str
    alias: str
    candidate_fingerprint: str
    generation: int
    status: str
    validated: bool
    blockers: list[str]
    previous_generation: int | None = None
    checksum: str
    created_at: datetime


class CandidatePromotionListDto(ContractModel):
    promotions: list[CandidatePromotionRecordDto]


class CandidatePathRequest(ContractModel):
    candidate_path: str
