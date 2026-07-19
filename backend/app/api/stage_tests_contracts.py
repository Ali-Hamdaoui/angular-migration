"""Typed HTTP contracts for S3-F12 stage tests and conditional lint."""
from typing import Any
from pydantic import Field
from app.domain.contracts import ContractModel


class StageTestRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    prerequisite_artifact_ids: list[str] = Field(default_factory=list)
    skip_lint: bool = False


class StageTestResponse(ContractModel):
    test_id: str
    run_id: str
    stage_id: str
    status: str
    test_results: list[dict[str, Any]] = Field(default_factory=list)
    lint_results: list[dict[str, Any]] = Field(default_factory=list)
    test_summary: dict[str, Any] = Field(default_factory=dict)
    lint_summary: dict[str, Any] = Field(default_factory=dict)
    known_baseline_failures: list[dict[str, Any]] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
