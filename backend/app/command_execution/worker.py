"""Sandbox command execution boundary for Sprint 0.

The worker intentionally supports only version-check preflight commands in
Sprint 0. It never invokes a shell; every request is validated against an
allowlist and a sandbox-root working-directory policy before execution.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Final

from app.artifact_store import LocalFilesystemArtifactStore, StoredArtifact
from app.domain.contracts import ArtifactType, CommandRequestDto, CommandResultDto, CommandStatus

CommandRequest = CommandRequestDto

_ALLOWED_PREFLIGHT_COMMANDS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("python", ("--version",)),
    ("node", ("--version",)),
    ("npm", ("--version",)),
    ("git", ("--version",)),
)


class CommandPolicyViolation(ValueError):
    """Raised when a command request violates the sandbox execution policy."""


@dataclass(frozen=True)
class CommandExecutionResult:
    """Structured worker result plus the persisted command log artifact."""

    result: CommandResultDto
    command_log_artifact: StoredArtifact


@dataclass(frozen=True)
class CommandPolicy:
    """Allowlist and sandbox working-directory policy for command requests."""

    sandbox_root: Path
    allowed_commands: tuple[tuple[str, tuple[str, ...]], ...] = _ALLOWED_PREFLIGHT_COMMANDS

    def validate(self, request: CommandRequestDto) -> Path:
        """Return a resolved working directory or raise a policy violation."""
        command = (request.executable, tuple(request.arguments))
        if command not in self.allowed_commands:
            raise CommandPolicyViolation("Command is not in the Sprint 0 preflight allowlist")

        working_directory = self._resolve_working_directory(request.working_directory)
        if not working_directory.is_dir():
            raise CommandPolicyViolation("Working directory must exist inside the sandbox root")
        return working_directory

    def _resolve_working_directory(self, working_directory: str) -> Path:
        if not working_directory.strip():
            raise CommandPolicyViolation("Working directory is required")
        raw_path = Path(working_directory)
        candidate = raw_path if raw_path.is_absolute() else self.sandbox_root / raw_path
        sandbox_root = self.sandbox_root.resolve()
        resolved = candidate.resolve()
        try:
            resolved.relative_to(sandbox_root)
        except ValueError as exc:
            raise CommandPolicyViolation("Working directory must stay inside the sandbox root") from exc
        return resolved


class CommandLogWriter:
    """Persist command execution records as command-log artifacts."""

    def __init__(self, artifact_store: LocalFilesystemArtifactStore) -> None:
        self._artifact_store = artifact_store

    def write(
        self,
        request: CommandRequestDto,
        result: CommandResultDto,
        *,
        command: list[str],
        working_directory: Path,
        stdout: str,
        stderr: str,
        rejection_reason: str | None = None,
    ) -> StoredArtifact:
        payload = {
            "command_id": result.command_id,
            "run_id": result.run_id,
            "stage_id": result.stage_id,
            "command": command,
            "working_directory": str(working_directory),
            "requester": request.requester,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.exit_code,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat() if result.finished_at else None,
            "duration_ms": result.duration_ms,
            "status": result.status.value,
            "rejection_reason": rejection_reason,
        }
        artifact_path = f"04_workflow_state/command_logs/{result.command_id}.json"
        return self._artifact_store.write_text_artifact(
            result.run_id,
            artifact_path,
            json.dumps(payload, indent=2, sort_keys=True),
            ArtifactType.COMMAND_LOG,
            stage_id=result.stage_id,
            created_by="command-execution-worker",
            created_at=result.finished_at or result.started_at,
        )


class ExecutionWorker:
    """Validate and run approved commands through the backend authority boundary."""

    def __init__(
        self,
        policy: CommandPolicy,
        log_writer: CommandLogWriter,
        *,
        timeout_seconds: int,
    ) -> None:
        self._policy = policy
        self._log_writer = log_writer
        self._timeout_seconds = timeout_seconds

    def run(self, request: CommandRequestDto) -> CommandExecutionResult:
        started_at = datetime.now(UTC)
        start_time = monotonic()
        command = [request.executable, *request.arguments]
        fallback_working_directory = self._policy.sandbox_root.resolve()

        try:
            working_directory = self._policy.validate(request)
        except CommandPolicyViolation as exc:
            finished_at = datetime.now(UTC)
            result = self._build_result(
                request,
                CommandStatus.REJECTED,
                started_at,
                finished_at,
                start_time,
                exit_code=None,
            )
            artifact = self._log_writer.write(
                request,
                result,
                command=command,
                working_directory=fallback_working_directory,
                stdout="",
                stderr=str(exc),
                rejection_reason=str(exc),
            )
            return CommandExecutionResult(result=result, command_log_artifact=artifact)

        try:
            completed = subprocess.run(
                command,
                cwd=working_directory,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                shell=False,
                check=False,
            )
            finished_at = datetime.now(UTC)
            status = CommandStatus.SUCCEEDED if completed.returncode == 0 else CommandStatus.FAILED
            result = self._build_result(
                request,
                status,
                started_at,
                finished_at,
                start_time,
                exit_code=completed.returncode,
            )
            artifact = self._log_writer.write(
                request,
                result,
                command=command,
                working_directory=working_directory,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
            return CommandExecutionResult(result=result, command_log_artifact=artifact)
        except subprocess.TimeoutExpired as exc:
            finished_at = datetime.now(UTC)
            result = self._build_result(
                request,
                CommandStatus.TIMED_OUT,
                started_at,
                finished_at,
                start_time,
                exit_code=None,
            )
            artifact = self._log_writer.write(
                request,
                result,
                command=command,
                working_directory=working_directory,
                stdout=exc.stdout or "",
                stderr=exc.stderr or f"Command timed out after {self._timeout_seconds} seconds",
            )
            return CommandExecutionResult(result=result, command_log_artifact=artifact)

    def _build_result(
        self,
        request: CommandRequestDto,
        status: CommandStatus,
        started_at: datetime,
        finished_at: datetime,
        start_time: float,
        *,
        exit_code: int | None,
    ) -> CommandResultDto:
        return CommandResultDto(
            command_id=request.command_id,
            run_id=request.run_id,
            stage_id=request.stage_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(0, round((monotonic() - start_time) * 1000)),
            exit_code=exit_code,
        )
