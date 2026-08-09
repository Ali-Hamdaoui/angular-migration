"""Authorization tests for the run-scoped S3-F02 command routes."""

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.authentication import authorize_run
from app.api.routes import run_commands
from app.domain.contracts import CommandExecuteRequestDto
from app.repositories.models import MigrationRunModel
from app.repositories.models.base import Base


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/runs/run-1/commands", "headers": []})


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    session.add(
        MigrationRunModel(
            id="run-owned",
            status="RUNNING",
            run_phase="COMMAND",
            phase_status="running",
            actor="alice",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def test_authorize_run_requires_the_persisted_run_owner(db_session: Session):
    assert authorize_run(db_session, "run-owned", "alice").id == "run-owned"

    with pytest.raises(HTTPException) as unauthorized:
        authorize_run(db_session, "run-owned", "bob")
    assert unauthorized.value.status_code == 403
    assert unauthorized.value.detail["error_code"] == "RUN_ACCESS_FORBIDDEN"

    with pytest.raises(HTTPException) as missing:
        authorize_run(db_session, "missing", "alice")
    assert missing.value.status_code == 404
    assert missing.value.detail["error_code"] == "RUN_NOT_FOUND"


def test_queue_route_uses_authenticated_actor_not_client_requested_by(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    calls: dict[str, str | None] = {}

    @contextmanager
    def scoped_session():
        yield db_session

    class Executor:
        def queue_authorized_command(self, session, **kwargs):
            calls["requested_by"] = kwargs["requested_by"]
            return SimpleNamespace(
                execution_id="exec-1", run_id="run-owned", command_id="python-version", status="queued",
                state_version=1, event_sequence=1, idempotent_replay=False, stage_id=None,
                authorization_id="auth-1", template_id=None, template_version=None, plan_id=None,
                plan_version=None, execution_profile_id=None, workspace_alias=None, created_at=None,
                started_at=None, completed_at=None, duration_ms=None, exit_code=None, failure_code=None,
                correlation_id=None, artifact_ids=(), stdout_artifact_id=None, stderr_artifact_id=None,
                command_log_artifact_id=None, manifest_artifact_id=None, result_artifact_id=None,
                executable="python", arguments=["--version"], safe_relative_working_directory=None,
                runtime_checksum=None, worker_id=None, failure_reason=None, request_payload_hash=None,
            )

        def dispatch_execution(self, execution_id):
            raise AssertionError("API process must not dispatch migration commands")

    monkeypatch.setattr(run_commands, "session_scope", scoped_session)
    result = run_commands.queue_command(
        "run-owned",
        CommandExecuteRequestDto(
            authorization_decision_id="auth-1",
            expected_state_version=1,
            idempotency_key="exec-1",
            requested_by="spoofed-client",
        ),
        _request(),
        actor="alice",
        executor=Executor(),
    )

    assert result.execution_id == "exec-1"
    assert calls == {"requested_by": "alice"}


def test_command_retrieval_route_rejects_cross_actor_access(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    @contextmanager
    def scoped_session():
        yield db_session

    class Executor:
        def get_list_command_executions(self, session, run_id):
            raise AssertionError("authorization must run before retrieval")

    monkeypatch.setattr(run_commands, "session_scope", scoped_session)
    with pytest.raises(HTTPException) as unauthorized:
        run_commands.list_command_executions("run-owned", actor="bob", executor=Executor())
    assert unauthorized.value.status_code == 403
