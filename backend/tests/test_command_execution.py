"""Tests for the Sprint 0 sandbox command execution worker."""

from datetime import UTC, datetime
import ctypes
import os
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution import (
    CommandDefinition,
    CommandLogWriter,
    CommandPolicy,
    CommandRegistry,
    ExecutionWorker,
    WorkerSupervisor,
)
from app.domain.contracts import ArtifactType, CancellationPolicy, CommandRequestDto, CommandStatus
from app.main import app


def _request(
    *,
    command_id: str = "python-version",
    executable: str = "python",
    arguments: list[str] | None = None,
    working_directory_alias: str | None = "BASELINE_SANDBOX",
    working_directory: str | None = None,
    runtime_profile_id: str = "source-runtime-profile",
    timeout_seconds: int = 5,
    idempotency_key: str = "python-version-key",
) -> CommandRequestDto:
    return CommandRequestDto(
        command_id=command_id,
        run_id="mock-run-angular-18-to-21",
        stage_id=None,
        requested_by="runtime-preflight",
        requester="runtime-preflight",
        executable=executable,
        arguments=arguments or ["--version"],
        shell=False,
        working_directory_alias=working_directory_alias,
        working_directory=working_directory,
        runtime_profile_id=runtime_profile_id,
        timeout_seconds=timeout_seconds,
        network_profile="none",
        cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
        idempotency_key=idempotency_key,
        requested_at=datetime.now(UTC),
    )


def _worker(
    tmp_path: Path,
    *,
    registry: CommandRegistry | None = None,
    timeout_seconds: int = 5,
) -> tuple[ExecutionWorker, LocalFilesystemArtifactStore, Path]:
    artifact_store = LocalFilesystemArtifactStore(tmp_path / "runs")
    sandbox_root = tmp_path / "sandboxes"
    sandbox_root.mkdir()
    worker = ExecutionWorker(
        CommandPolicy(
            sandbox_root=sandbox_root,
            registry=registry or CommandRegistry(),
            working_directory_aliases={"BASELINE_SANDBOX": sandbox_root},
        ),
        CommandLogWriter(artifact_store, max_output_bytes=128),
        timeout_seconds=timeout_seconds,
    )
    return worker, artifact_store, sandbox_root


def test_worker_does_not_retry_supervisor_after_type_error(tmp_path: Path) -> None:
    class TypeErrorSupervisor(WorkerSupervisor):
        def __init__(self):
            self.calls = 0

        def run(self, request, *, cancel_event=None, output_callback=None):
            self.calls += 1
            raise TypeError("supervisor failure")

    supervisor = TypeErrorSupervisor()
    artifact_store = LocalFilesystemArtifactStore(tmp_path / "runs")
    sandbox_root = tmp_path / "sandboxes"
    sandbox_root.mkdir()
    worker = ExecutionWorker(
        CommandPolicy(
            sandbox_root=sandbox_root,
            registry=CommandRegistry(),
            working_directory_aliases={"BASELINE_SANDBOX": sandbox_root},
        ),
        CommandLogWriter(artifact_store),
        supervisor=supervisor,
    )

    with pytest.raises(TypeError, match="supervisor failure"):
        worker.run(_request())
    assert supervisor.calls == 1


def test_worker_runs_safe_python_version_command_and_writes_command_artifacts(tmp_path: Path) -> None:
    worker, artifact_store, _sandbox_root = _worker(tmp_path)

    execution = worker.run(_request())

    assert execution.result.status == CommandStatus.SUCCEEDED
    assert execution.result.exit_code == 0
    assert execution.command_log_artifact.ref.artifact_type == ArtifactType.COMMAND_LOG
    assert execution.command_log_artifact.ref.relative_path == "04_workflow_state/command_logs/python-version.json"
    assert execution.result.stdout_artifact or execution.result.stderr_artifact

    stored = artifact_store.read_artifact(
        "mock-run-angular-18-to-21",
        execution.command_log_artifact.ref.relative_path,
    )
    assert '"command": [' in stored.content
    assert '"python"' in stored.content
    assert '"shell": false' in stored.content
    assert '"status": "succeeded"' in stored.content
    assert '"runtime_profile_id": "source-runtime-profile"' in stored.content


