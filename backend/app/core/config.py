"""Centralized, server-side configuration for the backend."""

from functools import lru_cache
from pathlib import Path
import os
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PLATFORM_REPOSITORY_ROOT = _BACKEND_ROOT.parent
_STABLE_TARGET_ROOT = Path(r"C:\Users\abdelilah.mortaki\Desktop\angularRus")

def _default_application_data_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "AngularMigrationControlTower" if base else Path.home() / ".local" / "share" / "AngularMigrationControlTower"


def _parse_csv(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
    else:
        items = value
    if not items:
        raise ValueError("value must include at least one item")
    return items


def _reject_root_path(path: Path, field_name: str) -> Path:
    if path.parent == path or str(path).strip() in {"", ".", "./"}:
        raise ValueError(f"{field_name} must not be empty, current directory, or filesystem root")
    return path


class Settings(BaseSettings):
    """Typed environment configuration; secrets are never exposed by the API."""

    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    application_data_root: Path = Field(default_factory=_default_application_data_root)
    database_url: str | None = None

    # Operational state is external; run data is derived from the output root.
    artifact_root: Path | None = None
    workspace_root: Path | None = None
    snapshot_root: Path | None = None
    delivery_root: Path | None = None
    sandbox_root: Path | None = None
    allowed_source_roots: Annotated[list[Path], NoDecode] = Field(default_factory=list)
    allowed_target_roots: Annotated[list[Path], NoDecode] = Field(default_factory=lambda: [_STABLE_TARGET_ROOT])
    platform_repository_root: Path = _PLATFORM_REPOSITORY_ROOT

    backend_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3301",
            "http://127.0.0.1:3301",
            "http://localhost:3302",
            "http://127.0.0.1:3302",
        ]
    )
    command_timeout_seconds: int = Field(default=300, gt=0)
    command_max_output_bytes: int = Field(default=1_000_000, gt=0)
    worker_lease_seconds: int = Field(default=120, gt=0)
    sse_heartbeat_seconds: int = Field(default=15, gt=0)
    sse_replay_retention_events: int = Field(default=1_000, gt=0)
    log_chunk_bytes: int = Field(default=64_000, gt=0)
    minimum_free_disk_bytes: int = Field(default=100 * 1024 * 1024, ge=0)

    sqlite_wal_enabled: bool = True
    sqlite_busy_timeout_ms: int = Field(default=5_000, gt=0)

    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_api_key: SecretStr | None = None
    llm_enabled: bool = False
    llm_input_price_per_million_tokens: float = Field(default=0.0, ge=0)
    llm_output_price_per_million_tokens: float = Field(default=0.0, ge=0)
    llm_pricing_version: str = Field(default='mvp-pricing-2026-01', min_length=1)
    llm_prompt_policy_version: str = Field(default='migration-policy-v1', min_length=1)
    llm_schema_registry_version: str = Field(default='schema-registry-v1', min_length=1)
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_transport_retries: int = Field(default=2, ge=0, le=5)
    llm_token_budget: int = Field(default=0, ge=0)
    llm_cost_budget_usd: float = Field(default=0.0, ge=0)

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Accept a comma-delimited environment value or a programmatic list."""
        return _parse_csv(value)

    @field_validator("allowed_source_roots", "allowed_target_roots", mode="before")
    @classmethod
    def parse_path_list(cls, value: str | list[str] | list[Path] | None) -> list[Path]:
        """Accept comma-delimited path lists from environment variables."""
        return [] if not value else [Path(item) for item in _parse_csv(value)]

    @field_validator(
        "application_data_root", "artifact_root", "workspace_root", "snapshot_root", "delivery_root", "sandbox_root",
        mode="after",
    )
    @classmethod
    def validate_root_path(cls, value: Path | None, info):
        return _reject_root_path(value, info.field_name) if value is not None else value

    @field_validator("allowed_source_roots", "allowed_target_roots", mode="after")
    @classmethod
    def validate_allowed_roots(cls, value: list[Path], info):
        return [_reject_root_path(path, info.field_name) for path in value] if value else []

    @model_validator(mode="after")
    def derive_external_operational_locations(self) -> "Settings":
        root = self.application_data_root.expanduser().resolve(strict=False)
        if self.database_url is None:
            object.__setattr__(self, "database_url", f"sqlite:///{(root / 'control-tower.db').as_posix()}")
        repository = self.platform_repository_root.resolve()
        for field, suffix in (("artifact_root", "operational-artifacts"), ("workspace_root", "workspaces"), ("snapshot_root", "snapshots"), ("delivery_root", "delivery"), ("sandbox_root", "sandboxes")):
            value = getattr(self, field) or root / suffix
            resolved = value.expanduser().resolve(strict=False)
            try:
                resolved.relative_to(repository)
                raise ValueError(f"{field} must be outside the platform repository")
            except ValueError as error:
                if str(error).endswith("platform repository"):
                    raise
            object.__setattr__(self, field, resolved)
        return self

    @model_validator(mode="after")
    def require_llm_settings_when_enabled(self) -> "Settings":
        """Avoid partial LLM configuration while keeping the mock gateway disabled."""
        if self.llm_enabled:
            missing = [
                variable
                for variable, value in {
                    "AZURE_OPENAI_ENDPOINT": self.azure_openai_endpoint,
                    "AZURE_OPENAI_DEPLOYMENT": self.azure_openai_deployment,
                    "AZURE_OPENAI_API_VERSION": self.azure_openai_api_version,
                    "AZURE_OPENAI_API_KEY": self.azure_openai_api_key,
                }.items()
                if value is None or (isinstance(value, str) and not value.strip())
            ]
            if missing:
                raise ValueError(
                    "LLM_ENABLED=true requires " + ", ".join(missing) + " to be configured"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Load settings once for application startup; tests can clear this cache."""
    return Settings()
