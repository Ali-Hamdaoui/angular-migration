"""Tests for the G01 command executor, log, and job supervisor services."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.contracts import CommandExecuteRequestDto
from app.repositories.models.base import Base
from app.repositories.models.workflow import (
    CommandExecutionModel,
    CommandLogChunkModel,
    WorkerLeaseModel,
    WorkflowEventModel,
)
from app.services.command_executor_service import CommandExecutorService
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
            status="RUNNING",
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
            status="RUNNING",
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
            status="RUNNING",
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
