"""Typed HTTP contracts for S3-F13 assurance aggregation and G09 gate."""
from typing import Any
from pydantic import Field
from app.domain.contracts import ContractModel


class AssuranceRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    prerequisite_artifact_ids: list[str] = Field(default_factory=list)


class AssuranceResponse(ContractModel):
    assurance_id: str
    run_id: str
    stage_id: str
    overall_status: str
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    overall_score: float = 0.0
    overall_max_score: float = 0.0
    summary: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False


class G09GateResponse(ContractModel):
    gate_id: str
    run_id: str
    stage_id: str
    status: str
    decision: str = "pending"
    assurance_checksum: str | None = None
    plan_checksum: str | None = None
    workspace_fingerprint: str | None = None
    comment: str | None = None
    state_version: int
    event_sequence: int


class G09DecisionRequest(ContractModel):
    gate_id: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    actor: str = Field(min_length=1, max_length=128)
    rationale: str | None = None
    idempotency_key: str | None = None
