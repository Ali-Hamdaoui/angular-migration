from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.repositories.models import Base, CommandExecutionModel, MigrationRunModel, WorkerLeaseModel
from app.services.command_executor_service import CommandExecutorService
from app.services.job_supervisor_service import JobSupervisorService


def _database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'command-recovery.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    now = datetime.now(UTC)
    session.add(
        MigrationRunModel(
            id="run-1",
            status="RUNNING",
            run_phase="STAGED_MIGRATION",
            state_version=1,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return engine, factory


def _execution(
    execution_id: str,
    *,
    status: str = "queued",
    worker_id: str | None = None,
    claim_expires_at=None,
    operation_kind: str = "read_only",
):
    return CommandExecutionModel(
        id=execution_id,
        run_id="run-1",
        command_id="python-version",
        executable="python",
        arguments=["--version"],
        status=status,
        worker_id=worker_id,
        claim_expires_at=claim_expires_at,
        operation_kind=operation_kind,
        requested_at=datetime.now(UTC),
    )


def test_command_claim_allows_only_one_worker(tmp_path: Path):
    engine, factory = _database(tmp_path)
    first = factory()
    first.add(_execution("exec-1"))
    first.commit()
    second = factory()
    now = datetime.now(UTC)

    assert CommandExecutorService().claim_next_execution(first, "worker-1", now) == "exec-1"
    first.commit()
    assert CommandExecutorService().claim_next_execution(second, "worker-2", now) is None
    assert second.query(WorkerLeaseModel).count() == 1
    first.close()
    second.close()
    engine.dispose()


def test_queued_claim_with_expired_lease_is_reclaimed(tmp_path: Path):
    engine, factory = _database(tmp_path)
    session = factory()
    now = datetime.now(UTC)
    session.add(
        _execution(
            "exec-expired",
            worker_id="dead-worker",
            claim_expires_at=now - timedelta(seconds=1),
        )
    )
    session.commit()

    claimed = CommandExecutorService().claim_next_execution(session, "worker-new", now)

    assert claimed == "exec-expired"
    assert session.get(CommandExecutionModel, claimed).worker_id == "worker-new"
    session.close()
    engine.dispose()


def test_running_mutation_with_expired_lease_requires_reconstruction(tmp_path: Path):
    engine, factory = _database(tmp_path)
    session = factory()
    now = datetime.now(UTC)
    session.add(
        _execution(
            "exec-mutating",
            status="running",
            worker_id="dead-worker",
            claim_expires_at=now - timedelta(seconds=1),
            operation_kind="mutating",
        )
    )
    session.commit()

    recovered = CommandExecutorService().reconcile_expired_executions(session, now)

    model = session.get(CommandExecutionModel, "exec-mutating")
    assert recovered == ["exec-mutating"]
    assert model.status == "interrupted"
    assert model.reconstruction_required is True
    assert model.worker_id is None
    session.close()
    engine.dispose()


def test_queued_command_can_be_cancelled_and_survives_service_restart(tmp_path: Path):
    engine, factory = _database(tmp_path)
    session = factory()
    session.add(_execution("exec-cancel"))
    session.commit()

    JobSupervisorService().cancel_command(
        session,
        "run-1",
        "exec-cancel",
        "operator",
        idempotency_key="cancel-queued",
    )
    session.commit()
    session.close()

    restarted = factory()
    model = restarted.get(CommandExecutionModel, "exec-cancel")
    assert model.status == "cancelled"
    assert model.cancel_requested_by == "operator"
    restarted.close()
    engine.dispose()


def test_active_command_partial_unique_index_blocks_duplicate_delivery(tmp_path: Path):
    engine, factory = _database(tmp_path)
    session = factory()
    session.add_all([_execution("exec-a"), _execution("exec-b")])

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()
    session.close()
    engine.dispose()