def test_process_id_is_reported_before_normal_output(tmp_path: Path) -> None:
    worker, _, _ = _worker(tmp_path)
    structured = worker._policy.validate(_request())
    observed: list[tuple[str, int | str]] = []

    WorkerSupervisor().run(
        structured,
        process_started_callback=lambda pid: observed.append(("pid", pid)),
        output_callback=lambda _stream, text: observed.append(("output", text)),
    )

    assert observed
    assert observed[0][0] == "pid"
    assert isinstance(observed[0][1], int)


def test_supervisor_writes_bounded_stdin_and_closes_pipe(tmp_path: Path) -> None:
    worker, _, _ = _worker(tmp_path)
    structured = replace(
        worker._policy.validate(_request()),
        command=(sys.executable, "-c", "print(input())"),
        stdin_text="yes\n",
    )

    result = WorkerSupervisor().run(structured)

    assert result.status == CommandStatus.SUCCEEDED
    assert result.stdout.strip() == "yes"


def test_supervisor_emits_short_prompt_output_before_process_exit(tmp_path: Path) -> None:
    worker, _, _ = _worker(tmp_path)
    structured = replace(
        worker._policy.validate(_request()),
        command=(
            sys.executable,
            "-c",
            "import sys,time; sys.stdout.write('Would you like to continue? [y/N]\\n'); sys.stdout.flush(); time.sleep(5)",
        ),
    )
    cancel_event = threading.Event()
    observed: list[str] = []
    started = time.monotonic()

    result = WorkerSupervisor().run(
        structured,
        cancel_event=cancel_event,
        output_callback=lambda _stream, text: (observed.append(text), cancel_event.set()),
    )

    assert result.cancelled is True
    assert observed
    assert time.monotonic() - started < 3


def test_worker_registers_output_artifact_truncation_metadata(tmp_path: Path) -> None:
    worker, _artifact_store, _sandbox_root = _worker(tmp_path)

    execution = worker.run(_request())

    # The version output is normally short; exercise the writer contract
    # directly through its bounded output path in a separate fixture below.
    writer = CommandLogWriter(LocalFilesystemArtifactStore(tmp_path / "truncated-runs"), max_output_bytes=4)
    bounded = writer.write(
        _request(idempotency_key="truncated-output-key"),
        execution.result,
        command=("python", "--version"),
        working_directory=_sandbox_root,
        stdout="0123456789",
        stderr="",
    )

    assert bounded.stdout_artifact is not None
    assert bounded.stdout_artifact.envelope.input_hashes["truncated"] == "true"


def test_worker_rejects_unknown_command_id(tmp_path: Path) -> None:
    worker, artifact_store, _sandbox_root = _worker(tmp_path)

    execution = worker.run(
        _request(
            command_id="npm-install",
            executable="npm",
            arguments=["install"],
            idempotency_key="npm-install-key",
        )
    )

    assert execution.result.status == CommandStatus.REJECTED
    assert execution.result.exit_code is None
    stored = artifact_store.read_artifact(
        "mock-run-angular-18-to-21", "04_workflow_state/command_logs/npm-install.json"
    )
    assert "Command ID is not registered" in stored.content


def test_worker_rejects_argument_metacharacters_that_do_not_match_registry(tmp_path: Path) -> None:
    worker, artifact_store, _sandbox_root = _worker(tmp_path)

    execution = worker.run(
        _request(
            arguments=["--version", "&&", "git", "--version"],
            idempotency_key="metacharacter-key",
        )
    )

    assert execution.result.status == CommandStatus.REJECTED
    stored = artifact_store.read_artifact(
        "mock-run-angular-18-to-21", "04_workflow_state/command_logs/python-version.json"
    )
    assert "Arguments do not match" in stored.content


