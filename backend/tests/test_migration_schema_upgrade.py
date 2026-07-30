from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.repositories.models import ArtifactMetadataModel, MigrationRunModel


def _alembic_config(database_url: str) -> Config:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_run_readiness_upgrade_backfills_stage_parents_for_historical_artifacts(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    config = _alembic_config(database_url)
    command.upgrade(config, "20260729_33")
    now = datetime(2026, 7, 29, tzinfo=UTC)
    engine = create_engine(database_url)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        with connection.begin():
            connection.execute(
                MigrationRunModel.__table__.insert().values(
                    id="historical-run",
                    status="FAILED",
                    run_phase="FEASIBILITY_PLANNING",
                    phase_status="failed",
                    approval_status="approved",
                    repair_status="not_required",
                    state_version=1,
                    artifact_root=str(tmp_path / "artifacts"),
                    created_at=now,
                    updated_at=now,
                )
            )
            connection.execute(
                ArtifactMetadataModel.__table__.insert().values(
                    id="metadata-historical-stage-artifact",
                    run_id="historical-run",
                    stage_id="angular-18-to-19",
                    artifact_type="json",
                    relative_path="stages/angular-18-to-19/stage-execution-plan.json",
                    checksum="sha256:" + "1" * 64,
                    created_at=now,
                )
            )
            connection.execute(
                ArtifactMetadataModel.__table__.insert().values(
                    id="metadata-historical-phase-artifact",
                    run_id="historical-run",
                    stage_id="03_planning",
                    artifact_type="json",
                    relative_path="03_planning/versions/v1/planning-explanation.json",
                    checksum="sha256:" + "2" * 64,
                    created_at=now,
                )
            )
    engine.dispose()

    command.upgrade(config, "heads")

    verified = create_engine(database_url)
    with verified.connect() as connection:
        parent = connection.exec_driver_sql(
            "SELECT run_id, stage_order, status FROM migration_stages WHERE id = 'angular-18-to-19'"
        ).one()
        assert tuple(parent) == ("historical-run", 1, "planned")
        phase_owner = connection.exec_driver_sql(
            "SELECT stage_id FROM artifact_metadata WHERE id = 'metadata-historical-phase-artifact'"
        ).one()
        assert phase_owner[0] is None
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM migration_stages WHERE id = '03_planning'"
        ).scalar_one() == 0
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    verified.dispose()


def test_transformer_schema_upgrades_and_downgrades_from_current_head(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'transformer-migration.db'}"
    config = _alembic_config(database_url)
    command.upgrade(config, "20260729_35")

    command.upgrade(config, "heads")

    engine = create_engine(database_url)
    schema = inspect(engine)
    assert {
        "transformation_continuations",
        "stage_checkpoints",
        "stage_prompt_requests",
        "stage_gate_packages",
        "stage_gate_decisions",
    }.issubset(schema.get_table_names())
    assert {
        "claim_attempt",
        "claim_expires_at",
        "prompt_request_id",
        "operation_kind",
        "checkpoint_id",
    }.issubset({column["name"] for column in schema.get_columns("command_executions")})
    assert {
        "source_checkpoint_id",
        "input_fingerprint",
        "last_verified_fingerprint",
        "last_verified_at",
    }.issubset({column["name"] for column in schema.get_columns("stage_workspace_bindings")})
    engine.dispose()

    command.downgrade(config, "20260729_35")

    downgraded = create_engine(database_url)
    schema = inspect(downgraded)
    assert "transformation_continuations" not in schema.get_table_names()
    assert "claim_attempt" not in {column["name"] for column in schema.get_columns("command_executions")}
    downgraded.dispose()
