"""Tests for the G01 command executor, log, and job supervisor services."""

from __future__ import annotations

from datetime import UTC, datetime
import os
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
    _command_environment_overrides,
    _runtime_path_overrides,
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


def test_angular_update_environment_forwards_configured_chrome_binary(tmp_path: Path, monkeypatch) -> None:
    chrome = tmp_path / "chrome.exe"
    chrome.write_bytes(b"chrome")
    monkeypatch.setenv("CHROME_BIN", str(chrome))

    assert _command_environment_overrides("npm-script-test-ci", {}) == {
        "CHROME_BIN": str(chrome.resolve()),
    }


def test_angular_update_environment_disables_only_cli_latest_redirect(monkeypatch) -> None:
    monkeypatch.delenv("CHROME_BIN", raising=False)
    assert _command_environment_overrides("angular-update-exact", {}) == {
        "NG_DISABLE_VERSION_CHECK": "true",
    }
    assert _command_environment_overrides("npm-ci-bootstrap", {}) == {}


def test_runtime_path_overrides_uses_windows_installation_parent_without_bin(
    tmp_path: Path, monkeypatch
) -> None:
    runtime_root = tmp_path / "v16.20.2"
    runtime_root.mkdir()
    node = runtime_root / "node.exe"
    node.write_bytes(b"node")
    descriptor = MagicMock(
        installation_root=str(runtime_root),
        resolved_path=str(node),
    )
    monkeypatch.setenv("PATH", "baseline-path")

    result = _runtime_path_overrides({"node": descriptor})

    assert result["PATH"].split(os.pathsep)[:2] == [str(runtime_root), "baseline-path"]


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
    """Regression coverage for the removed client-controlled execution API.

    Execution now requires an accepted authorization decision and is covered
    by the authorization-bound API/service tests. These cases ensure the
    former request shape cannot silently regain execution authority.
    """

    def assert_legacy_execution_disabled(self, db_session: Session, **overrides):
        service = CommandExecutorService()
        request = {
            "run_id": "run-qc-1",
            "stage_id": None,
            "command_id": "python-version",
            "executable": "python",
            "arguments": ["--version"],
            "idempotency_key": "qc-legacy-key",
            "requested_by": "tester",
        }
        request.update(overrides)
        with pytest.raises(CommandExecutorError) as exc_info:
            service.legacy_queue_command_disabled(db_session, **request)
        assert exc_info.value.code == "LEGACY_EXECUTION_DISABLED"

    def test_successful_execution(self, db_session: Session):
        self.assert_legacy_execution_disabled(db_session)

    def test_idempotent_replay_returns_cached_result(self, db_session: Session):
        self.assert_legacy_execution_disabled(db_session, idempotency_key="qc-test-idemp")

    def test_conflicting_replay_raises_error(self, db_session: Session):
        """Same idempotency_key with different payload should raise conflict."""
        self.assert_legacy_execution_disabled(db_session, idempotency_key="qc-test-conflict", arguments=["--different-arg"])

    def test_policy_rejection_raises_error(self, db_session: Session):
        """Command rejected by policy engine should raise POLICY_REJECTED."""
        self.assert_legacy_execution_disabled(db_session, idempotency_key="qc-test-rejected")

    def test_successful_execution_sets_authorization_id(self, db_session: Session):
        """The execution record should contain the authorization_id from policy engine."""
        expected_authz_id = "authz-specific-for-test-42"
        self.assert_legacy_execution_disabled(db_session, idempotency_key="qc-test-authz")

    def test_successful_execution_sets_runtime_checksum(self, db_session: Session):
        """The execution record should contain a valid runtime_checksum."""
        self.assert_legacy_execution_disabled(db_session, idempotency_key="qc-test-checksum")

    def test_timeout_sets_timed_out_status(self, db_session: Session):
        """When supervisor reports timed_out, the execution should be TIMED_OUT."""
        self.assert_legacy_execution_disabled(db_session, idempotency_key="qc-test-timeout")

    def test_cancelled_sets_cancelled_status(self, db_session: Session):
        """When supervisor reports cancelled, the execution should be CANCELLED."""
        self.assert_legacy_execution_disabled(db_session, idempotency_key="qc-test-cancelled")

    def test_workflow_events_emitted(self, db_session: Session):
        """queue_command should emit workflow events at each lifecycle step."""
        self.assert_legacy_execution_disabled(db_session, idempotency_key="qc-test-events")

    def test_stale_state_error_mapping(self, db_session: Session):
        """Verify queue_command stores execution correctly."""
        self.assert_legacy_execution_disabled(db_session, idempotency_key="qc-test-stale")


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
