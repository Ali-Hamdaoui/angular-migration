"""Typed HTTP contracts for approval gate decisions (G09/G12)."""
from typing import Any
from pydantic import Field
from app.domain.contracts import ContractModel


class ApprovalGateRequest(ContractModel):
    gate_id: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    actor: str = Field(min_length=1, max_length=128)
    rationale: str | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)


class ApprovalGateResponse(ContractModel):
    approval_id: str
    run_id: str
    stage_id: str
    gate_id: str
    decision: str
    status: str
    actor: str
    rationale: str | None = None
    state_version: int
    event_sequence: int
    created_at: str
    idempotent_replay: bool = False
