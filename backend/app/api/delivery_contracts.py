"""Typed HTTP contracts for the G14 delivery surface."""

from typing import Any

from pydantic import Field

from app.domain.contracts import ContractModel
from app.domain.delivery import G14Decision


class G14DecisionRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    decision: G14Decision
    comment: str | None = Field(default=None, max_length=4000)
    gate_id: str = Field(default="G14", min_length=1, max_length=16)


class DeliveryRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    destination: str = Field(min_length=1)


class DeliveryResponse(ContractModel):
    run_id: str
    gate_id: str
    gate_version: str
    status: str
    decision: str | None = None
    candidate: dict[str, Any] | None = None
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    idempotent_replay: bool = False
    stale_reason: str | None = None
    comment: str | None = None
