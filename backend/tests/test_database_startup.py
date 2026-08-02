from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.core.database import assert_schema_compatible, database_path, expected_heads


def test_database_path_and_heads_are_resolved_from_repository_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None, application_data_root=tmp_path / "AngularMigrationControlTower")
    assert database_path(settings.database_url) == (tmp_path / "AngularMigrationControlTower" / "control-tower.db").resolve()
    assert expected_heads(settings.platform_repository_root / "backend") == ("20260802_39",)


def test_startup_rejects_head_claim_with_missing_provider_failure_columns(tmp_path: Path):
    database = tmp_path / "AngularMigrationControlTower" / "control-tower.db"
    database.parent.mkdir(parents=True)
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version(version_num) VALUES ('20260724_19')"))
        connection.execute(text("CREATE TABLE llm_invocations (id VARCHAR(64) PRIMARY KEY)"))
    settings = Settings(_env_file=None, database_url=f"sqlite:///{database}", platform_repository_root=Path(__file__).resolve().parents[2])
    with pytest.raises(RuntimeError, match="missing required columns:.*provider_http_status"):
        assert_schema_compatible(engine, settings)
