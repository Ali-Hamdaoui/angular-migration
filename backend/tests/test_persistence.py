from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.repositories.migration_run_repository import MigrationRunRepository
from app.repositories.models import Base, MigrationRunModel
from app.repositories.session import create_database_engine


def test_alembic_creates_initial_sqlite_schema(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration-factory.db'}"
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "head")

    engine = create_database_engine(database_url)
    expected_tables = {
        "agent_executions",
        "approval_events",
        "artifact_metadata",
        "migration_runs",
        "migration_stages",
        "workflow_events",
    }
    assert expected_tables.issubset(inspect(engine).get_table_names())
    engine.dispose()


def test_migration_run_repository_inserts_and_reads_a_run(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'repository.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    repository = MigrationRunRepository(session)
    created_at = datetime.now(UTC)

    repository.add(
        MigrationRunModel(
            id="mock-run-001",
            status="CREATED",
            source_angular_version="18.x",
            target_angular_version="21.x",
            created_at=created_at,
            updated_at=created_at,
        )
    )
    session.commit()

    persisted = repository.get_by_id("mock-run-001")

    assert persisted is not None
    assert persisted.status == "CREATED"
    assert persisted.source_angular_version == "18.x"
    assert persisted.target_angular_version == "21.x"
    session.close()
    engine.dispose()