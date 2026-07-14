"""Centralized, server-side configuration for the backend."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


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
    database_url: str = "sqlite:///./.migration-factory/migration-factory.db"

    artifact_root: Path = Path(".migration-factory/runs")
    workspace_root: Path = Path(".migration-factory/workspaces")
    snapshot_root: Path = Path(".migration-factory/snapshots")
    delivery_root: Path = Path(".migration-factory/delivery")
    sandbox_root: Path = Path(".migration-factory/sandboxes")
    allowed_source_roots: Annotated[list[Path], NoDecode] = Field(default_factory=lambda: [Path("demo-apps")])
    allowed_target_roots: Annotated[list[Path], NoDecode] = Field(default_factory=lambda: [Path(".migration-factory")])

    backend_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
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
    llm_token_budget: int = Field(default=0, ge=0)
    llm_cost_budget_usd: float = Field(default=0.0, ge=0)

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Accept a comma-delimited environment value or a programmatic list."""
        return _parse_csv(value)

    @field_validator("allowed_source_roots", "allowed_target_roots", mode="before")
    @classmethod
    def parse_path_list(cls, value: str | list[str] | list[Path]) -> list[Path]:
        """Accept comma-delimited path lists from environment variables."""
        return [Path(item) for item in _parse_csv(value)]

    @field_validator(
        "artifact_root",
        "workspace_root",
        "snapshot_root",
        "delivery_root",
        "sandbox_root",
        mode="after",
    )
    @classmethod
    def validate_root_path(cls, value: Path, info):
        return _reject_root_path(value, info.field_name)

    @field_validator("allowed_source_roots", "allowed_target_roots", mode="after")
    @classmethod
    def validate_allowed_roots(cls, value: list[Path], info):
        return [_reject_root_path(path, info.field_name) for path in value]

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
