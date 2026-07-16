"""Structured command execution boundary for Sprint 0.

Only this module may start local processes. Sprint 0 intentionally allows a
small version-check registry, validates every structured request field, and
persists bounded command evidence as artifacts.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Final

from app.artifact_store import LocalFilesystemArtifactStore, StoredArtifact
from app.domain.contracts import (
    ArtifactType,
    CancellationPolicy,
    CommandRequestDto,
    CommandResultDto,
    CommandStatus,
)

CommandRequest = CommandRequestDto

_DEFAULT_RUNTIME_PROFILE: Final = "source-runtime-profile"
_DEFAULT_NETWORK_PROFILE: Final = "none"
_MUTABLE_WORKSPACE_ALIASES: Final = frozenset({"BASELINE_SANDBOX", "STAGE_SANDBOX", "REPAIR_SANDBOX", "FINAL_ASSURANCE_SANDBOX", "DELIVERY_CANDIDATE"})


class CommandPolicyViolation(ValueError):
    """Raised when a command request violates the execution policy."""


@dataclass(frozen=True)
class CommandDefinition:
    """One registered command shape allowed by the Sprint 0 worker."""

    command_id: str
    executable: str
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class StructuredCommandRequest:
    """Policy-normalized command request ready for supervised execution."""

    dto: CommandRequestDto
    definition: CommandDefinition
    command: tuple[str, ...]
    working_directory: Path


@dataclass(frozen=True)
class CommandExecutionResult:
    """Structured worker result plus persisted command artifacts."""

    result: CommandResultDto
    command_log_artifact: StoredArtifact
    stdout_artifact: StoredArtifact | None = None
    stderr_artifact: StoredArtifact | None = None
    idempotent_replay: bool = False


@dataclass(frozen=True)
class SupervisedProcessResult:
    """Output returned by the process supervisor."""

    status: CommandStatus
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    cancelled: bool = False


@dataclass(frozen=True)
class CommandRegistry:
    """Registry of safe command definitions."""

    definitions: tuple[CommandDefinition, ...] = (
        CommandDefinition("python-version", "python", ("--version",)),
        CommandDefinition("node-version", "node", ("--version",)),
        CommandDefinition("npm-version", "npm", ("--version",)),
        CommandDefinition("npx-version", "npx", ("--version",)),
        CommandDefinition("git-version", "git", ("--version",)),
        CommandDefinition("npm-ci-bootstrap", "npm", ("ci",)),
    )

    def find(self, command_id: str) -> CommandDefinition:
        for definition in self.definitions:
            if definition.command_id == command_id:
                return definition
        raise CommandPolicyViolation("Command ID is not registered for Sprint 0 execution")


@dataclass(frozen=True)
class CommandPolicy:
    """Allowlist, working-directory, runtime, network, and cancellation policy."""

    sandbox_root: Path
    registry: CommandRegistry = field(default_factory=CommandRegistry)
    working_directory_aliases: dict[str, Path] = field(default_factory=dict)
    runtime_profiles: frozenset[str] = frozenset({_DEFAULT_RUNTIME_PROFILE})
    network_profiles: frozenset[str] = frozenset({_DEFAULT_NETWORK_PROFILE})

    def __post_init__(self) -> None:
        aliases = {name: Path(path).resolve() for name, path in self.working_directory_aliases.items()}
        if not set(aliases).issubset(_MUTABLE_WORKSPACE_ALIASES):
            raise CommandPolicyViolation("Only registered mutable workspace aliases may execute commands")
        object.__setattr__(self, "working_directory_aliases", aliases)

    def validate(self, request: CommandRequestDto) -> StructuredCommandRequest:
        """Return a normalized request or raise a policy violation."""
        if request.shell is not False:
            raise CommandPolicyViolation("Shell execution is forbidden in Sprint 0")
        if not request.idempotency_key or not request.idempotency_key.strip():
            raise CommandPolicyViolation("Idempotency key is required")
        if request.timeout_seconds <= 0:
            raise CommandPolicyViolation("Timeout must be greater than zero")
        if request.runtime_profile_id not in self.runtime_profiles:
            raise CommandPolicyViolation("Runtime profile is not registered")
        if request.network_profile not in self.network_profiles:
            raise CommandPolicyViolation("Network profile is not registered")
        if request.cancellation_policy is not CancellationPolicy.TERMINATE_PROCESS_TREE:
            raise CommandPolicyViolation("Cancellation policy is not supported by the Sprint 0 supervisor")

        definition = self.registry.find(request.command_id)
        if request.executable != definition.executable:
            raise CommandPolicyViolation("Executable does not match the registered command definition")
        if tuple(request.arguments) != definition.arguments:
            raise CommandPolicyViolation("Arguments do not match the registered command definition")

        working_directory = self._resolve_working_directory(request)
        if not working_directory.is_dir():
            raise CommandPolicyViolation("Working directory must exist inside the sandbox root")

        return StructuredCommandRequest(
            dto=request,
            definition=definition,
            command=(definition.executable, *definition.arguments),
            working_directory=working_directory,
        )

    def _resolve_working_directory(self, request: CommandRequestDto) -> Path:
        if request.working_directory_alias:
            if request.working_directory_alias not in self.working_directory_aliases:
                raise CommandPolicyViolation("Working directory alias is not registered")
            candidate = self.working_directory_aliases[request.working_directory_alias]
        elif request.working_directory:
            raw_path = Path(request.working_directory)
            candidate = raw_path if raw_path.is_absolute() else self.sandbox_root / raw_path
        else:
            raise CommandPolicyViolation("Working directory alias is required")

        sandbox_root = self.sandbox_root.resolve()
        resolved = Path(candidate).resolve()
        try:
            resolved.relative_to(sandbox_root)
        except ValueError as exc:
            raise CommandPolicyViolation("Working directory must stay inside the sandbox root") from exc
        return resolved


class CommandLogWriter:
    """Persist command execution records and bounded output artifacts."""

    def __init__(self, artifact_store: LocalFilesystemArtifactStore, *, max_output_bytes: int = 1_000_000) -> None:
        self._artifact_store = artifact_store
        self._max_output_bytes = max_output_bytes

    def write(
        self,
        request: CommandRequestDto,
        result: CommandResultDto,
        *,
        command: tuple[str, ...],
        working_directory: Path,
        stdout: str,
        stderr: str,
        rejection_reason: str | None = None,
        timed_out: bool = False,
        cancelled: bool = False,
    ) -> CommandExecutionResult:
        stdout_text, stdout_truncated = self._bound_text(stdout)
        stderr_text, stderr_truncated = self._bound_text(stderr)

        stdout_artifact = self._write_output_artifact(request, result, "stdout", stdout_text)
        stderr_artifact = self._write_output_artifact(request, result, "stderr", stderr_text)
        result_with_artifacts = result.model_copy(
            update={
                "stdout_artifact": stdout_artifact.ref if stdout_artifact else None,
                "stderr_artifact": stderr_artifact.ref if stderr_artifact else None,
            }
        )

        payload = {
            "command_id": result.command_id,
            "run_id": result.run_id,
            "stage_id": result.stage_id,
            "command": list(command),
            "shell": request.shell,
            "working_directory_alias": request.working_directory_alias,
            "working_directory": str(working_directory),
            "runtime_profile_id": request.runtime_profile_id,
            "timeout_seconds": request.timeout_seconds,
            "network_profile": request.network_profile,
            "cancellation_policy": request.cancellation_policy.value,
            "idempotency_key": request.idempotency_key,
            "requested_by": request.requested_by,
            "requester": request.requester,
            "stdout_artifact_id": stdout_artifact.ref.artifact_id if stdout_artifact else None,
            "stderr_artifact_id": stderr_artifact.ref.artifact_id if stderr_artifact else None,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "exit_code": result.exit_code,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat() if result.finished_at else None,
            "duration_ms": result.duration_ms,
            "status": result.status.value,
            "timed_out": timed_out,
            "cancelled": cancelled,
            "rejection_reason": rejection_reason,
        }
        artifact_path = f"04_workflow_state/command_logs/{result.command_id}.json"
        command_log_artifact = self._artifact_store.write_text_artifact(
            result.run_id,
            artifact_path,
            json.dumps(payload, indent=2, sort_keys=True),
            ArtifactType.COMMAND_LOG,
            stage_id=result.stage_id,
            created_by="command-execution-worker",
            created_at=result.finished_at or result.started_at,
        )
        return CommandExecutionResult(
            result=result_with_artifacts,
            command_log_artifact=command_log_artifact,
            stdout_artifact=stdout_artifact,
            stderr_artifact=stderr_artifact,
        )

    def _write_output_artifact(
        self,
        request: CommandRequestDto,
        result: CommandResultDto,
        stream_name: str,
        content: str,
    ) -> StoredArtifact | None:
        if content == "":
            return None
        return self._artifact_store.write_text_artifact(
            result.run_id,
            f"04_workflow_state/command_logs/{result.command_id}.{stream_name}.log",
            content,
            ArtifactType.TEXT_LOG,
            stage_id=result.stage_id,
            created_by="command-execution-worker",
            created_at=result.finished_at or result.started_at,
            input_hashes={"command_id": request.command_id},
        )

    def _bound_text(self, value: str | bytes | None) -> tuple[str, bool]:
        if value is None:
            return "", False
        text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
        payload = text.encode("utf-8")
        if len(payload) <= self._max_output_bytes:
            return text, False
        bounded = payload[: self._max_output_bytes].decode("utf-8", errors="replace")
        return bounded + "\n[command output truncated]", True


class WorkerSupervisor:
    """Run approved processes with shell disabled and process-tree termination."""

    def run(self, request: StructuredCommandRequest) -> SupervisedProcessResult:
        creationflags = 0
        popen_kwargs: dict[str, object] = {}
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(
            list(request.command),
            cwd=request.working_directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            creationflags=creationflags,
            **popen_kwargs,
        )
        try:
            stdout, stderr = process.communicate(timeout=request.dto.timeout_seconds)
        except subprocess.TimeoutExpired:
            self.terminate_process_tree(process)
            stdout, stderr = process.communicate()
            return SupervisedProcessResult(
                status=CommandStatus.CANCELLED,
                exit_code=None,
                stdout=stdout or "",
                stderr=stderr or f"Command timed out after {request.dto.timeout_seconds} seconds",
                timed_out=True,
                cancelled=True,
            )

        status = CommandStatus.SUCCEEDED if process.returncode == 0 else CommandStatus.FAILED
        return SupervisedProcessResult(
            status=status,
            exit_code=process.returncode,
            stdout=stdout or "",
            stderr=stderr or "",
        )

    def terminate_process_tree(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
                process.wait(timeout=1)
                return
            except (AttributeError, subprocess.TimeoutExpired, ProcessLookupError, ValueError):
                process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=1)
                return
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    return
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class ExecutionWorker:
    """Validate and run approved commands through the backend authority boundary."""

    def __init__(
        self,
        policy: CommandPolicy,
        log_writer: CommandLogWriter,
        *,
        timeout_seconds: int | None = None,
        supervisor: WorkerSupervisor | None = None,
    ) -> None:
        self._policy = policy
        self._log_writer = log_writer
        self._default_timeout_seconds = timeout_seconds
        self._supervisor = supervisor or WorkerSupervisor()
        self._idempotency_records: dict[tuple[str, str], CommandExecutionResult] = {}

    def run(self, request: CommandRequestDto) -> CommandExecutionResult:
        replay = self._find_idempotent_result(request)
        if replay is not None:
            return CommandExecutionResult(
                result=replay.result,
                command_log_artifact=replay.command_log_artifact,
                stdout_artifact=replay.stdout_artifact,
                stderr_artifact=replay.stderr_artifact,
                idempotent_replay=True,
            )

        started_at = datetime.now(UTC)
        start_time = monotonic()
        normalized_request = self._apply_default_timeout(request)
        fallback_working_directory = self._policy.sandbox_root.resolve()
        command = (normalized_request.executable, *normalized_request.arguments)

        try:
            structured_request = self._policy.validate(normalized_request)
        except CommandPolicyViolation as exc:
            execution = self._record(
                normalized_request,
                CommandStatus.REJECTED,
                started_at,
                start_time,
                command=command,
                working_directory=fallback_working_directory,
                stdout="",
                stderr=str(exc),
                exit_code=None,
                rejection_reason=str(exc),
            )
            self._remember_idempotent_result(normalized_request, execution)
            return execution

        supervised = self._supervisor.run(structured_request)
        execution = self._record(
            normalized_request,
            supervised.status,
            started_at,
            start_time,
            command=structured_request.command,
            working_directory=structured_request.working_directory,
            stdout=supervised.stdout,
            stderr=supervised.stderr,
            exit_code=supervised.exit_code,
            timed_out=supervised.timed_out,
            cancelled=supervised.cancelled,
        )
        self._remember_idempotent_result(normalized_request, execution)
        return execution

    def _record(
        self,
        request: CommandRequestDto,
        status: CommandStatus,
        started_at: datetime,
        start_time: float,
        *,
        command: tuple[str, ...],
        working_directory: Path,
        stdout: str,
        stderr: str,
        exit_code: int | None,
        rejection_reason: str | None = None,
        timed_out: bool = False,
        cancelled: bool = False,
    ) -> CommandExecutionResult:
        finished_at = datetime.now(UTC)
        result = CommandResultDto(
            command_id=request.command_id,
            run_id=request.run_id,
            stage_id=request.stage_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(0, round((monotonic() - start_time) * 1000)),
            exit_code=exit_code,
        )
        return self._log_writer.write(
            request,
            result,
            command=command,
            working_directory=working_directory,
            stdout=stdout,
            stderr=stderr,
            rejection_reason=rejection_reason,
            timed_out=timed_out,
            cancelled=cancelled,
        )

    def _apply_default_timeout(self, request: CommandRequestDto) -> CommandRequestDto:
        if self._default_timeout_seconds is None or request.timeout_seconds != 30:
            return request
        return request.model_copy(update={"timeout_seconds": self._default_timeout_seconds})

    def _find_idempotent_result(self, request: CommandRequestDto) -> CommandExecutionResult | None:
        if not request.idempotency_key:
            return None
        return self._idempotency_records.get((request.run_id, request.idempotency_key))

    def _remember_idempotent_result(self, request: CommandRequestDto, execution: CommandExecutionResult) -> None:
        if request.idempotency_key:
            self._idempotency_records[(request.run_id, request.idempotency_key)] = execution
