"""Database identity and startup compatibility checks."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import Settings

LLM_PROVIDER_FAILURE_COLUMNS = (
    "provider_http_status",
    "provider_error_code",
    "sanitized_provider_message",
    "provider_request_id",
    "failure_stage",
)
TRANSFORMER_TABLES = (
    "transformation_continuations",
    "stage_checkpoints",
    "stage_prompt_requests",
    "stage_gate_packages",
    "stage_gate_decisions",
)


def database_path(database_url: str) -> Path | None:
    """Return the resolved file path for a SQLite URL, or None for other DBs."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database).expanduser().resolve(strict=False)


def expected_heads(backend_root: Path) -> tuple[str, ...]:
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    return tuple(sorted(ScriptDirectory.from_config(config).get_heads()))


def active_revisions(engine: Engine) -> tuple[str, ...]:
    with engine.connect() as connection:
        table_exists = inspect(connection).has_table("alembic_version")
        if not table_exists:
            return ()
        return tuple(sorted(row[0] for row in connection.execute(text("SELECT version_num FROM alembic_version"))))


def assert_schema_compatible(engine: Engine, settings: Settings) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Fail before serving requests when migration or required schema is absent."""
    backend_root = settings.platform_repository_root / "backend"
    current = active_revisions(engine)
    heads = expected_heads(backend_root)
    path = database_path(settings.database_url or "")
    missing = set(LLM_PROVIDER_FAILURE_COLUMNS)
    missing_tables = set(TRANSFORMER_TABLES)
    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        columns = (
            {column["name"] for column in inspector.get_columns("llm_invocations")}
            if "llm_invocations" in table_names
            else set()
        )
        missing_tables -= table_names
    missing = set(LLM_PROVIDER_FAILURE_COLUMNS) - columns
    if current != heads or missing or missing_tables:
        missing_text = ", ".join(sorted(missing)) or "none"
        missing_table_text = ", ".join(sorted(missing_tables)) or "none"
        raise RuntimeError(
            "Database schema is incompatible with the backend. "
            f"active database path: {path or '<non-file database>'}; "
            f"current revision: {', '.join(current) or '<none>'}; "
            f"expected head(s): {', '.join(heads) or '<none>'}; "
            f"missing required columns: {missing_text}; "
            f"missing required tables: {missing_table_text}; "
            "safe migration command: python -m alembic -c alembic.ini upgrade heads"
        )
    return current, heads
