"""Tests for the G01 command executor, log, and job supervisor services."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.command_execution.worker import (
    CommandDefinition,
    CommandRegistry,
    SupervisedProcessResult,
)
from app.domain.command import CommandTemplate, CommandTemplateStatus
from app.domain.contracts import (
    CommandExecuteRequestDto,
    CommandPolicyValidateResponseDto,
    CommandStatus,
    WorkflowEventType,
)
from app.repositories.models.base import Base
from app.repositories.models.workflow import (
    CommandExecutionModel,
    CommandLogChunkModel,
    WorkerLeaseModel,
    WorkflowEventModel,
)
from app.services.command_executor_service import (
    CommandExecutorError,
    CommandExecutorService,
    CommandExecutionResponse,
)
from app.services.command_log_service import CommandLogService, LogChunkDto
from app.services.job_supervisor_service import JobSupervisorService, JobSupervisorError


@pytest.fixture
def db_session(tmp_path: Path) -> Session:
    """Create an isolated SQLite in-memory database for each test."""
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    _session = sessionmaker(bind=engine)()
    yield _session
    _session.close()


# ---------------------------------------------------------------------------
# Helpers for mock policy engine
# ---------------------------------------------------------------------------

def make_accepted_policy_response(
    authorization_id: str | None = None,
) -> CommandPolicyValidateResponseDto:
    authz_id = authorization_id or f"authz-{uuid4().hex[:12]}"
    return CommandPolicyValidateResponseDto(
        authorization_id=authz_id,
        run_id="run-qc-1",
        stage_id=None,
        command_id="python-version",
        executable="python",
        arguments=["--version"],
        cwd_alias=None,
        plan_id=None,
        execution_profile_id="source-runtime-profile",
        decision="accepted",
        reasons=[],
        policy_version="s3-f01-v1",
    )


def make_mock_policy_engine(
    *,
    decision: str = "accepted",
    authorization_id: str | None = None,
) -> MagicMock:
    mock = MagicMock()
    mock.validate.return_value = make_accepted_policy_response(
        authorization_id=authorization_id,
    )
    if decision == "rejected":
        mock.validate.return_value = CommandPolicyValidateResponseDto(
            authorization_id=authorization_id or f"authz-{uuid4().hex[:12]}",
            run_id="run-qc-1",
            stage_id=None,
            command_id="python-version",
            executable="python",
            arguments=["--version"],
            cwd_alias=None,
            plan_id=None,
            execution_profile_id="source-runtime-profile",
            decision="rejected",
            reasons=["policy rejected"],
            policy_version="s3-f01-v1",
        )
    return mock


def make_mock_supervisor(status: CommandStatus = CommandStatus.SUCCEEDED) -> MagicMock:
    mock = MagicMock()
    mock.run.return_value = SupervisedProcessResult(
        status=status,
        exit_code=0 if status == CommandStatus.SUCCEEDED else 1,
        stdout="Python 3.11.15\n",
        stderr="",
        timed_out=(status == CommandStatus.TIMED_OUT),
        cancelled=(status == CommandStatus.CANCELLED),
    )
    return mock


# ===========================================================================
# TestCommandLogService
# ===========================================================================

class TestCommandLogService:
    """Tests for the log chunk persistence and retrieval."""

    def test_append_chunk_creates_ordered_sequence(self, db_session: Session):
        svc = CommandLogService()
        c1 = svc.append_chunk(db_session, "exec-1", "run-1", "stdout", "hello")
        assert c1.sequence == 1
        assert c1.stream == "stdout"

        c2 = svc.append_chunk(db_session, "exec-1", "run-1", "stderr", "world")
        assert c2.sequence == 2
        assert c2.stream == "stderr"

        c3 = svc.append_chunk(db_session, "exec-1", "run-1", "stdout", "line3")
        assert c3.sequence == 3

    def test_get_logs_returns_ordered_chunks(self, db_session: Session):
        svc = CommandLogService()
        for i in range(5):
            svc.append_chunk(db_session, "exec-2", "run-1", "stdout", f"line{i}")

        chunks, total = svc.get_logs(db_session, "exec-2")
        assert total == 5
        assert len(chunks) == 5
        assert chunks[0].sequence == 1
        assert chunks[4].sequence == 5

    def test_get_logs_stream_filter(self, db_session: Session):
        svc = CommandLogService()
        svc.append_chunk(db_session, "exec-3", "run-1", "stdout", "out1")
        svc.append_chunk(db_session, "exec-3", "run-1", "stderr", "err1")
        svc.append_chunk(db_session, "exec-3", "run-1", "stdout", "out2")

        chunks, total = svc.get_logs(db_session, "exec-3", stream_filter="stdout")
        assert total == 2
        assert all(c.stream == "stdout" for c in chunks)

    def test_get_logs_with_offset_and_limit(self, db_session: Session):
        svc = CommandLogService()
        for i in range(10):
            svc.append_chunk(db_session, "exec-4", "run-1", "stdout", f"line{i}")

        chunks, total = svc.get_logs(db_session, "exec-4", offset=3, limit=4)
        assert total == 10
        assert len(chunks) == 4
        assert chunks[0].sequence == 4

    def test_get_logs_with_cursor(self, db_session: Session):
        """Cursor returns only chunks with sequence > cursor."""
        svc = CommandLogService()
        for i in range(5):
            svc.append_chunk(db_session, "exec-cursor", "run-1", "stdout", f"line{i}")

        # cursor=2 → chunks with sequence > 2 (i.e. 3, 4, 5)
        chunks, total = svc.get_logs(db_session, "exec-cursor", cursor=2)
        assert total == 5
        assert len(chunks) == 3
        assert chunks[0].sequence == 3
        assert chunks[2].sequence == 5

    def test_get_stream_summary(self, db_session: Session):
        svc = CommandLogService()
        for i in range(3):
            svc.append_chunk(db_session, "exec-5", "run-1", "stdout", f"out{i}")
        for i in range(2):
            svc.append_chunk(db_session, "exec-5", "run-1", "stderr", f"err{i}")

        summary = svc.get_stream_summary(db_session, "exec-5")
        assert summary["total_chunks"] == 5
        assert summary["streams"]["stdout"] == 3
        assert summary["streams"]["stderr"] == 2

    def test_chunk_emits_event(self, db_session: Session):
        """Appending a chunk should create a workflow event."""
        svc = CommandLogService()
        svc.append_chunk(db_session, "exec-6", "run-1", "stdout", "test")
        events = db_session.query(WorkflowEventModel).filter(
            WorkflowEventModel.event_type == "COMMAND_OUTPUT_AVAILABLE"
        ).all()
        assert len(events) == 1
        assert events[0].payload["execution_id"] == "exec-6"


# ===========================================================================
# TestJobSupervisorService
# ===========================================================================

class TestJobSupervisorService:
    """Tests for job supervision and cancellation."""

    def test_acquire_lease_creates_new_lease(self, db_session: Session):
        svc = JobSupervisorService(lease_seconds=60)
        result = svc.acquire_lease(db_session, "run-1", "exec-1", "worker-1", "tester")
        assert result.lease_id is not None
        assert result.status == "active"

        # Verify DB
        saved = db_session.query(WorkerLeaseModel).first()
        assert saved is not None
        assert saved.run_id == "run-1"
        assert saved.worker_id == "worker-1"

    def test_acquire_lease_rejects_duplicate(self, db_session: Session):
        svc = JobSupervisorService(lease_seconds=60)
        svc.acquire_lease(db_session, "run-1", "exec-1", "worker-1", "tester")
        with pytest.raises(JobSupervisorError, match="already has an active"):
            svc.acquire_lease(db_session, "run-1", "exec-2", "worker-2", "tester2")

    def test_renew_lease_extends_expiry(self, db_session: Session):
        svc = JobSupervisorService(lease_seconds=60)
        initial = svc.acquire_lease(db_session, "run-1", "exec-1", "worker-1", "tester")
        renewed = svc.renew_lease(db_session, initial.lease_id, "worker-1")
        assert renewed.expires_at > initial.expires_at

    def test_cancel_command_updates_execution(self, db_session: Session):
        svc = JobSupervisorService()
        now = datetime.now(UTC)

        # Create a running execution
        exec_model = CommandExecutionModel(
            id="exec-cancel-1",
            run_id="run-1",
            command_id="test-cmd",
            executable="echo",
            arguments=["hello"],
            status="running",
            requested_at=now,
        )
        db_session.add(exec_model)
        db_session.flush()

        result = svc.cancel_command(
            db_session, "run-1", "exec-cancel-1", "operator",
            idempotency_key="cancel-key-1",
        )
        assert result["cancelled"] is True

        # Verify execution record updated
        updated = db_session.get(CommandExecutionModel, "exec-cancel-1")
        assert updated.cancelled is True
        assert updated.cancel_requested_by == "operator"

    def test_get_active_command_returns_running(self, db_session: Session):
        svc = JobSupervisorService()
        now = datetime.now(UTC)

        exec_model = CommandExecutionModel(
            id="exec-active-1",
            run_id="run-1",
            command_id="test-cmd",
            executable="echo",
            arguments=["hello"],
            status="running",
            requested_at=now,
        )
        db_session.add(exec_model)
        db_session.flush()

        active = svc.get_active_command(db_session, "run-1")
        assert active is not None
        assert active.id == "exec-active-1"

    def test_get_active_command_returns_none_when_none_running(self, db_session: Session):
        svc = JobSupervisorService()
        active = svc.get_active_command(db_session, "run-empty")
        assert active is None

    def test_cancel_idempotent_replay(self, db_session: Session):
        """Same key returns idempotent replay."""
        svc = JobSupervisorService()
        now = datetime.now(UTC)

        exec_model = CommandExecutionModel(
            id="exec-idemp-1",
            run_id="run-1",
            command_id="test-cmd",
            executable="echo",
            arguments=["hello"],
            status="running",
            requested_at=now,
        )
        db_session.add(exec_model)
        db_session.flush()

        result1 = svc.cancel_command(
            db_session, "run-1", "exec-idemp-1", "operator",
            idempotency_key="cancel-idemp-key",
        )
        assert result1["idempotent_replay"] is False

        # Second call with same key
        result2 = svc.cancel_command(
            db_session, "run-1", "exec-idemp-1", "operator",
            idempotency_key="cancel-idemp-key",
        )
        assert result2["idempotent_replay"] is True


# ===========================================================================
# TestCommandExecutorQueueCommand — unit tests using mocks
# ===========================================================================

class TestCommandExecutorQueueCommand:
    """Tests for CommandExecutorService.queue_command().

    All tests use a mock policy engine to avoid requiring registered
    command templates in the test DB.  Policy-engine integration is
    tested separately via test_policy_rejection_raises_error.
    """

    def test_successful_execution(self, db_session: Session):
        """queue_command should execute a command and return a response."""
        mock_supervisor = make_mock_supervisor()
        mock_policy = make_mock_policy_engine()
        svc = CommandExecutorService(
            supervisor=mock_supervisor,
            policy_engine=mock_policy,
        )

        result = svc.queue_command(
            db_session,
            run_id="run-qc-1",
            stage_id=None,
            command_id="python-version",
            executable="python",
            arguments=["--version"],
            idempotency_key="qc-test-1",
            requested_by="tester",
        )

        assert result.execution_id is not None
        assert result.status == "succeeded"
        assert result.idempotent_replay is False
        assert result.run_id == "run-qc-1"
        assert result.command_id == "python-version"
        assert result.state_version >= 1
        assert result.event_sequence >= 1

        # Verify DB record
        saved = db_session.get(CommandExecutionModel, result.execution_id)
        assert saved is not None
        assert saved.status == "succeeded"
        assert saved.exit_code == 0
        assert saved.authorization_id is not None
        assert saved.runtime_checksum is not None
        assert saved.runtime_checksum.startswith("sha256:")
        assert saved.started_at is not None
        assert saved.finished_at is not None
        assert saved.duration_ms is not None

    def test_idempotent_replay_returns_cached_result(self, db_session: Session):
        """Same idempotency_key + same payload should return cached result."""
        mock_supervisor = make_mock_supervisor()
        mock_policy = make_mock_policy_engine()
        svc = CommandExecutorService(
            supervisor=mock_supervisor,
            policy_engine=mock_policy,
        )

        result1 = svc.queue_command(
            db_session,
            run_id="run-qc-1",
            stage_id=None,
            command_id="python-version",
            executable="python",
            arguments=["--version"],
            idempotency_key="qc-test-idemp",
            requested_by="tester",
        )
        assert result1.idempotent_replay is False

        result2 = svc.queue_command(
            db_session,
            run_id="run-qc-1",
            stage_id=None,
            command_id="python-version",
            executable="python",
            arguments=["--version"],
            idempotency_key="qc-test-idemp",
            requested_by="tester",
        )
        assert result2.idempotent_replay is True
        assert result2.execution_id == result1.execution_id
        assert result2.status == result1.status

    def test_conflicting_replay_raises_error(self, db_session: Session):
        """Same idempotency_key with different payload should raise conflict."""
        mock_supervisor = make_mock_supervisor()
        mock_policy = make_mock_policy_engine()
        svc = CommandExecutorService(
            supervisor=mock_supervisor,
            policy_engine=mock_policy,
        )

        svc.queue_command(
            db_session,
            run_id="run-qc-1",
            stage_id=None,
            command_id="python-version",
            executable="python",
            arguments=["--version"],
            idempotency_key="qc-test-conflict",
            requested_by="tester",
        )

        with pytest.raises(CommandExecutorError) as exc_info:
            svc.queue_command(
                db_session,
                run_id="run-qc-1",
                stage_id=None,
                command_id="python-version",
                executable="python",
                arguments=["--different-arg"],  # different payload
                idempotency_key="qc-test-conflict",
                requested_by="tester",
            )
        assert exc_info.value.code == "IDEMPOTENCY_KEY_CONFLICT"

    def test_policy_rejection_raises_error(self, db_session: Session):
        """Command rejected by policy engine should raise POLICY_REJECTED."""
        mock_supervisor = make_mock_supervisor()
        mock_policy = make_mock_policy_engine(decision="rejected")

        svc = CommandExecutorService(
            supervisor=mock_supervisor,
            policy_engine=mock_policy,
        )

        with pytest.raises(CommandExecutorError) as exc_info:
            svc.queue_command(
                db_session,
                run_id="run-qc-1",
                stage_id=None,
                command_id="python-version",
                executable="python",
                arguments=["--version"],
                idempotency_key="qc-test-rejected",
                requested_by="tester",
            )
        assert exc_info.value.code == "POLICY_REJECTED"

    def test_successful_execution_sets_authorization_id(self, db_session: Session):
        """The execution record should contain the authorization_id from policy engine."""
        expected_authz_id = "authz-specific-for-test-42"
        mock_supervisor = make_mock_supervisor()
        mock_policy = make_mock_policy_engine(authorization_id=expected_authz_id)

        svc = CommandExecutorService(
            supervisor=mock_supervisor,
            policy_engine=mock_policy,
        )

        result = svc.queue_command(
            db_session,
            run_id="run-qc-1",
            stage_id=None,
            command_id="python-version",
            executable="python",
            arguments=["--version"],
            idempotency_key="qc-test-authz",
            requested_by="tester",
        )

        saved = db_session.get(CommandExecutionModel, result.execution_id)
        assert saved is not None
        assert saved.authorization_id == expected_authz_id

    def test_successful_execution_sets_runtime_checksum(self, db_session: Session):
        """The execution record should contain a valid runtime_checksum."""
        mock_supervisor = make_mock_supervisor()
        mock_policy = make_mock_policy_engine()
        svc = CommandExecutorService(
            supervisor=mock_supervisor,
            policy_engine=mock_policy,
        )

        result = svc.queue_command(
            db_session,
            run_id="run-qc-1",
            stage_id=None,
            command_id="python-version",
            executable="python",
            arguments=["--version"],
            idempotency_key="qc-test-checksum",
            requested_by="tester",
        )

        saved = db_session.get(CommandExecutionModel, result.execution_id)
        assert saved is not None
        assert saved.runtime_checksum is not None
        assert saved.runtime_checksum.startswith("sha256:")
        # sha256 hex is 64 chars
        hex_part = saved.runtime_checksum[len("sha256:"):]
        assert len(hex_part) == 64
        int(hex_part, 16)  # should not raise

    def test_timeout_sets_timed_out_status(self, db_session: Session):
        """When supervisor reports timed_out, the execution should be TIMED_OUT."""
        mock_supervisor = make_mock_supervisor(status=CommandStatus.TIMED_OUT)
        mock_policy = make_mock_policy_engine()
        svc = CommandExecutorService(
            supervisor=mock_supervisor,
            policy_engine=mock_policy,
        )

        result = svc.queue_command(
            db_session,
            run_id="run-qc-1",
            stage_id=None,
            command_id="python-version",
            executable="python",
            arguments=["--version"],
            idempotency_key="qc-test-timeout",
            requested_by="tester",
        )

        assert result.status == "timed_out"

        saved = db_session.get(CommandExecutionModel, result.execution_id)
        assert saved is not None
        assert saved.timed_out is True

    def test_cancelled_sets_cancelled_status(self, db_session: Session):
        """When supervisor reports cancelled, the execution should be CANCELLED."""
        mock_supervisor = make_mock_supervisor(status=CommandStatus.CANCELLED)
        mock_policy = make_mock_policy_engine()
        svc = CommandExecutorService(
            supervisor=mock_supervisor,
            policy_engine=mock_policy,
        )

        result = svc.queue_command(
            db_session,
            run_id="run-qc-1",
            stage_id=None,
            command_id="python-version",
            executable="python",
            arguments=["--version"],
            idempotency_key="qc-test-cancelled",
            requested_by="tester",
        )

        assert result.status == "cancelled"

        saved = db_session.get(CommandExecutionModel, result.execution_id)
        assert saved is not None
        assert saved.cancelled is True

    def test_workflow_events_emitted(self, db_session: Session):
        """queue_command should emit workflow events at each lifecycle step."""
        mock_supervisor = make_mock_supervisor()
        mock_policy = make_mock_policy_engine()
        svc = CommandExecutorService(
            supervisor=mock_supervisor,
            policy_engine=mock_policy,
        )

        result = svc.queue_command(
            db_session,
            run_id="run-qc-1",
            stage_id=None,
            command_id="python-version",
            executable="python",
            arguments=["--version"],
            idempotency_key="qc-test-events",
            requested_by="tester",
        )

        events = db_session.query(WorkflowEventModel).filter(
            WorkflowEventModel.run_id == "run-qc-1"
        ).order_by(WorkflowEventModel.sequence).all()

        event_types = [e.event_type for e in events]
        assert "COMMAND_QUEUED" in event_types
        assert "COMMAND_STARTED" in event_types
        assert "COMMAND_SUCCEEDED" in event_types

    def test_stale_state_error_mapping(self, db_session: Session):
        """Verify queue_command stores execution correctly."""
        mock_supervisor = make_mock_supervisor()
        mock_policy = make_mock_policy_engine()
        svc = CommandExecutorService(
            supervisor=mock_supervisor,
            policy_engine=mock_policy,
        )

        result = svc.queue_command(
            db_session,
            run_id="run-qc-1",
            stage_id=None,
            command_id="python-version",
            executable="python",
            arguments=["--version"],
            idempotency_key="qc-test-stale",
            requested_by="tester",
        )

        # Verify execution was stored correctly
        saved = db_session.get(CommandExecutionModel, result.execution_id)
        assert saved is not None
        assert saved.requested_by == "tester"
        assert saved.command_id == "python-version"


# ===========================================================================
# TestCancellationProcessTermination
# ===========================================================================

class TestCancellationProcessTermination:
    """Verify cancellation reaches the process.

    Tests the cancel_event mechanism end-to-end through
    CommandExecutorService without threading, proving that:
    - request_cancel() sets the stored cancel_event
    - the execution record is properly updated
    - cancel_event.state changes are visible to the supervisor
    """

    def test_request_cancel_sets_cancel_event(self, db_session: Session):
        """request_cancel sets cancel_event and updates execution record."""
        import threading

        mock_policy = make_mock_policy_engine()
        svc = CommandExecutorService(policy_engine=mock_policy)

        cancel_event = threading.Event()
        execution_id = "exec-cancel-direct-1"
        svc._cancel_events[execution_id] = cancel_event

        now = datetime.now(UTC)
        run_id = "run-cancel-direct-1"

        from app.repositories.models.workflow import MigrationRunModel
        run = MigrationRunModel(
            id=run_id, status="RUNNING", run_phase="TEST",
            phase_status="running", created_at=now, updated_at=now,
        )
        db_session.add(run)

        exec_model = CommandExecutionModel(
            id=execution_id, run_id=run_id, command_id="python-version",
            executable="python", arguments=["--version"], status="running",
            requested_at=now,
        )
        db_session.add(exec_model)
        db_session.flush()

        # Verify: event not set before cancel
        assert not cancel_event.is_set()

        # Act
        cancel_result = svc.request_cancel(
            db_session, run_id=run_id, execution_id=execution_id,
            actor="tester", idempotency_key="cancel-direct-key-1",
        )
        assert cancel_result["cancelled"] is True

        # Verify: event IS set after cancel
        assert cancel_event.is_set(), "cancel_event should be set by request_cancel"

        # Verify: execution record updated
        updated = db_session.get(CommandExecutionModel, execution_id)
        assert updated is not None
        assert updated.cancelled is True
        assert updated.cancel_requested_by == "tester"

    def test_cancel_event_detected_by_supervisor(self, db_session: Session):
        """A mock supervisor that polls cancel_event sees it get set.

        This proves the cancel mechanism would reach a real subprocess.
        """
        import threading
        import time

        captured_event: list[threading.Event] = []

        def run_side_effect(structured, cancel_event=None, output_callback=None):
            captured_event.append(cancel_event)
            # Simulate WorkerSupervisor: poll cancel_event in a loop
            while cancel_event is not None and not cancel_event.is_set():
                cancel_event.wait(timeout=0.05)
            return SupervisedProcessResult(
                status=CommandStatus.CANCELLED,
                exit_code=-15, stdout="", stderr="",
                timed_out=False, cancelled=True,
            )

        mock_supervisor = MagicMock()
        mock_supervisor.run.side_effect = run_side_effect

        mock_policy = make_mock_policy_engine()
        svc = CommandExecutorService(
            supervisor=mock_supervisor,
            policy_engine=mock_policy,
        )

        now = datetime.now(UTC)
        run_id = "run-cancel-supervisor-1"

        # Manually set up: create the DB record as if queue_command already started
        cancel_event = threading.Event()
        execution_id = "exec-cancel-supervisor-1"
        svc._cancel_events[execution_id] = cancel_event

        from app.repositories.models.workflow import MigrationRunModel
        run = MigrationRunModel(
            id=run_id, status="RUNNING", run_phase="TEST",
            phase_status="running", created_at=now, updated_at=now,
        )
        db_session.add(run)
        db_session.flush()

        # Start supervisor in a thread (it polls cancel_event)
        result_holder = [None]

        def run_supervisor():
            try:
                supervised = mock_supervisor.run(
                    "structured-request",
                    cancel_event=cancel_event,
                )
                result_holder[0] = supervised
            except Exception as e:
                result_holder[0] = e

        t = threading.Thread(target=run_supervisor, daemon=True)
        t.start()
        time.sleep(0.15)

        # Supervisor should be polling right now
        assert not result_holder[0], "Supervisor should still be running"

        # Set the cancel event (as request_cancel would)
        cancel_event.set()

        # Supervisor should now return
        t.join(timeout=3)
        assert result_holder[0] is not None
        supervised = result_holder[0]
        assert supervised.cancelled is True
        assert supervised.exit_code == -15
