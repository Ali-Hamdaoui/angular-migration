"""T08: terminal-command waiter reconciliation.

A continuation parked on ``waiting_command`` must be deterministically
released when its command reaches ANY terminal state: the durable worker
wakes the waiter for the execution it just ran, the reconciliation sweep
releases waiters whose command reached a terminal state without a wake
(reconcile-to-interrupted, lost wake after a worker crash), and a queued
command cancelled before spawn wakes the waiter directly.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.orchestration.transformer_worker import TransformerWorker
from app.repositories.models import (
    Base,
    CommandAuthorizationAuditModel,
    CommandExecutionModel,
    MigrationRunModel,
    TransformationContinuationModel,
)
from app.services.command_executor_service import (
    CommandExecutorError,
    CommandExecutorService,
)
from app.services.job_supervisor_service import JobSupervisorService
from app.services.transformation_continuation_service import TransformationContinuationService

NOW = datetime(2026, 8, 1, tzinfo=UTC)


def _database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'wake.db'}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _scope(factory):
    @contextmanager
    def scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return scope


def _worker(factory, *, workflow=None) -> TransformerWorker:
    return TransformerWorker(
        command_executor=CommandExecutorService(),
        continuation_service=TransformationContinuationService(),
        workflow=workflow or MagicMock(),
        scope=_scope(factory),
    )


def _seed_run(factory, run_id: str = "run-1", *, now: datetime = NOW) -> None:
    session = factory()
    session.add(
        MigrationRunModel(
            id=run_id,
            status="RUNNING",
            run_phase="STAGED_MIGRATION",
            state_version=1,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    session.close()


def _seed_execution(
    factory,
    execution_id: str = "exec-1",
    *,
    run_id: str = "run-1",
    stage_id: str = "stage-1",
    status: str = "queued",
    worker_id: str | None = None,
    claim_expires_at: datetime | None = None,
    operation_kind: str = "read_only",
    reconstruction_required: bool = False,
    authorization_id: str | None = None,
    now: datetime = NOW,
) -> None:
    session = factory()
    session.add(
        CommandExecutionModel(
            id=execution_id,
            run_id=run_id,
            stage_id=stage_id,
            command_id="npm-ci-bootstrap",
            executable="npm",
            arguments=["ci"],
            status=status,
            worker_id=worker_id,
            claim_expires_at=claim_expires_at,
            operation_kind=operation_kind,
            reconstruction_required=reconstruction_required,
            authorization_id=authorization_id,
            requested_at=now,
            state_version=1,
        )
    )
    session.commit()
    session.close()


def _seed_authorization(
    factory,
    authorization_id: str = "auth-1",
    *,
    run_id: str = "run-1",
    stage_id: str = "stage-1",
    now: datetime = NOW,
) -> None:
    session = factory()
    session.add(
        CommandAuthorizationAuditModel(
            id=authorization_id,
            run_id=run_id,
            stage_id=stage_id,
            command_id="npm-ci-bootstrap",
            executable="npm",
            arguments=["ci"],
            decision="accepted",
            reasons=[],
            policy_version="policy-v1",
            idempotency_key=f"auth-{authorization_id}",
            request_payload_hash="sha256:request",
            expected_state_version=1,
            execution_profile_id="profile-1",
            workspace_alias="run_workspace",
            network_profile="none",
            correlation_id=f"corr-{authorization_id}",
            actor="operator",
            artifact_ids=[],
            state_version=1,
            created_at=now,
        )
    )
    session.commit()
    session.close()


def _seed_continuation(
    factory,
    *,
    continuation_id: str = "cont-stage-1",
    run_id: str = "run-1",
    stage_id: str = "stage-1",
    status: str = "waiting_command",
    worker_id: str | None = None,
    next_attempt_at: datetime | None = None,
    attempt: int = 0,
    wake_sequence: int = 0,
    state_version: int = 1,
    now: datetime = NOW,
) -> None:
    session = factory()
    session.add(
        TransformationContinuationModel(
            id=continuation_id,
            run_id=run_id,
            current_stage_id=stage_id,
            thread_id=f"thread:{run_id}:{stage_id}",
            status=status,
            current_node="verify_bootstrap",
            g06_approval_id="g06-1",
            plan_id="plan-1",
            plan_checksum="sha256:plan",
            stage_plan_id="stage-plan-1",
            stage_plan_checksum="sha256:stage-plan",
            idempotency_key=f"continuation:{stage_id}",
            request_checksum="sha256:continuation",
            attempt=attempt,
            max_attempts=3,
            worker_id=worker_id,
            next_attempt_at=next_attempt_at,
            wake_sequence=wake_sequence,
            state_version=state_version,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    session.close()


def test_reconciled_interrupted_command_wakes_parked_waiter(tmp_path: Path):
    """D1.1: reconcile of an expired mutating claim (interrupted) releases the waiter."""
    engine, factory = _database(tmp_path)
    _seed_run(factory)
    _seed_execution(
        factory,
        status="running",
        worker_id="dead-worker",
        claim_expires_at=NOW - timedelta(seconds=1),
        operation_kind="mutating",
    )
    _seed_continuation(factory)
    workflow = MagicMock()
    worker = _worker(factory, workflow=workflow)

    assert worker.run_once() is True

    session = factory()
    execution = session.get(CommandExecutionModel, "exec-1")
    assert execution.status == "interrupted"
    assert execution.reconstruction_required is True
    continuation = session.get(TransformationContinuationModel, "cont-stage-1")
    assert continuation.status == "running"
    assert continuation.wake_sequence == 1
    assert continuation.state_version == 3
    assert continuation.worker_id is not None
    session.close()
    workflow.invoke.assert_called_once()
    engine.dispose()


def test_terminal_command_without_wake_is_swept_on_next_worker_pass(tmp_path: Path):
    """A terminal command whose wake was lost (crash gap) is released by the sweep."""
    engine, factory = _database(tmp_path)
    _seed_run(factory)
    _seed_execution(factory, status="failed")
    _seed_continuation(factory)
    worker = _worker(factory)

    assert worker.run_once() is True

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-stage-1")
    assert continuation.status == "running"
    assert continuation.wake_sequence == 1
    assert continuation.state_version == 3
    session.close()
    engine.dispose()


def test_waiting_waiter_is_not_woken_by_active_command(tmp_path: Path):
    """A still-active command must not release the waiter (sweep only fires on terminal)."""
    engine, factory = _database(tmp_path)
    _seed_run(factory)
    _seed_execution(factory, status="queued", worker_id="worker-1")
    _seed_continuation(factory)
    worker = _worker(factory)

    assert worker.run_once() is False

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-stage-1")
    assert continuation.status == "waiting_command"
    assert continuation.wake_sequence == 0
    execution = session.get(CommandExecutionModel, "exec-1")
    assert execution.status == "queued"
    session.close()
    engine.dispose()


def test_waiting_retry_is_claimable_when_next_attempt_is_due(tmp_path: Path):
    """D1.2: waiting_retry with next_attempt_at in the past resumes through claim_next."""
    engine, factory = _database(tmp_path)
    _seed_run(factory)
    _seed_continuation(
        factory,
        status="waiting_retry",
        next_attempt_at=NOW - timedelta(seconds=1),
        attempt=2,
        state_version=3,
    )
    session = factory()

    claimed = TransformationContinuationService().claim_next(session, "worker-1", now=NOW)

    assert claimed is not None
    assert claimed.id == "cont-stage-1"
    assert claimed.status == "running"
    assert claimed.attempt == 2
    assert claimed.claim_count == 1
    session.close()
    engine.dispose()


def test_waiting_retry_is_not_claimable_before_next_attempt(tmp_path: Path):
    """D1.2: waiting_retry stays parked until next_attempt_at elapses."""
    engine, factory = _database(tmp_path)
    _seed_run(factory)
    _seed_continuation(
        factory,
        status="waiting_retry",
        next_attempt_at=NOW + timedelta(seconds=60),
        attempt=2,
        state_version=3,
    )
    session = factory()

    assert TransformationContinuationService().claim_next(session, "worker-1", now=NOW) is None
    session.close()
    engine.dispose()


def test_queued_cancel_wakes_parked_waiter(tmp_path: Path):
    """D1.4: cancelling a QUEUED command releases the continuation parked on it."""
    engine, factory = _database(tmp_path)
    _seed_run(factory)
    _seed_execution(factory, status="queued", operation_kind="mutating")
    _seed_continuation(factory)
    session = factory()

    JobSupervisorService().cancel_command(
        session,
        "run-1",
        "exec-1",
        "operator",
        idempotency_key="cancel-queued",
    )
    session.commit()
    session.close()

    session = factory()
    execution = session.get(CommandExecutionModel, "exec-1")
    assert execution.status == "cancelled"
    continuation = session.get(TransformationContinuationModel, "cont-stage-1")
    assert continuation.status == "queued"
    assert continuation.wake_sequence == 1
    assert continuation.state_version == 2
    session.close()
    engine.dispose()


def test_cancel_wake_is_not_double_fired_by_worker_sweep(tmp_path: Path):
    """The cancel wake and the reconciliation sweep must not double-wake the waiter."""
    engine, factory = _database(tmp_path)
    _seed_run(factory)
    _seed_execution(factory, status="queued", operation_kind="mutating")
    _seed_continuation(factory)
    session = factory()
    JobSupervisorService().cancel_command(
        session,
        "run-1",
        "exec-1",
        "operator",
        idempotency_key="cancel-queued",
    )
    session.commit()
    session.close()

    worker = _worker(factory)
    assert worker.run_once() is True

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-stage-1")
    assert continuation.wake_sequence == 1
    session.close()
    engine.dispose()


def test_wake_is_idempotent_and_increments_sequence_once(tmp_path: Path):
    """Repeated wake attempts for the same terminal command are a no-op."""
    engine, factory = _database(tmp_path)
    _seed_run(factory)
    _seed_execution(factory, status="succeeded")
    _seed_continuation(factory)
    worker = _worker(factory)

    worker._wake_command_waiter("exec-1")
    worker._wake_command_waiter("exec-1")

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-stage-1")
    assert continuation.status == "queued"
    assert continuation.wake_sequence == 1
    assert continuation.state_version == 2
    session.close()
    engine.dispose()


def test_run_once_wakes_waiter_for_executed_terminal_command(tmp_path: Path):
    """Existing behavior: the executed command's terminal wake still fires in run_once."""
    engine, factory = _database(tmp_path)
    _seed_run(factory)
    _seed_execution(factory, status="queued")
    _seed_continuation(factory)
    worker = _worker(factory)

    def fake_execute(execution_id: str, _worker_id: str) -> None:
        with factory() as session:
            model = session.get(CommandExecutionModel, execution_id)
            model.status = "succeeded"
            session.commit()

    worker.command_executor.execute_claimed_execution = fake_execute

    assert worker.run_once() is True

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-stage-1")
    assert continuation.status == "queued"
    assert continuation.wake_sequence == 1
    session.close()
    engine.dispose()


