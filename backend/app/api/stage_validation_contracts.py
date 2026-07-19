"""Typed HTTP contracts for S3-F10 stage validation (install + static checks)."""
from typing import Any

from pydantic import Field

from app.domain.contracts import ContractModel


class StageValidationRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    step_config: dict[str, Any] | None = None
    skip_install: bool = False
    skip_static_checks: bool = False


class StageValidationResponse(ContractModel):
    validation_id: str
    run_id: str
    stage_id: str
    status: str
    install_succeeded: bool | None = None
    install_duration_ms: int | None = None
    all_checks_passed: bool | None = None
    check_results: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
