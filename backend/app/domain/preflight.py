"""Contracts for durable production preflight and G01."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class PreflightRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    path_validation_id: str = Field(min_length=1)
    environment_snapshot_id: str = Field(min_length=1)
    source_analysis_id: str = Field(min_length=1)
    target_angular_family: str = Field(min_length=1)
    migration_mode: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    actor: str = "control-tower"

class G01DecisionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    gate_id: str = Field(min_length=1)
    decision: Literal["approved", "approved_with_comment", "modification_requested", "rejected"]
    expected_state_version: int = Field(ge=1)
    input_checksum: str = Field(min_length=1)
    artifact_set_checksum: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    comment: str | None = None

class PreflightSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    preflight_id: str
    gate_id: str
    gate_version: str
    state_version: int = Field(ge=1)
    status: Literal["passed", "passed_with_warnings", "blocked", "expired", "stale"]
    created_at: datetime
    expires_at: datetime
    input_checksum: str
    artifact_set_checksum: str
    target_angular_family: str
    migration_mode: str
    source_path: str
    target_parent_path: str = ""
    generated_output_name: str = ""
    resolved_output_root: str = ""
    platform_repository_root: str = ""
    target_output_path: str
    target_reservation_id: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifacts: dict[str, dict] = Field(default_factory=dict)
    approval_status: Literal["pending", "approved", "approved_with_comment", "modification_requested", "rejected", "expired", "stale"] = "pending"
    decision_history: list[dict] = Field(default_factory=list)

class PreflightResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    snapshot: PreflightSnapshot

class G01Decision(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_id: str
    preflight_id: str
    gate_id: str
    decision: str
    actor: str
    comment: str | None = None
    decided_at: datetime
    input_checksum: str
    artifact_set_checksum: str
    state_version: int
    idempotent_replay: bool = False