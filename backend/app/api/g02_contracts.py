"""Typed HTTP contracts for the G02 approval surface."""

from typing import Any

from pydantic import Field

from app.domain.contracts import ContractModel
from app.domain.g02 import G02Decision


class G02DecisionRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    decision: G02Decision
    comment: str | None = Field(default=None, max_length=4000)
    gate_id: str = Field(default="G02", min_length=1, max_length=16)


class G02ReviewResponse(ContractModel):
    run_id: str
    gate_id: str
    gate_version: str
    status: str
    decision: str | None = None
    package: dict[str, Any]
    baseline_input_boundary: str | None = None
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    idempotent_replay: bool = False
    stale_reason: str | None = None
    comment: str | None = None
