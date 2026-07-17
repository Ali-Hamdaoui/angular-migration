from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: str


class VersionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    version: str
    environment: str


class RuntimeInventoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: Literal["node", "npm", "npx", "git", "python"]
    executable: str | None = None
    attempted_executable: str | None = None
    version: str | None = None
    installation_root: str | None = None
    status: Literal["available", "missing", "failed"]
    reason: str | None = None
    remediation: str | None = None


class LocalStorageReadiness(BaseModel):
    model_config = ConfigDict(frozen=True)
    database_path: str
    artifact_root: str
    writable: bool
    local_filesystem: bool
    free_bytes: int = Field(ge=0)
    status: Literal["available", "degraded", "blocked"]


class CorporateNetworkReadiness(BaseModel):
    model_config = ConfigDict(frozen=True)
    registry_configured: bool
    proxy_configured: bool
    https_proxy_configured: bool
    strict_ssl: bool
    custom_ca_configured: bool
    credentials_redacted: bool = True


class EnvironmentCapabilitySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    snapshot_id: str
    captured_at: datetime
    policy_version: str
    status: Literal["available", "degraded", "blocked"]
    runtimes: list[RuntimeInventoryEntry]
    node_npm_npx_paired: bool
    git_ready: bool
    python_ready: bool
    storage: LocalStorageReadiness
    network: CorporateNetworkReadiness
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checksum: str


class EnvironmentCapabilityResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    snapshot: EnvironmentCapabilitySnapshot
    artifact: dict[str, str] | None = None


class RefreshEnvironmentRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    idempotency_key: str = Field(min_length=1)
    actor: str | None = None

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("idempotency_key must not be blank")
        return value
