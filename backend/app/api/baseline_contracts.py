"""Typed HTTP contracts for the S1-F10 baseline surface."""

from typing import Any

from pydantic import Field

from app.domain.contracts import ContractModel


class BaselineWorkspaceRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)


class BaselinePrequalifyRequest(BaselineWorkspaceRequest):
    private_auth_configured: bool = False


class BaselineInstallAuthorizationRequest(BaselineWorkspaceRequest):
    decision: str = Field(pattern="^(authorize|reject)$")
    comment: str | None = Field(default=None, max_length=4000)


class BaselineResponse(ContractModel):
    run_id: str
    status: str
    policy_version: str
    snapshot_id: str
    sandbox_path: str
    input_fingerprint: str
    sandbox_fingerprint: str | None = None
    package: dict[str, Any] | None = None
    lockfile: dict[str, Any] | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    scripts: list[dict[str, Any]] = Field(default_factory=list)
    registry: dict[str, Any] | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    authorization_status: str
    checksum: str
    artifact_ids: list[str] = Field(default_factory=list)
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False

class BaselineInstallRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    runtime_profile_id: str = Field(min_length=1, max_length=128)
    runtime_checksum: str = Field(min_length=1, max_length=128)
    timeout_seconds: int = Field(default=3600, ge=1, le=86400)


class BaselineInstallResponse(ContractModel):
    run_id: str
    execution_id: str
    command_id: str
    status: str
    exit_code: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    timed_out: bool = False
    cancelled: bool = False
    reconstruction_required: bool = False
    runtime_checksum: str | None = None
    baseline_checksum: str | None = None
    start_fingerprint: dict[str, Any] | None = None
    end_fingerprint: dict[str, Any] | None = None
    blockers: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
class BaselineInstallCancelRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)