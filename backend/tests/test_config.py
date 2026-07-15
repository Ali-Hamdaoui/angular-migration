from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.policies.sprint0 import get_sprint0_policies


def test_settings_load_environment_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("SNAPSHOT_ROOT", str(tmp_path / "snapshots"))
    monkeypatch.setenv("DELIVERY_ROOT", str(tmp_path / "delivery"))
    monkeypatch.setenv("SANDBOX_ROOT", str(tmp_path / "sandboxes"))
    monkeypatch.setenv("ALLOWED_SOURCE_ROOTS", f"{tmp_path / 'source-a'},{tmp_path / 'source-b'}")
    monkeypatch.setenv("ALLOWED_TARGET_ROOTS", f"{tmp_path / 'target-a'},{tmp_path / 'target-b'}")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://localhost:3000, https://control.example")
    monkeypatch.setenv("COMMAND_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("COMMAND_MAX_OUTPUT_BYTES", "12345")
    monkeypatch.setenv("WORKER_LEASE_SECONDS", "60")
    monkeypatch.setenv("SSE_HEARTBEAT_SECONDS", "5")
    monkeypatch.setenv("SSE_REPLAY_RETENTION_EVENTS", "250")
    monkeypatch.setenv("LOG_CHUNK_BYTES", "4096")
    monkeypatch.setenv("SQLITE_WAL_ENABLED", "false")
    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "2500")
    monkeypatch.setenv("LLM_INPUT_PRICE_PER_MILLION_TOKENS", "0.15")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_PER_MILLION_TOKENS", "0.60")
    monkeypatch.setenv("LLM_TOKEN_BUDGET", "100000")
    monkeypatch.setenv("LLM_COST_BUDGET_USD", "25.50")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.database_url == "sqlite:///./test.db"
    assert settings.artifact_root == tmp_path / "runs"
    assert settings.workspace_root == tmp_path / "workspaces"
    assert settings.snapshot_root == tmp_path / "snapshots"
    assert settings.delivery_root == tmp_path / "delivery"
    assert settings.sandbox_root == tmp_path / "sandboxes"
    assert settings.allowed_source_roots == [tmp_path / "source-a", tmp_path / "source-b"]
    assert settings.allowed_target_roots == [tmp_path / "target-a", tmp_path / "target-b"]
    assert settings.backend_cors_origins == ["http://localhost:3000", "https://control.example"]
    assert settings.command_timeout_seconds == 90
    assert settings.command_max_output_bytes == 12345
    assert settings.worker_lease_seconds == 60
    assert settings.sse_heartbeat_seconds == 5
    assert settings.sse_replay_retention_events == 250
    assert settings.log_chunk_bytes == 4096
    assert settings.sqlite_wal_enabled is False
    assert settings.sqlite_busy_timeout_ms == 2500
    assert settings.llm_input_price_per_million_tokens == 0.15
    assert settings.llm_output_price_per_million_tokens == 0.60
    assert settings.llm_token_budget == 100000
    assert settings.llm_cost_budget_usd == 25.50


def test_settings_load_dotenv_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for variable in (
        "APP_ENV",
        "COMMAND_TIMEOUT_SECONDS",
        "BACKEND_CORS_ORIGINS",
        "WORKSPACE_ROOT",
        "ALLOWED_SOURCE_ROOTS",
    ):
        monkeypatch.delenv(variable, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=test\n"
        "COMMAND_TIMEOUT_SECONDS=45\n"
        "BACKEND_CORS_ORIGINS=http://localhost:3000,https://control.example\n"
        "WORKSPACE_ROOT=C:/external/workspaces-from-env\n"
        "ALLOWED_SOURCE_ROOTS=bundled Angular workspace,C:/projects/approved\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.app_env == "test"
    assert settings.command_timeout_seconds == 45
    assert settings.backend_cors_origins == ["http://localhost:3000", "https://control.example"]
    assert settings.workspace_root == Path("C:/external/workspaces-from-env").resolve()
    assert settings.allowed_source_roots == [Path("bundled Angular workspace"), Path("C:/projects/approved")]


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("COMMAND_TIMEOUT_SECONDS", "0"),
        ("COMMAND_MAX_OUTPUT_BYTES", "0"),
        ("WORKER_LEASE_SECONDS", "0"),
        ("SSE_HEARTBEAT_SECONDS", "0"),
        ("SSE_REPLAY_RETENTION_EVENTS", "0"),
        ("LOG_CHUNK_BYTES", "0"),
        ("SQLITE_BUSY_TIMEOUT_MS", "0"),
        ("LLM_INPUT_PRICE_PER_MILLION_TOKENS", "-1"),
        ("LLM_OUTPUT_PRICE_PER_MILLION_TOKENS", "-1"),
        ("LLM_TOKEN_BUDGET", "-1"),
        ("LLM_COST_BUDGET_USD", "-1"),
    ],
)
def test_invalid_numeric_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_root_paths_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTIFACT_ROOT", "/")

    with pytest.raises(ValidationError, match="filesystem root"):
        Settings(_env_file=None)


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


def test_env_example_contains_safe_placeholders() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "not-a-real-api-key" not in env_example
    assert "AZURE_OPENAI_API_KEY=" in env_example
    assert "APPLICATION_DATA_ROOT=" in env_example
    assert ".migration-factory/workspaces" not in env_example


def test_policy_defaults_are_injectable() -> None:
    policies = get_sprint0_policies()

    assert policies.topology.default_support_level == "historical_experimental"
    assert policies.commands.shell_allowed is False
    assert ("npm", ("--version",)) in policies.commands.version_commands
    assert policies.install_scripts.lifecycle_scripts_allowed is False
    assert policies.auto_approval.enabled_by_default is False
    assert "**/.env*" in policies.changed_files.blocked_globs
