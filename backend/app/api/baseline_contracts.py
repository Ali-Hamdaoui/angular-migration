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
