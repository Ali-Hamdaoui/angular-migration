"""Centralized, server-side configuration for the backend."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


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
    sandbox_root: Path = Path(".migration-factory/sandboxes")
    backend_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    command_timeout_seconds: int = Field(default=300, gt=0)
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str | None = None
    azure_openai_api_key: SecretStr | None = None
    llm_enabled: bool = False

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Accept a comma-delimited environment value or a programmatic list."""
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        else:
            origins = value
        if not origins:
            raise ValueError("BACKEND_CORS_ORIGINS must include at least one origin")
        return origins

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
