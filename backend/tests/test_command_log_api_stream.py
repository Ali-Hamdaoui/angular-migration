"""Run-scoped command-log API and SSE protocol tests for AMFA-163."""

from contextlib import contextmanager
from datetime import UTC, datetime
import pytest
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.api.routes import run_commands
from app.repositories.models.base import Base
from app.repositories.models.workflow import CommandExecutionModel, MigrationRunModel
from app.services.command_log_service import CommandLogService


def _request(path: str = "/api/v1/runs/run-1/commands/exec-1/logs") -> Request:
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    return Request({"type": "http", "method": "GET", "path": path, "headers": []}, receive)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    session.add_all([
        MigrationRunModel(id="run-1", status="RUNNING", run_phase="COMMAND", phase_status="running", actor="alice", created_at=now, updated_at=now),
        MigrationRunModel(id="run-2", status="RUNNING", run_phase="COMMAND", phase_status="running", actor="alice", created_at=now, updated_at=now),
        CommandExecutionModel(id="exec-1", run_id="run-1", command_id="python-version", executable="python", arguments=["--version"], status="succeeded", requested_at=now, finished_at=now),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _scope(session):
    @contextmanager
    def scoped_session():
        yield session
    return scoped_session


def test_log_retrieval_is_run_scoped(db_session, monkeypatch):
    service = CommandLogService()
    service.append_chunk(db_session, "exec-1", "run-1", "stdout", "safe output")
    db_session.commit()
    monkeypatch.setattr(run_commands, "session_scope", _scope(db_session))

    response = run_commands.get_command_logs("run-2", "exec-1", _request(), actor="alice")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 404


def test_log_retrieval_rejects_unknown_stream_filter(db_session, monkeypatch):
    monkeypatch.setattr(run_commands, "session_scope", _scope(db_session))

    response = run_commands.get_command_logs("run-1", "exec-1", _request(), actor="alice", stream="debug")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 422
    assert response.body and b"INVALID_LOG_STREAM" in response.body


def test_log_retrieval_exposes_chunk_truncation_metadata(db_session, monkeypatch):
    service = CommandLogService()
    service.append_chunk(db_session, "exec-1", "run-1", "stdout", "0123456789", max_chunk_bytes=4)
    db_session.commit()
    monkeypatch.setattr(run_commands, "session_scope", _scope(db_session))

    response = run_commands.get_command_logs("run-1", "exec-1", _request(), actor="alice")

    assert response["chunks"][0].truncated is True


def test_sse_rejects_unknown_stream_filter(db_session, monkeypatch):
    monkeypatch.setattr(run_commands, "session_scope", _scope(db_session))

    response = run_commands.stream_command_logs("run-1", "exec-1", _request("/logs/stream"), actor="alice", stream="debug", last_event_id=None)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 422
    assert response.body and b"INVALID_LOG_STREAM" in response.body


def test_sse_rejects_malformed_last_event_id(db_session, monkeypatch):
    monkeypatch.setattr(run_commands, "session_scope", _scope(db_session))

    response = run_commands.stream_command_logs("run-1", "exec-1", _request("/logs/stream"), actor="alice", last_event_id="not-a-sequence")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 422
    assert response.body and b"INVALID_LAST_EVENT_ID" in response.body


@pytest.mark.asyncio
async def test_sse_failure_preserves_correlation_id(db_session, monkeypatch):
    db_session.query(CommandExecutionModel).filter_by(id="exec-1").update({"correlation_id": "corr-sse-failure"})
    db_session.commit()
    monkeypatch.setattr(run_commands, "session_scope", _scope(db_session))
    monkeypatch.setattr(CommandLogService, "get_logs", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("storage unavailable")))

    response = run_commands.stream_command_logs("run-1", "exec-1", _request("/logs/stream"), actor="alice", cursor=0)
    body = "".join([item async for item in response.body_iterator])

    assert '"code": "LOG_STREAM_FAILED"' in body
    assert '"correlation_id": "corr-sse-failure"' in body


def test_log_redacts_secrets_before_persistence(db_session):
    service = CommandLogService()
    service.append_chunk(db_session, "exec-1", "run-1", "stderr", "Authorization: Bearer super-secret-token-value")

    chunks, _ = service.get_logs(db_session, "exec-1")

    assert "super-secret-token-value" not in chunks[0].text
    assert "[REDACTED]" in chunks[0].text


@pytest.mark.asyncio
async def test_sse_uses_sequence_ids_and_sends_completion(db_session, monkeypatch):
    service = CommandLogService()
    service.append_chunk(db_session, "exec-1", "run-1", "stdout", "safe output")
    service.ensure_summary(db_session, "exec-1", "run-1")
    service.finalize(db_session, "exec-1")
    db_session.commit()
    monkeypatch.setattr(run_commands, "session_scope", _scope(db_session))

    response = run_commands.stream_command_logs("run-1", "exec-1", _request("/logs/stream"), actor="alice", cursor=0)
    body = "".join([item async for item in response.body_iterator])

    assert "id: 1\n" in body
    assert "event: command_log" in body
    assert '"content": "safe output"' in body
    assert "event: execution_complete" in body
    assert "event: cursor" not in body


@pytest.mark.asyncio
async def test_explicit_cursor_is_preferred_over_last_event_id(db_session, monkeypatch):
    service = CommandLogService()
    for sequence in range(3):
        service.append_chunk(db_session, "exec-1", "run-1", "stdout", f"line-{sequence}")
    db_session.commit()
    monkeypatch.setattr(run_commands, "session_scope", _scope(db_session))

    response = run_commands.stream_command_logs(
        "run-1", "exec-1", _request("/logs/stream"), actor="alice", cursor=2, last_event_id="0"
    )
    body = "".join([item async for item in response.body_iterator])

    assert response.media_type == "text/event-stream"
    assert "id: 3\n" in body
    assert "id: 1\n" not in body
    assert "id: 2\n" not in body
