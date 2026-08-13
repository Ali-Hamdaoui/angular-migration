"""Contracts for the narrowly governed transformation replan boundary."""

from typing import Any

from pydantic import Field

from app.domain.contracts import ContractModel


class TransformationReplanRecoveryRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    expected_continuation_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    failed_execution_id: str = Field(min_length=1, max_length=64)
    failed_result_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    approved_plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    approved_stage_plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    correlation_id: str | None = Field(default=None, max_length=128)


class TransformationReplanRecoveryResponse(ContractModel):
    run_id: str
    continuation_id: str
    failed_execution_id: str
    reconstruction_checkpoint_id: str
    restored_workspace_fingerprint: str
    previous_plan_checksum: str
    previous_stage_plan_checksum: str
    plan: dict[str, Any]
    stage_plan: dict[str, Any]
    plan_checksum: str
    stage_plan_checksum: str
    g06_id: str
    g06_status: str
    g06_package_checksum: str
    g06_artifact_set_checksum: str
    state_version: int
    idempotent_replay: bool = False
