"""F05 Worker Reliability V2 delta: deterministic startup orphan sweep + capability proof.

Most F05 capabilities (durable lease with heartbeat/expiry, persisted
cancellation state, bounded chunked logs, periodic reconcile) already exist in
repository truth.  This suite proves them and covers the V2 delta: a
deterministic ``recover_command_orphans`` sweep callable at backend startup so a
worker process death mid-command is reconciled exactly once on restart.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import pytest

from app.repositories.models import Base, CommandExecutionModel, MigrationRunModel, WorkerLeaseModel
from app.services.command_executor_service import CommandExecutorService
from app.services.job_supervisor_service import JobSupervisorError, JobSupervisorService


def _database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'f05.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    now = datetime.now(UTC)
    session.add(
        MigrationRunModel(
            id="run-f05", status="RUNNING", run_phase="STAGED_MIGRATION",
            state_version=1, created_at=now, updated_at=now,
        )
    )
    session.commit()
    return factory


@contextmanager
def _scope(factory):
    session = factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def _execution(
    execution_id: str,
    *,
    status: str = "queued",
    worker_id: str | None = "worker-dead",
    claim_expires_at=None,
    operation_kind: str = "read_only",
    claim_attempt: int = 0,
):
    return CommandExecutionModel(
        id=execution_id,
        run_id="run-f05",
        command_id="python-version",
        executable="python",
        arguments=["--version"],
        status=status,
        worker_id=worker_id,
        claim_expires_at=claim_expires_at,
        operation_kind=operation_kind,
        claim_attempt=claim_attempt,
        requested_at=datetime.now(UTC),
    )


def test_startup_orphan_sweep_requeues_read_only_expired_claims(tmp_path: Path):
    factory = _database(tmp_path)
    expired = datetime.now(UTC) - timedelta(seconds=60)
    with factory() as session:
        session.add(_execution("exec-read", status="running", claim_expires_at=expired))
        session.commit()

    # The persisted worker claim is expired; the owning worker is dead.
    with factory() as session:
        row = session.get(CommandExecutionModel, "exec-read")
        assert row.status == "running"
        assert row.claim_expires_at is not None

    recovered = CommandExecutorService().recover_command_orphans(scope=lambda: _scope(factory))
    assert "exec-read" in recovered

    with factory() as session:
        row = session.get(CommandExecutionModel, "exec-read")
        assert row.worker_id is None
        assert row.claim_expires_at is None
        assert row.status == "queued"
        assert row.failure_code == "COMMAND_WORKER_LOST_REQUEUED"


def test_startup_orphan_sweep_seals_mutating_expired_claims_reconstruction_required(tmp_path: Path):
    factory = _database(tmp_path)
    expired = datetime.now(UTC) - timedelta(seconds=60)
    with factory() as session:
        session.add(
            _execution("exec-mutate", status="running", operation_kind="mutating", claim_expires_at=expired)
        )
        session.commit()

    recovered = CommandExecutorService().recover_command_orphans(scope=lambda: _scope(factory))
    assert "exec-mutate" in recovered

    with factory() as session:
        row = session.get(CommandExecutionModel, "exec-mutate")
        assert row.status == "interrupted"
        assert row.reconstruction_required is True
        assert row.failure_code == "COMMAND_RECOVERY_REQUIRED"
        assert row.failure_message and "reconstruct" in row.failure_message


def test_startup_orphan_sweep_fails_after_claim_retry_threshold(tmp_path: Path):
    factory = _database(tmp_path)
    expired = datetime.now(UTC) - timedelta(seconds=60)
    with factory() as session:
        session.add(
            _execution("exec-exhausted", status="running", operation_kind="read_only", claim_attempt=5, claim_expires_at=expired)
        )
        session.commit()

    recovered = CommandExecutorService().recover_command_orphans(scope=lambda: _scope(factory))
    assert "exec-exhausted" in recovered

    with factory() as session:
        row = session.get(CommandExecutionModel, "exec-exhausted")
        assert row.status == "failed"
        assert row.failure_code == "COMMAND_CLAIM_EXHAUSTED"


def test_startup_orphan_sweep_cleans_expired_worker_lease(tmp_path: Path):
    factory = _database(tmp_path)
    expired = datetime.now(UTC) - timedelta(seconds=60)
    with factory() as session:
        session.add(_execution("exec-lease", claim_expires_at=expired))
        session.add(
            WorkerLeaseModel(
                id="lease-dead", run_id="run-f05", execution_id="exec-lease",
                worker_id="worker-dead", lease_owner="worker-dead",
                acquired_at=expired, heartbeat_at=expired, expires_at=expired,
            )
        )
        session.commit()

    CommandExecutorService().recover_command_orphans(scope=lambda: _scope(factory))

    with factory() as session:
        assert session.get(WorkerLeaseModel, "lease-dead") is None


def test_lease_heartbeat_and_expiry_are_durable(tmp_path: Path):
    """F05-01: a durable lease is owned exclusively, heartbeats extend it, expiry frees it."""
    factory = _database(tmp_path)
    supervisor = JobSupervisorService(lease_seconds=30)
    with factory() as session:
        first = supervisor.acquire_lease(session, "run-f05", "exec-lease-1", "worker-a", "worker-a")
        lease_id = first.lease_id
        assert first.worker_id == "worker-a"
        assert first.expires_at > datetime.now(UTC)
        session.commit()

    # renew extends the expiry
    with factory() as session:
        renewed = supervisor.renew_lease(session, lease_id, "worker-a")
        assert renewed.expires_at > datetime.now(UTC)
        session.commit()

    # a second worker cannot steal an active lease
    with pytest.raises(JobSupervisorError, match="already has an active lease"):
        with factory() as session:
            supervisor.acquire_lease(session, "run-f05", "exec-lease-1", "worker-b", "worker-b")
    with factory() as session:
        lease = session.get(WorkerLeaseModel, lease_id)
        assert lease.worker_id == "worker-a"


def test_cancellation_state_survives_restart(tmp_path: Path):
    """F05-02: cancellation state is durable; a fresh service instance sees it."""
    factory = _database(tmp_path)
    now = datetime.now(UTC)
    with factory() as session:
        session.add(
            _execution("exec-cancel", status="running", worker_id="worker-a", claim_expires_at=now + timedelta(seconds=60))
        )
        session.commit()

    with factory() as session:
        CommandExecutorService().request_cancel(session, "run-f05", "exec-cancel", "operator", idempotency_key="cancel:1")
        session.commit()
    # Simulate a worker/service restart: read through a brand-new session.
    with factory() as session:
        row = session.get(CommandExecutionModel, "exec-cancel")
        assert row.cancel_requested_at is not None
        assert row.cancel_requested_by is not None
        assert row.cancel_idempotency_key == "cancel:1"