def test_worker_rejects_working_directory_outside_sandbox_root(tmp_path: Path) -> None:
    worker, artifact_store, _sandbox_root = _worker(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    execution = worker.run(
        _request(
            working_directory_alias=None,
            working_directory=str(outside),
            idempotency_key="outside-workdir-key",
        )
    )

    assert execution.result.status == CommandStatus.REJECTED
    stored = artifact_store.read_artifact(
        "mock-run-angular-18-to-21",
        "04_workflow_state/command_logs/python-version.json",
    )
    assert '"status": "rejected"' in stored.content


def test_worker_rejects_unknown_working_directory_alias(tmp_path: Path) -> None:
    worker, _artifact_store, _sandbox_root = _worker(tmp_path)

    execution = worker.run(_request(working_directory_alias="unknown", idempotency_key="unknown-alias-key"))

    assert execution.result.status == CommandStatus.REJECTED


def test_worker_rejects_unknown_runtime_profile(tmp_path: Path) -> None:
    worker, _artifact_store, _sandbox_root = _worker(tmp_path)

    execution = worker.run(_request(runtime_profile_id="unknown-runtime", idempotency_key="unknown-runtime-key"))

    assert execution.result.status == CommandStatus.REJECTED


def test_worker_rejects_unsupported_cancellation_policy(tmp_path: Path) -> None:
    worker, _artifact_store, _sandbox_root = _worker(tmp_path)
    request = _request(idempotency_key="safe-point-key").model_copy(
        update={"cancellation_policy": CancellationPolicy.WAIT_FOR_SAFE_POINT}
    )

    execution = worker.run(request)

    assert execution.result.status == CommandStatus.REJECTED


def test_worker_times_out_and_records_cancelled_status(tmp_path: Path) -> None:
    registry = CommandRegistry(
        definitions=(
            CommandDefinition(
                "python-sleep",
                "python",
                ("-c", "import time; time.sleep(5)"),
            ),
        )
    )
    worker, artifact_store, _sandbox_root = _worker(tmp_path, registry=registry, timeout_seconds=1)

    execution = worker.run(
        _request(
            command_id="python-sleep",
            executable="python",
            arguments=["-c", "import time; time.sleep(5)"],
            idempotency_key="timeout-key",
            timeout_seconds=1,
        )
    )

    assert execution.result.status == CommandStatus.CANCELLED
    stored = artifact_store.read_artifact(
        "mock-run-angular-18-to-21",
        "04_workflow_state/command_logs/python-sleep.json",
    )
    assert '"timed_out": true' in stored.content
    assert '"cancelled": true' in stored.content


def test_duplicate_idempotency_key_returns_recorded_result_without_reexecution(tmp_path: Path) -> None:
    worker, artifact_store, _sandbox_root = _worker(tmp_path)
    request = _request(idempotency_key="same-command-key")

    first = worker.run(request)
    second = worker.run(request.model_copy(update={"command_id": "npm-version", "executable": "npm"}))

    assert second.idempotent_replay is True
    assert second.result == first.result
    assert second.command_log_artifact.ref.artifact_id == first.command_log_artifact.ref.artifact_id
    assert (
        len(
            [
                item
                for item in artifact_store.list_artifacts("mock-run-angular-18-to-21")
                if item.artifact_type == ArtifactType.COMMAND_LOG
            ]
        )
        == 1
    )


def test_command_logs_are_visible_through_artifact_api(monkeypatch, tmp_path: Path) -> None:
    worker, artifact_store, _sandbox_root = _worker(tmp_path)
    execution = worker.run(_request())
    monkeypatch.setattr("app.api.routes.artifacts.get_artifact_store", lambda *args: artifact_store)

    client = TestClient(app)
    list_response = client.get("/migrations/mock-run-angular-18-to-21/artifacts")
    read_response = client.get(
        f"/migrations/mock-run-angular-18-to-21/artifacts/{execution.command_log_artifact.ref.relative_path}"
    )

    assert list_response.status_code == 200
    assert execution.command_log_artifact.ref.relative_path in [item["relative_path"] for item in list_response.json()]
    assert read_response.status_code == 200
    assert read_response.json()["artifact"]["artifact_type"] == "command_log"


def test_worker_cancellation_event_terminates_running_process_tree(tmp_path: Path) -> None:
    registry = CommandRegistry(
        definitions=(
            CommandDefinition(
                "python-sleep", "python", ("-c", "import time; print('started', flush=True); time.sleep(10)")
            ),
        )
    )
    worker, _artifact_store, _sandbox_root = _worker(tmp_path, registry=registry, timeout_seconds=30)
    cancel_event = threading.Event()
    result_holder = {}

    def run_command() -> None:
        result_holder["result"] = worker.run(
            _request(
                command_id="python-sleep",
                executable="python",
                arguments=["-c", "import time; print('started', flush=True); time.sleep(10)"],
                idempotency_key="cancel-process-key",
                timeout_seconds=30,
            ),
            cancel_event=cancel_event,
        )

    thread = threading.Thread(target=run_command)
    thread.start()
    time.sleep(0.25)
    cancel_event.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert result_holder["result"].cancelled is True
    assert result_holder["result"].result.status is CommandStatus.CANCELLED


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object proof")
def test_job_object_terminates_descendant_process(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    script = (
        "import pathlib,subprocess,sys,time;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid));"
        "time.sleep(30)"
    )
    registry = CommandRegistry(
        definitions=(CommandDefinition("python-child", "python", ("-c", script)),)
    )
    worker, _, _ = _worker(tmp_path, registry=registry, timeout_seconds=30)
    cancel_event = threading.Event()
    thread = threading.Thread(
        target=lambda: worker.run(
            _request(
                command_id="python-child",
                executable="python",
                arguments=["-c", script],
                idempotency_key="cancel-descendant",
                timeout_seconds=30,
            ),
            cancel_event=cancel_event,
        )
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert pid_file.exists()
    child_pid = int(pid_file.read_text())

    cancel_event.set()
    thread.join(timeout=5)

    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, child_pid)
    if handle:
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        assert exit_code.value != 259
    assert not thread.is_alive()


@pytest.mark.parametrize(
    ("command_id", "executable"),
    [
        ("node-version", "node.exe"),
        ("npm-version", "npm.cmd"),
        ("npx-version", "npx.cmd"),
        ("git-version", "git.exe"),
        ("python-version", "python.exe"),
        ("python-version", "py"),
    ],
)
def test_policy_allows_registered_windows_version_executables(tmp_path, command_id, executable):
    _worker_instance, _artifact_store, sandbox_root = _worker(tmp_path)
    policy = CommandPolicy(
        sandbox_root=sandbox_root,
        working_directory_aliases={"BASELINE_SANDBOX": sandbox_root},
    )

    structured = policy.validate(_request(command_id=command_id, executable=executable))

    assert structured.command == (executable, "--version")


def test_worker_records_os_start_failure_as_failed_command(tmp_path):
    class MissingExecutableSupervisor(WorkerSupervisor):
        def run(self, request, *, cancel_event=None, output_callback=None):
            raise FileNotFoundError("The system cannot find the file specified")

    artifact_store = LocalFilesystemArtifactStore(tmp_path / "runs")
    sandbox_root = tmp_path / "sandboxes"
    sandbox_root.mkdir()
    worker = ExecutionWorker(
        CommandPolicy(sandbox_root=sandbox_root, working_directory_aliases={"BASELINE_SANDBOX": sandbox_root}),
        CommandLogWriter(artifact_store),
        supervisor=MissingExecutableSupervisor(),
    )

    execution = worker.run(_request())

    assert execution.result.status == CommandStatus.FAILED
    assert execution.stderr_artifact is not None
    assert "Unable to start approved command" in execution.stderr_artifact.content
