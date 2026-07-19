"""Typed HTTP contracts for S3-F11 stage build matrix."""
from typing import Any
from pydantic import Field
from app.domain.contracts import ContractModel


class StageBuildRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    prerequisite_artifact_ids: list[str] = Field(default_factory=list)


class StageBuildResponse(ContractModel):
    build_id: str
    run_id: str
    stage_id: str
    status: str
    targets: list[dict[str, Any]] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False


class StageBuildStatusResponse(ContractModel):
    build_id: str
    run_id: str
    stage_id: str
    status: str
    results: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    state_version: int
    event_sequence: int
