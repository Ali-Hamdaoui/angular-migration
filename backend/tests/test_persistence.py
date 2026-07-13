from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.repositories.migration_run_repository import MigrationRunRepository, StaleStateVersionError
from app.repositories.models import (
    AgentExecutionModel,
    ApprovalEventModel,
    ApprovalPolicyEventModel,
    ArtifactMetadataModel,
    Base,
    CommandExecutionModel,
    LlmUsageRecordModel,
    MigrationRunModel,
    MigrationStageModel,
    RepairAttemptModel,
    RunAssuranceStatusModel,
    StageStepModel,
    WorkerLeaseModel,
    WorkflowEventModel,
)
from app.repositories.session import create_database_engine


EXPECTED_TABLES = {
    "agent_executions",
    "approval_events",
    "approval_policy_events",
    "artifact_metadata",
    "command_executions",
    "llm_usage_records",
    "migration_runs",
    "migration_stages",
    "repair_attempts",
    "run_assurance_statuses",
    "stage_steps",
    "worker_leases",
    "workflow_events",
}


def _alembic_config(database_url: str) -> Config:
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    return alembic_config


def _create_run(repository: MigrationRunRepository, now: datetime) -> MigrationRunModel:
    return repository.add(
        MigrationRunModel(
            id="mock-run-001",
            status="CREATED",
            run_phase="PREFLIGHT_SNAPSHOT",
            state_version=1,
            source_version_family="18.x",
            target_version_family="21.x",
            source_version_detected="18.2.x",
            target_version_resolved=None,
            source_angular_version="18.x",
            target_angular_version="21.x",
            created_at=now,
            updated_at=now,
        )
    )


def test_alembic_creates_initial_sqlite_schema(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration-factory.db'}"

    command.upgrade(_alembic_config(database_url), "head")

    engine = create_database_engine(database_url)
    inspector = inspect(engine)
    assert EXPECTED_TABLES.issubset(inspector.get_table_names())
    run_columns = {column["name"] for column in inspector.get_columns("migration_runs")}
    assert {"run_phase", "state_version", "source_version_family", "target_version_resolved"}.issubset(run_columns)
    event_unique_constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints("workflow_events")
    }
    command_unique_constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints("command_executions")
    }
    assert "uq_workflow_events_run_sequence" in event_unique_constraints
    assert "uq_workflow_events_run_idempotency" in event_unique_constraints
    assert "uq_command_executions_run_idempotency" in command_unique_constraints
    artifact_columns = {column["name"] for column in inspector.get_columns("artifact_metadata")}
    assert "checksum" in artifact_columns
    assert "schema_version" in artifact_columns
    assert not {"content", "blob", "body"}.intersection(artifact_columns)
    engine.dispose()


def test_sqlite_wal_and_busy_timeout_are_configurable(tmp_path: Path) -> None:
    engine = create_database_engine(
        f"sqlite:///{tmp_path / 'wal.db'}",
        sqlite_wal_enabled=True,
        sqlite_busy_timeout_ms=2500,
    )

    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 2500
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"

    engine.dispose()


