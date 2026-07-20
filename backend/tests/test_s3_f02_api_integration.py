"""Real API integration coverage for S3-F02 command execution."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import artifacts as artifact_routes
from app.api.routes import baseline as baseline_routes
from app.api.routes import run_commands
from app.command_execution.worker import CommandDefinition, CommandRegistry
from app.main import app
from app.repositories import session as repository_session
from app.repositories.execution_profiles import ExecutionProfileModel
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandAuthorizationAuditModel,
    CommandExecutionModel,
    CommandTemplateModel,
    MigrationRunModel,
    WorkflowEventModel,
)
from app.services import command_executor_service
from app.repositories.models.base import Base


@pytest.fixture
def isolated_command_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'command-api.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def isolated_scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(repository_session, "SessionLocal", factory)
    monkeypatch.setattr(run_commands, "session_scope", isolated_scope)
    monkeypatch.setattr(baseline_routes, "session_scope", isolated_scope)
    monkeypatch.setattr(artifact_routes, "session_scope", isolated_scope)

    with TestClient(app) as client:
        yield client, factory, tmp_path

    engine.dispose()


def _create_run(
    session: Session,
    root: Path,
    *,
    run_id: str,
    command_id: str = "python-version",
    template_id: str = "tpl-python-version",
    arguments: list[str] | None = None,
    executable: str = "python",
    profile_id: str = "source-runtime-profile",
    execution_idempotency_key: str | None = None,
) -> None:
    run_root = root / run_id
    workspace = run_root / "workspace"
    workspace.mkdir(parents=True)
    artifact_root = run_root / "artifacts"
    now = datetime.now(UTC)
    session.add(
        MigrationRunModel(
            id=run_id,
            status="RUNNING",
            run_phase="COMMAND",
            phase_status="running",
            state_version=1,
            actor="alice",
            run_root=str(run_root),
            artifact_root=str(artifact_root),
            workspace_aliases={"BASELINE_SANDBOX": "workspace"},
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        CommandTemplateModel(
            id=template_id,
            command_id=command_id,
            executable=executable,
            arguments=arguments or ["--version"],
            executable_aliases=[],
            description="integration test command",
            status="active",
            version=1,
            allowed_env_vars=[],
            max_output_bytes=1_000_000,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        ExecutionProfileModel(
            id=f"profile-row-{run_id}",
            run_id=run_id,
            idempotency_key=f"profile-{run_id}",
            request_checksum="sha256:profile-request",
            policy_version="execution-profile-v1",
            status="selected",
            source_angular_exact="18.2.0",
            selected_profile_id=profile_id,
            selected_checksum="sha256:runtime-profile",
            profiles=[
                {
                    "profile_id": profile_id,
                    "checksum": "sha256:runtime-profile",
                    "environment_allowlist": ["PATH"],
                }
            ],
            blockers=[],
            guidance=[],
            artifact_ids=[],
            state_version=1,
            event_sequence=1,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        CommandAuthorizationAuditModel(
            id=f"auth-{run_id}",
            run_id=run_id,
            stage_id=None,
            command_id=command_id,
            template_id=template_id,
            template_version=1,
            plan_id=None,
            plan_version=None,
            executable=executable,
            arguments=arguments or ["--version"],
            decision="accepted",
            reasons=[],
            policy_version="s3-f01-v1",
            idempotency_key=execution_idempotency_key or f"execute-{run_id}-1",
            request_payload_hash="sha256:authorization-request",
            expected_state_version=1,
            execution_profile_id=profile_id,
            workspace_alias="BASELINE_SANDBOX",
            network_profile="none",
            correlation_id=f"corr-{run_id}",
            actor="alice",
            artifact_ids=[],
            state_version=1,
            created_at=now,
        )
    )
    session.commit()


def _wait_for_terminal(client: TestClient, run_id: str, execution_id: str) -> dict:
    terminal = {"succeeded", "failed", "timed_out", "cancelled", "interrupted"}
    for _ in range(100):
        response = client.get(
            f"/api/v1/runs/{run_id}/commands/{execution_id}",
            headers={"x-authenticated-actor": "alice"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in terminal:
            return payload
        time.sleep(0.02)
    pytest.fail(f"execution {execution_id} did not reach a terminal state")


def test_s3_f02_api_happy_path_persists_real_execution_and_supports_replay_and_stale(
    isolated_command_api,
):
    client, factory, root = isolated_command_api
    with factory() as session:
        _create_run(
            session,
            root,
            run_id="run-success",
            execution_idempotency_key="execute-run-success-1",
        )

    request = {
        "authorization_decision_id": "auth-run-success",
        "expected_state_version": 1,
        "idempotency_key": "execute-run-success-1",
        "requested_by": "spoofed-client",
    }
    headers = {
        "x-authenticated-actor": "alice",
        "x-correlation-id": "corr-api-success",
    }
    queued = client.post("/api/v1/runs/run-success/commands", headers=headers, json=request)
    assert queued.status_code == 202, queued.text
    queued_payload = queued.json()
    execution_id = queued_payload["execution_id"]
    assert queued_payload["status"] == "queued"

    terminal = _wait_for_terminal(client, "run-success", execution_id)
    assert terminal["status"] == "succeeded"
    assert terminal["exit_code"] == 0
    assert terminal["executable"] == "python"
    assert terminal["arguments"] == ["--version"]
    assert terminal["safe_relative_working_directory"] == "BASELINE_SANDBOX"
    assert terminal["correlation_id"] == "corr-api-success"
    assert len(terminal["artifact_ids"]) == 5

    forbidden = client.get(
        f"/api/v1/runs/run-success/commands/{execution_id}",
        headers={"x-authenticated-actor": "bob"},
    )
    assert forbidden.status_code == 403

    with factory() as session:
        execution = session.get(CommandExecutionModel, execution_id)
        assert execution is not None
        assert execution.requested_by == "alice"
        assert execution.status == "succeeded"
        assert execution.idempotency_key == request["idempotency_key"]
        assert execution.runtime_checksum == "sha256:runtime-profile"
        assert execution.started_at is not None
        assert execution.finished_at is not None
        assert execution.stdout_artifact_id is not None
        assert execution.stderr_artifact_id is not None
        assert execution.manifest_artifact_id is not None
        assert execution.result_artifact_id is not None
        events = list(
            session.scalars(
                select(WorkflowEventModel)
                .where(WorkflowEventModel.run_id == "run-success")
                .order_by(WorkflowEventModel.sequence)
            )
        )
        assert [event.event_type for event in events] == [
            "COMMAND_QUEUED",
            "COMMAND_STARTED",
            "COMMAND_SUCCEEDED",
        ]
        assert [event.sequence for event in events] == [1, 2, 3]
        metadata = list(
            session.scalars(
                select(ArtifactMetadataModel).where(ArtifactMetadataModel.execution_id == execution_id)
            )
        )
        assert len(metadata) == 5
        assert all(item.immutable and item.finalized_at is not None for item in metadata)

    for artifact_id in terminal["artifact_ids"]:
        artifact = client.get(
            f"/api/v1/artifacts/{artifact_id}",
            headers={"x-authenticated-actor": "alice"},
        )
        assert artifact.status_code == 200, artifact.text
        assert artifact.json()["artifact"]["checksum"].startswith("sha256:")

    replay = client.post("/api/v1/runs/run-success/commands", headers=headers, json=request)
    assert replay.status_code == 202, replay.text
    assert replay.json()["execution_id"] == execution_id
    assert replay.json()["idempotent_replay"] is True

    with factory() as session:
        session.get(MigrationRunModel, "run-success").state_version = 2
        session.commit()
    stale = client.post(
        "/api/v1/runs/run-success/commands",
        headers=headers,
        json={**request, "idempotency_key": "execute-run-success-stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["error_code"] == "STALE_STATE_VERSION"
    with factory() as session:
        assert session.scalar(select(CommandExecutionModel).where(CommandExecutionModel.run_id == "run-success")).id == execution_id


def test_s3_f02_api_real_worker_failure_persists_failed_state_evidence_and_event(
    isolated_command_api, monkeypatch: pytest.MonkeyPatch
):
    client, factory, root = isolated_command_api
    failing_arguments = ["-c", "import sys; print('failure-output'); sys.exit(7)"]
    with factory() as session:
        _create_run(
            session,
            root,
            run_id="run-failure",
            command_id="python-failure",
            template_id="tpl-python-failure",
            arguments=failing_arguments,
            execution_idempotency_key="execute-run-failure-1",
        )

    registry = CommandRegistry(
        definitions=(CommandDefinition("python-failure", "python", tuple(failing_arguments)),)
    )
    monkeypatch.setattr(command_executor_service, "CommandRegistry", lambda: registry)
    response = client.post(
        "/api/v1/runs/run-failure/commands",
        headers={"x-authenticated-actor": "alice"},
        json={
            "authorization_decision_id": "auth-run-failure",
            "expected_state_version": 1,
            "idempotency_key": "execute-run-failure-1",
        },
    )
    assert response.status_code == 202, response.text
    execution_id = response.json()["execution_id"]
    terminal = _wait_for_terminal(client, "run-failure", execution_id)
    assert terminal["status"] == "failed"
    assert terminal["exit_code"] == 7
    assert len(terminal["artifact_ids"]) == 5

    with factory() as session:
        execution = session.get(CommandExecutionModel, execution_id)
        assert execution.status == "failed"
        assert execution.failure_code == "COMMAND_EXIT_NONZERO"
        event = session.scalar(
            select(WorkflowEventModel)
            .where(
                WorkflowEventModel.run_id == "run-failure",
                WorkflowEventModel.event_type == "COMMAND_FAILED",
            )
        )
        assert event is not None
        assert event.payload["execution_id"] == execution_id
