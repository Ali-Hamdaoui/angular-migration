"""API contracts for governed repair proposal cycles (V2 F21)."""

from datetime import datetime
from typing import Literal

from app.domain.contracts import ContractModel


class ProposalCycleDto(ContractModel):
    cycle_id: str
    run_id: str
    attempt_id: str
    cycle_number: int
    proposal_checksum: str
    decision: Literal["pending", "accepted", "rejected", "request_changes"]
    reviewer: str | None = None
    hints: list[str]
    parent_cycle_id: str | None = None
    checksum: str


class ProposalCycleRecordDto(ContractModel):
    id: str
    run_id: str
    attempt_id: str
    cycle_number: int
    proposal_checksum: str
    decision: str
    reviewer: str | None = None
    hints: list[str]
    parent_cycle_id: str | None = None
    checksum: str
    created_at: datetime | None = None


class ProposalCycleListDto(ContractModel):
    cycles: list[ProposalCycleRecordDto]


class CreateCycleRequest(ContractModel):
    proposal_checksum: str


class DecideCycleRequest(ContractModel):
    decision: Literal["accepted", "rejected", "request_changes"]
    reviewer: str | None = None
    hints: list[str] | None = None
