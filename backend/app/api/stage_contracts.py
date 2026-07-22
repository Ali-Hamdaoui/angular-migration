"""Typed HTTP contracts for stage workspace preparation (S3-F05)."""

from datetime import datetime
from typing import Any

from pydantic import Field

from app.domain.contracts import ContractModel
from app.domain.stage_workspace import G07Decision


class StagePrepareRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    stage_key: str = Field(min_length=1, max_length=64)
    source_version_family: str = Field(min_length=1, max_length=32)
    target_version_family: str = Field(min_length=1, max_length=32)
    plan_version: str = Field(min_length=1, max_length=64)


class StagePrepareResponse(ContractModel):
    run_id: str
    stage_id: str
    stage_key: str
    status: str
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    plan: dict[str, Any] | None = None
    idempotent_replay: bool = False


class G07DecisionRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    stage_id: str = Field(min_length=1, max_length=64)
    decision: G07Decision
    comment: str | None = Field(default=None, max_length=4000)
    gate_id: str = Field(default="G07", min_length=1, max_length=16)


class G07ReviewResponse(ContractModel):
    run_id: str
    stage_id: str
    gate_id: str
    gate_version: str
    status: str
    decision: str | None = None
    package: dict[str, Any]
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    idempotent_replay: bool = False
    stale_reason: str | None = None
    comment: str | None = None
    decision_id: str | None = None


class StageSandboxRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)


class StageSandboxResponse(ContractModel):
    run_id: str
    stage_id: str
    sandbox_path: str
    status: str
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    verification: dict[str, Any] | None = None
    idempotent_replay: bool = False


class StageBootstrapInstallRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)


class StageBootstrapStatusResponse(ContractModel):
    run_id: str
    stage_id: str
    step_id: str
    name: str = "bootstrap_install"
    status: str
    command: str | None = None
    exit_code: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    artifact_ids: list[str] = Field(default_factory=list)
    runtime_profile: str | None = None
    stage_sandbox: str | None = None
    g07_status: str | None = None
    lifecycle_script_audit_ref: str | None = None
    pre_fingerprint: str | None = None
    post_fingerprint: str | None = None
    failure_classification: str | None = None
    blocker_code: str | None = None
    retry_eligible: bool = False
    recovery_required: bool = False
    reconstruction_guidance: str | None = None
    correlation_id: str | None = None


class StageBootstrapInstallResponse(StageBootstrapStatusResponse):
    idempotent_replay: bool = False
