"""Typed HTTP contracts for S3-F14 stage seal (G12) and seal operations."""
from typing import Any
from pydantic import Field
from app.domain.contracts import ContractModel


class StageSealRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)


class StageSealResponse(ContractModel):
    seal_id: str
    run_id: str
    stage_id: str
    status: str
    fingerprint: dict[str, Any] | None = None
    cleanup_result: dict[str, Any] | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False


class G12GateResponse(ContractModel):
    gate_id: str
    run_id: str
    stage_id: str
    status: str
    decision: str = "pending"
    fingerprint_checksum: str | None = None
    assurance_checksum: str | None = None
    workspace_fingerprint: str | None = None
    comment: str | None = None
    state_version: int
    event_sequence: int


class G12DecisionRequest(ContractModel):
    gate_id: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    actor: str = Field(min_length=1, max_length=128)
    rationale: str | None = None
    idempotency_key: str | None = None