def test_queue_retry_accepts_interrupted_reconstruction_required_parent(tmp_path: Path):
    """D1.5: an interrupted mutating command (reconstruction_required) is retryable."""
    engine, factory = _database(tmp_path)
    _seed_run(factory)
    _seed_authorization(factory)
    _seed_execution(
        factory,
        status="interrupted",
        operation_kind="mutating",
        reconstruction_required=True,
        authorization_id="auth-1",
    )
    session = factory()

    retry = CommandExecutorService().queue_retry_execution(
        session,
        "exec-1",
        idempotency_key="exec-1:retry:1",
    )
    session.commit()

    successor = session.get(CommandExecutionModel, retry.execution_id)
    assert retry.status == "queued"
    assert successor.parent_execution_id == "exec-1"
    assert successor.attempt_number == 2
    assert successor.operation_kind == "mutating"
    session.close()
    engine.dispose()


def test_queue_retry_rejects_cancelled_timed_out_and_plain_interrupted(tmp_path: Path):
    """D1.5: only failed or interrupted+reconstruction_required parents are retryable."""
    cases = [
        ("run-cancelled", "exec-cancelled", "cancelled", {}),
        ("run-timed-out", "exec-timed-out", "timed_out", {}),
        ("run-interrupted-plain", "exec-interrupted-plain", "interrupted", {}),
    ]
    for run_id, execution_id, status, _kwargs in cases:
        root = tmp_path / run_id
        root.mkdir()
        engine, factory = _database(root)
        _seed_run(factory, run_id=run_id)
        _seed_authorization(factory, authorization_id=f"auth-{run_id}", run_id=run_id)
        _seed_execution(
            factory,
            execution_id=execution_id,
            run_id=run_id,
            status=status,
            operation_kind="mutating",
            authorization_id=f"auth-{run_id}",
        )
        session = factory()

        with pytest.raises(CommandExecutorError) as raised:
            CommandExecutorService().queue_retry_execution(
                session,
                execution_id,
                idempotency_key=f"{execution_id}:retry:1",
            )
        assert raised.value.code == "EXECUTION_NOT_RETRYABLE"
        session.close()
        engine.dispose()


def test_interrupted_with_process_evidence_requires_workspace_recovery(tmp_path: Path):
    """Interrupted parents keep the mirror of the workspace_recovered requirement."""
    engine, factory = _database(tmp_path)
    _seed_run(factory)
    _seed_authorization(factory)
    _seed_execution(
        factory,
        status="interrupted",
        operation_kind="mutating",
        reconstruction_required=True,
        authorization_id="auth-1",
    )
    session = factory()
    execution = session.get(CommandExecutionModel, "exec-1")
    execution.process_id = 4242
    session.commit()

    with pytest.raises(CommandExecutorError) as raised:
        CommandExecutorService().queue_retry_execution(
            session,
            "exec-1",
            idempotency_key="exec-1:retry:1",
        )
    assert raised.value.code == "EXECUTION_RETRY_REQUIRES_RECOVERY"
    session.close()
    engine.dispose()
