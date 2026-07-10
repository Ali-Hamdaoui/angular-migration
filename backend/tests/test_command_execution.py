"""Tests for the Sprint 0 sandbox command execution worker."""

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution import CommandLogWriter, CommandPolicy, ExecutionWorker
from app.domain.contracts import ArtifactType, CommandRequestDto, CommandStatus
from app.main import app


def _request(
    *,
    command_id: str = "cmd-python-version",
    executable: str = "python",
    arguments: list[str] | None = None,
    working_directory: str,
) -> CommandRequestDto:
    return CommandRequestDto(
        command_id=command_id,
        run_id="mock-run-angular-18-to-21",
        stage_id=None,
        requester="runtime-preflight",
        executable=executable,
        arguments=arguments or ["--version"],
        working_directory=working_directory,
        requested_at=datetime.now(UTC),
    )


def _worker(tmp_path: Path) -> tuple[ExecutionWorker, LocalFilesystemArtifactStore, Path]:
    artifact_store = LocalFilesystemArtifactStore(tmp_path / "runs")
    sandbox_root = tmp_path / "sandboxes"
    sandbox_root.mkdir()
    worker = ExecutionWorker(
        CommandPolicy(sandbox_root=sandbox_root),
        CommandLogWriter(artifact_store),
        timeout_seconds=5,
    )
    return worker, artifact_store, sandbox_root


def test_worker_runs_safe_python_version_command_and_writes_command_log(tmp_path: Path) -> None:
    worker, artifact_store, sandbox_root = _worker(tmp_path)

    execution = worker.run(_request(working_directory=str(sandbox_root)))

    assert execution.result.status == CommandStatus.SUCCEEDED
    assert execution.result.exit_code == 0
    assert execution.command_log_artifact.ref.artifact_type == ArtifactType.COMMAND_LOG
    assert execution.command_log_artifact.ref.relative_path == "04_workflow_state/command_logs/cmd-python-version.json"

    stored = artifact_store.read_artifact(
        "mock-run-angular-18-to-21",
        execution.command_log_artifact.ref.relative_path,
    )
    assert '"command": [' in stored.content
    assert '"python"' in stored.content
    assert '"status": "SUCCEEDED"' in stored.content


def test_worker_rejects_commands_outside_preflight_allowlist(tmp_path: Path) -> None:
    worker, artifact_store, sandbox_root = _worker(tmp_path)

    execution = worker.run(
        _request(
            command_id="cmd-npm-install",
            executable="npm",
            arguments=["install"],
            working_directory=str(sandbox_root),
        )
    )

    assert execution.result.status == CommandStatus.REJECTED
    assert execution.result.exit_code is None
    stored = artifact_store.read_artifact("mock-run-angular-18-to-21", "04_workflow_state/command_logs/cmd-npm-install.json")
    assert "not in the Sprint 0 preflight allowlist" in stored.content


def test_worker_rejects_working_directory_outside_sandbox_root(tmp_path: Path) -> None:
    worker, artifact_store, _sandbox_root = _worker(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    execution = worker.run(
        _request(
            command_id="cmd-outside-sandbox",
            working_directory=str(outside),
        )
    )

    assert execution.result.status == CommandStatus.REJECTED
    stored = artifact_store.read_artifact(
        "mock-run-angular-18-to-21",
        "04_workflow_state/command_logs/cmd-outside-sandbox.json",
    )
    assert "must stay inside the sandbox root" in stored.content


def test_worker_rejects_missing_sandbox_working_directory(tmp_path: Path) -> None:
    worker, _artifact_store, sandbox_root = _worker(tmp_path)

    execution = worker.run(
        _request(
            command_id="cmd-missing-workdir",
            working_directory=str(sandbox_root / "missing"),
        )
    )

    assert execution.result.status == CommandStatus.REJECTED


def test_command_logs_are_visible_through_artifact_api(monkeypatch, tmp_path: Path) -> None:
    worker, artifact_store, sandbox_root = _worker(tmp_path)
    execution = worker.run(_request(working_directory=str(sandbox_root)))
    monkeypatch.setattr("app.api.routes.artifacts.get_artifact_store", lambda: artifact_store)

    client = TestClient(app)
    list_response = client.get("/migrations/mock-run-angular-18-to-21/artifacts")
    read_response = client.get(
        f"/migrations/mock-run-angular-18-to-21/artifacts/{execution.command_log_artifact.ref.relative_path}"
    )

    assert list_response.status_code == 200
    assert execution.command_log_artifact.ref.relative_path in [item["relative_path"] for item in list_response.json()]
    assert read_response.status_code == 200
    assert read_response.json()["artifact"]["artifact_type"] == "command_log"