def test_migration_run_repository_inserts_and_reads_complete_mock_snapshot(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'repository.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    repository = MigrationRunRepository(session)
    now = datetime.now(UTC)

    _create_run(repository, now)
    session.add_all(
        [
            MigrationStageModel(
                id="stage-18-19",
                run_id="mock-run-001",
                stage_order=1,
                source_version_family="18.x",
                target_version_family="19.x",
                source_version_detected="18.2.x",
                target_version_resolved=None,
                source_angular_version="18.x",
                target_angular_version="19.x",
                status="PENDING",
                current_agent=None,
                created_at=now,
                started_at=None,
                completed_at=None,
            ),
            StageStepModel(
                id="step-plan",
                run_id="mock-run-001",
                stage_id="stage-18-19",
                name="plan_approval",
                status="WAITING_APPROVAL",
                component_type="deterministic_gate",
                attempt_id="attempt-001",
                idempotency_key="step-plan-001",
                started_at=None,
                completed_at=None,
            ),
            AgentExecutionModel(
                id="agent-001",
                run_id="mock-run-001",
                stage_id="stage-18-19",
                agent_name="Planning Agent",
                status="COMPLETED",
                started_at=now,
                finished_at=now,
                summary="Mock plan prepared.",
            ),
            ApprovalEventModel(
                id="approval-001",
                run_id="mock-run-001",
                stage_id="stage-18-19",
                decision="PENDING",
                requested_at=now,
                decided_at=None,
                actor=None,
                rationale=None,
            ),
            ApprovalPolicyEventModel(
                id="approval-policy-001",
                run_id="mock-run-001",
                mode="off",
                changed_by="system",
                changed_at=now,
                reason="Sprint 0 default",
            ),
            ArtifactMetadataModel(
                id="artifact-001",
                run_id="mock-run-001",
                stage_id="stage-18-19",
                artifact_type="markdown",
                relative_path="03_planning/mock_migration_plan.md",
                checksum="sha256:mock",
                schema_version=1,
                created_at=now,
            ),
            CommandExecutionModel(
                id="command-001",
                run_id="mock-run-001",
                stage_id="stage-18-19",
                idempotency_key="command-key-001",
                requested_by="Transformation Agent",
                executable="npx",
                arguments=["ng", "update", "@angular/core@19"],
                working_directory_alias="run_workspace",
                runtime_profile_id="node-20-npm-10",
                status="PENDING",
                requested_at=now,
                started_at=None,
                finished_at=None,
                exit_code=None,
            ),
            WorkerLeaseModel(
                id="lease-001",
                run_id="mock-run-001",
                worker_id="worker-001",
                lease_owner="mock-orchestrator",
                acquired_at=now,
                expires_at=now + timedelta(seconds=120),
            ),
            RepairAttemptModel(
                id="repair-001",
                run_id="mock-run-001",
                stage_id="stage-18-19",
                attempt_number=1,
                status="SKIPPED",
                risk_level="low",
                created_at=now,
                diagnosis="No repair needed.",
            ),
            LlmUsageRecordModel(
                id="usage-001",
                run_id="mock-run-001",
                model="mock-gateway",
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
                input_price_per_million=0.0,
                output_price_per_million=0.0,
                cost_usd=0.0,
                created_at=now,
            ),
            RunAssuranceStatusModel(
                run_id="mock-run-001",
                technical_upgrade_status="not_evaluated",
                functional_parity_status="manual_required",
                security_assurance_status="not_evaluated",
                quality_assurance_status="not_evaluated",
                delivery_readiness="not_evaluated",
                updated_at=now,
            ),
        ]
    )
    repository.append_event(
        event_id="event-001",
        run_id="mock-run-001",
        event_type="run_state_changed",
        occurred_at=now,
        payload={"status": "CREATED"},
    )
    session.commit()

    persisted = repository.get_by_id("mock-run-001")

    assert persisted is not None
    assert persisted.status == "CREATED"
    assert persisted.run_phase == "PREFLIGHT_SNAPSHOT"
    assert persisted.state_version == 1
    assert session.query(MigrationStageModel).count() == 1
    assert session.query(StageStepModel).count() == 1
    assert session.query(WorkflowEventModel).one().sequence == 1
    assert session.query(ArtifactMetadataModel).one().checksum == "sha256:mock"
    session.close()
    engine.dispose()


def test_stale_expected_state_version_is_rejected(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'stale-version.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    repository = MigrationRunRepository(session)
    now = datetime.now(UTC)
    _create_run(repository, now)
    session.commit()

    updated = repository.update_status_with_version(
        run_id="mock-run-001",
        expected_state_version=1,
        status="RUNNING",
        run_phase="DISCOVERY_BASELINE",
        updated_at=now,
    )
    assert updated.state_version == 2
    with pytest.raises(StaleStateVersionError):
        repository.update_status_with_version(
            run_id="mock-run-001",
            expected_state_version=1,
            status="WAITING",
            run_phase="FEASIBILITY_PLANNING",
            updated_at=now,
        )
    session.rollback()
    session.close()
    engine.dispose()


def test_event_sequences_are_monotonic_and_unique_per_run(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'events.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    repository = MigrationRunRepository(session)
    now = datetime.now(UTC)
    _create_run(repository, now)

    first = repository.append_event(
        event_id="event-001",
        run_id="mock-run-001",
        event_type="run_state_changed",
        occurred_at=now,
    )
    second = repository.append_event(
        event_id="event-002",
        run_id="mock-run-001",
        event_type="stage_state_changed",
        occurred_at=now,
    )
    session.add(
        WorkflowEventModel(
            id="event-duplicate-sequence",
            run_id="mock-run-001",
            stage_id=None,
            event_type="agent_state_changed",
            sequence=2,
            payload={},
            occurred_at=now,
        )
    )

    assert (first.sequence, second.sequence) == (1, 2)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    session.close()
    engine.dispose()


def test_duplicate_command_idempotency_key_is_constrained_per_run(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'commands.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    repository = MigrationRunRepository(session)
    now = datetime.now(UTC)
    _create_run(repository, now)

    repository.add_command_execution(
        CommandExecutionModel(
            id="command-001",
            run_id="mock-run-001",
            stage_id=None,
            idempotency_key="same-key",
            requested_by="test",
            executable="python",
            arguments=["--version"],
            working_directory_alias="run_workspace",
            runtime_profile_id="python-runtime",
            status="PENDING",
            requested_at=now,
            started_at=None,
            finished_at=None,
            exit_code=None,
        )
    )

    with pytest.raises(IntegrityError):
        repository.add_command_execution(
            CommandExecutionModel(
                id="command-002",
                run_id="mock-run-001",
                stage_id=None,
                idempotency_key="same-key",
                requested_by="test",
                executable="python",
                arguments=["--version"],
                working_directory_alias="run_workspace",
                runtime_profile_id="python-runtime",
                status="PENDING",
                requested_at=now,
                started_at=None,
                finished_at=None,
                exit_code=None,
            )
        )
    session.rollback()
    session.close()
    engine.dispose()
