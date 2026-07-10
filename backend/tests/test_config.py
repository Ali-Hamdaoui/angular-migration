from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_load_environment_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("SANDBOX_ROOT", str(tmp_path / "sandboxes"))
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://localhost:3000, https://control.example")
    monkeypatch.setenv("COMMAND_TIMEOUT_SECONDS", "90")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.database_url == "sqlite:///./test.db"
    assert settings.artifact_root == tmp_path / "runs"
    assert settings.sandbox_root == tmp_path / "sandboxes"
    assert settings.backend_cors_origins == ["http://localhost:3000", "https://control.example"]
    assert settings.command_timeout_seconds == 90


def test_settings_load_dotenv_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for variable in ("APP_ENV", "COMMAND_TIMEOUT_SECONDS", "BACKEND_CORS_ORIGINS"):
        monkeypatch.delenv(variable, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=test\nCOMMAND_TIMEOUT_SECONDS=45\nBACKEND_CORS_ORIGINS=http://localhost:3000,https://control.example\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.app_env == "test"
    assert settings.command_timeout_seconds == 45
    assert settings.backend_cors_origins == ["http://localhost:3000", "https://control.example"]


def test_enabled_llm_requires_all_azure_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="LLM_ENABLED=true requires"):
        Settings(_env_file=None)


def test_secret_is_redacted_in_settings_representation(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "not-a-real-api-key"
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", secret)

    settings = Settings(_env_file=None)

    assert secret not in repr(settings)
    assert settings.azure_openai_api_key is not None
    assert settings.azure_openai_api_key.get_secret_value() == secret
