"""Structured command execution boundary for Sprint 0.

Only this module may start local processes. Sprint 0 intentionally allows a
small version-check registry, validates every structured request field, and
persists bounded command evidence as artifacts.
"""

from __future__ import annotations

import codecs
import ctypes
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Final

from app.artifact_store import LocalFilesystemArtifactStore, StoredArtifact
from app.domain.command import (
    ANGULAR_UPDATE_V2_RENDERER,
    ANGULAR_UPDATE_V3_RENDERER,
    ANGULAR_UPDATE_V4_RENDERER,
    ANGULAR_UPDATE_V5_RENDERER,
    ANGULAR_INSTALLED_MIGRATION_RENDERER,
    NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER,
    TRANSFORMATION_COMMAND_CATALOGUE,
    command_arguments_match,
)
from app.domain.contracts import (
    ArtifactType,
    CancellationPolicy,
    CommandRequestDto,
    CommandResultDto,
    CommandStatus,
)
from app.domain.runtime_execution import RuntimeExecutableDescriptor, RuntimeExecutableKind
from app.llm_gateway.redaction import redact_prompt_text

CommandRequest = CommandRequestDto

_RUNTIME_PROBE_COMMAND_ID: Final = "runtime-executable-probe"
_WILDCARD_EXECUTABLE: Final = "*"

_DEFAULT_RUNTIME_PROFILE: Final = "source-runtime-profile"
_DEFAULT_NETWORK_PROFILE: Final = "none"
_INSTALLED_MIGRATION_HELPER: Final = (Path(__file__).resolve().parent / "run_installed_migrations.cjs").resolve()
_LEGACY_INSTALLED_MIGRATION_HELPER: Final = "backend/app/command_execution/run_installed_migrations.cjs"
_LIVE_LOG_FIXTURE_ARGUMENTS: Final = (
    "-c",
    "import sys,time; [print(f'MT-003 live line {i}', flush=True) or time.sleep(0.7) for i in range(1,13)]",
)
_MUTABLE_WORKSPACE_ALIASES: Final = frozenset(
    {
        "run_workspace",
        "BASELINE_SANDBOX",
        "STAGE_SANDBOX",
        "REPAIR_SANDBOX",
        "FINAL_ASSURANCE_SANDBOX",
        "DELIVERY_CANDIDATE",
    }
)


def _executable_kind(executable: str) -> RuntimeExecutableKind | None:
    """Map a bare executable name to its runtime executable kind, if any."""
    name = Path(executable).name.lower()
    for kind in RuntimeExecutableKind:
        if name == kind.value or name == f"{kind.value}.exe" or name == f"{kind.value}.cmd":
            return kind
    return None


class _JobBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _JobIoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JobExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobBasicLimitInformation),
        ("IoInfo", _JobIoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _WindowsJobObject:
    """Own one Windows process tree with kill-on-close semantics."""

    _KILL_ON_JOB_CLOSE = 0x00002000

    def __init__(self, process: subprocess.Popen) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32 = kernel32
        self._handle = kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _JobExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = self._KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            self._handle,
            9,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel32.AssignProcessToJobObject(self._handle, int(process._handle)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def terminate(self) -> None:
        if self._handle and not self._kernel32.TerminateJobObject(self._handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if getattr(self, "_handle", None):
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


class CommandPolicyViolation(ValueError):
    """Raised when a command request violates the execution policy."""


@dataclass(frozen=True)
class CommandDefinition:
    """One registered command shape allowed by the Sprint 0 worker."""

    command_id: str
    executable: str
    arguments: tuple[str, ...]
    executable_aliases: tuple[str, ...] = ()

    @property
    def allowed_executables(self) -> frozenset[str]:
        """Executable names permitted for this fixed command shape."""
        return frozenset((self.executable, *self.executable_aliases))

    def matches_arguments(self, arguments: tuple[str, ...]) -> bool:
        return command_arguments_match(self.arguments, arguments)


def _transformation_command_definitions() -> tuple[CommandDefinition, ...]:
    return tuple(
        CommandDefinition(
            definition.command_id,
            definition.executable,
            definition.argument_patterns,
            definition.executable_aliases,
        )
        for definition in TRANSFORMATION_COMMAND_CATALOGUE.values()
    ) + (
        CommandDefinition(
            ANGULAR_UPDATE_V2_RENDERER.command_id,
            ANGULAR_UPDATE_V2_RENDERER.executable,
            ANGULAR_UPDATE_V2_RENDERER.argument_patterns,
            ANGULAR_UPDATE_V2_RENDERER.executable_aliases,
        ),
        CommandDefinition(
            ANGULAR_UPDATE_V3_RENDERER.command_id,
            ANGULAR_UPDATE_V3_RENDERER.executable,
            ANGULAR_UPDATE_V3_RENDERER.argument_patterns,
            ANGULAR_UPDATE_V3_RENDERER.executable_aliases,
        ),
        CommandDefinition(
            ANGULAR_UPDATE_V4_RENDERER.command_id,
            ANGULAR_UPDATE_V4_RENDERER.executable,
            ANGULAR_UPDATE_V4_RENDERER.argument_patterns,
            ANGULAR_UPDATE_V4_RENDERER.executable_aliases,
        ),
        CommandDefinition(
            ANGULAR_UPDATE_V5_RENDERER.command_id,
            ANGULAR_UPDATE_V5_RENDERER.executable,
            ANGULAR_UPDATE_V5_RENDERER.argument_patterns,
            ANGULAR_UPDATE_V5_RENDERER.executable_aliases,
        ),
        CommandDefinition(
            NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER.command_id,
            NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER.executable,
            NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER.argument_patterns,
            NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER.executable_aliases,
        ),
    )


@dataclass(frozen=True)
class StructuredCommandRequest:
    """Policy-normalized command request ready for supervised execution."""

    dto: CommandRequestDto
    definition: CommandDefinition
    command: tuple[str, ...]
    working_directory: Path
    environment_allowlist: tuple[str, ...] = ()
    environment_overrides: dict[str, str] = field(default_factory=dict)
    stdin_text: str | None = None
    runtime_bindings: dict[str, RuntimeExecutableDescriptor] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandExecutionResult:
    """Structured worker result plus persisted command artifacts."""

    result: CommandResultDto
    command_log_artifact: StoredArtifact
    stdout_artifact: StoredArtifact | None = None
    stderr_artifact: StoredArtifact | None = None
    idempotent_replay: bool = False
    timed_out: bool = False
    cancelled: bool = False


@dataclass(frozen=True)
class SupervisedProcessResult:
    """Output returned by the process supervisor."""

    status: CommandStatus
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    cancelled: bool = False
    output_chunks: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CommandRegistry:
    """Registry of safe command definitions."""

    definitions: tuple[CommandDefinition, ...] = (
        CommandDefinition("python-version", "python", ("--version",), ("python.exe", "py", "py.exe")),
        CommandDefinition("python-stream", "python", _LIVE_LOG_FIXTURE_ARGUMENTS, ("python.exe", "py", "py.exe")),
        CommandDefinition("node-version", "node", ("--version",), ("node.exe",)),
        CommandDefinition("node-exec-path", "node", ("-p", "process.execPath"), ("node.exe",)),
        CommandDefinition("npm-version", "npm", ("--version",), ("npm.cmd",)),
        CommandDefinition("npm-registry", "npm", ("config", "get", "registry"), ("npm.cmd",)),
        CommandDefinition("npx-version", "npx", ("--version",), ("npx.cmd",)),
        CommandDefinition("git-version", "git", ("--version",), ("git.exe",)),
        CommandDefinition(_RUNTIME_PROBE_COMMAND_ID, _WILDCARD_EXECUTABLE, ("--version",)),
        *_transformation_command_definitions(),
    )

    def find(self, command_id: str, arguments: tuple[str, ...] | None = None) -> CommandDefinition:
        candidates = [
            definition
            for definition in self.definitions
            if definition.command_id == command_id
        ]
        if not candidates:
            raise CommandPolicyViolation("Command ID is not registered for Sprint 0 execution")
        if arguments is None:
            return candidates[-1]
        # The registry holds multiple immutable shapes of one command_id
        # (e.g. angular-update-exact v1/v2/v3). Bind the request to the shape
        # that matches its concrete arguments; zero or several matches reject.
        matching = [
            definition for definition in candidates if definition.matches_arguments(arguments)
        ]
        if len(matching) != 1:
            raise CommandPolicyViolation(
                "Arguments do not match a registered command definition"
            )
        return matching[0]


@dataclass(frozen=True)
class CommandPolicy:
    """Allowlist, working-directory, runtime, network, and cancellation policy."""

    sandbox_root: Path
    registry: CommandRegistry = field(default_factory=CommandRegistry)
    working_directory_aliases: dict[str, Path] = field(default_factory=dict)
    runtime_profiles: frozenset[str] = frozenset({_DEFAULT_RUNTIME_PROFILE})
    network_profiles: frozenset[str] = frozenset({_DEFAULT_NETWORK_PROFILE})
    environment_allowlist: tuple[str, ...] = ()
    environment_overrides: dict[str, str] = field(default_factory=dict)
    runtime_probe_roots: frozenset[Path] = frozenset()
    runtime_bindings: dict[str, RuntimeExecutableDescriptor] = field(default_factory=dict)

    def __post_init__(self) -> None:
        aliases = {name: Path(path).resolve() for name, path in self.working_directory_aliases.items()}
        if any(name not in _MUTABLE_WORKSPACE_ALIASES and not name.startswith("STAGE_WORKSPACE_") for name in aliases):
            raise CommandPolicyViolation("Only registered mutable workspace aliases may execute commands")
        object.__setattr__(self, "working_directory_aliases", aliases)
        object.__setattr__(self, "runtime_probe_roots", frozenset(Path(path).resolve() for path in self.runtime_probe_roots))

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

        lookup_arguments = tuple(request.arguments)
        normalized_arguments = lookup_arguments
        if request.command_id == "angular-migrate-installed":
            normalized_arguments, lookup_arguments = self._installed_migration_arguments(lookup_arguments)
        definition = self.registry.find(request.command_id, lookup_arguments)
        normalized_request = request.model_copy(update={"arguments": list(normalized_arguments)})
        executable = self._resolve_executable(definition, normalized_request, argument_lookup=lookup_arguments)
        working_directory = self._resolve_working_directory(normalized_request)
        if not working_directory.is_dir():
            raise CommandPolicyViolation("Working directory must exist inside the sandbox root")

        return StructuredCommandRequest(
            dto=normalized_request,
            definition=definition,
            command=(executable, *normalized_arguments),
            working_directory=working_directory,
            environment_allowlist=self.environment_allowlist,
            environment_overrides={**self.environment_overrides, **normalized_request.environment_overrides},
            runtime_bindings=dict(self.runtime_bindings),
        )

    def _resolve_executable(
        self,
        definition: CommandDefinition,
        request: CommandRequestDto,
        *,
        argument_lookup: tuple[str, ...] | None = None,
    ) -> str:
        """Resolve the concrete executable path, fail-closed on descriptor mismatch."""
        if definition.command_id == _RUNTIME_PROBE_COMMAND_ID:
            return self._resolve_runtime_probe(request)
        binding = self._binding_for_executable(request.executable)
        if request.executable not in definition.allowed_executables and binding is None:
            raise CommandPolicyViolation("Executable does not match the registered command definition")
        if binding is not None and binding.kind.value not in definition.allowed_executables:
            raise CommandPolicyViolation("Bound runtime kind does not match the registered command definition")
        if not definition.matches_arguments(argument_lookup or tuple(request.arguments)):
            raise CommandPolicyViolation("Arguments do not match the registered command definition")
        if binding is None:
            return request.executable
        resolved = Path(binding.resolved_path).resolve()
        if not resolved.is_file():
            raise CommandPolicyViolation(
                f"RUNTIME_BINDING_MISSING: bound executable {resolved} is not an existing file"
            )
        actual = self._sha256(resolved)
        if actual != binding.sha256:
            raise CommandPolicyViolation(
                f"RUNTIME_EXECUTABLE_CHECKSUM_MISMATCH: bound {request.executable} resolved to "
                f"{resolved} but its sha256 {actual} does not match the expected {binding.sha256}"
            )
        return str(resolved)

    @staticmethod
    def _installed_migration_arguments(arguments: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if not arguments or arguments[0] not in {_LEGACY_INSTALLED_MIGRATION_HELPER, str(_INSTALLED_MIGRATION_HELPER)}:
            raise CommandPolicyViolation("Installed migration helper must be the Factory-owned asset")
        normalized = (str(_INSTALLED_MIGRATION_HELPER), *arguments[1:])
        return normalized, (_LEGACY_INSTALLED_MIGRATION_HELPER, *arguments[1:])

    def _resolve_runtime_probe(self, request: CommandRequestDto) -> str:
        """PATH-independent probe: executable must be an absolute path under a runtime root."""
        candidate = Path(request.executable)
        if not candidate.is_absolute():
            raise CommandPolicyViolation("Runtime probe executable must be an absolute path")
        if not self.runtime_probe_roots:
            raise CommandPolicyViolation("Runtime probe roots are not configured")
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise CommandPolicyViolation("Runtime probe executable is not available") from exc
        if not any(self._within_root(resolved, root) for root in self.runtime_probe_roots):
            raise CommandPolicyViolation("Runtime probe executable is outside the configured runtime roots")
        return str(resolved)

    @staticmethod
    def _within_root(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _binding_for_executable(self, executable: str) -> RuntimeExecutableDescriptor | None:
        kind = _executable_kind(executable)
        if kind is None or not self.runtime_bindings:
            return None
        return self.runtime_bindings.get(kind.value)

    @staticmethod
    def _sha256(path: Path) -> str:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _resolve_working_directory(self, request: CommandRequestDto) -> Path:
        if request.working_directory_alias:
            if request.working_directory:
                raise CommandPolicyViolation("Working directory path cannot override an approved alias")
            if request.working_directory_alias not in self.working_directory_aliases:
                raise CommandPolicyViolation("Working directory alias is not registered")
            candidate = self.working_directory_aliases[request.working_directory_alias]
        elif request.working_directory:
            raw_path = Path(request.working_directory)
            if ".." in raw_path.parts:
                raise CommandPolicyViolation("Working directory traversal is forbidden")
            if not raw_path.is_absolute() and raw_path.drive:
                raise CommandPolicyViolation("Working directory drive changes are forbidden")
            candidate = raw_path if raw_path.is_absolute() else self.sandbox_root / raw_path
        else:
            raise CommandPolicyViolation("Working directory alias is required")

        sandbox_root = self.sandbox_root.resolve(strict=True)
        try:
            resolved = Path(candidate).resolve(strict=True)
        except FileNotFoundError as exc:
            raise CommandPolicyViolation("Working directory is not available") from exc
        try:
            resolved.relative_to(sandbox_root)
        except ValueError as exc:
            raise CommandPolicyViolation("Working directory must stay inside the sandbox root") from exc
        return resolved


class CommandLogWriter:
    """Persist command execution records and bounded output artifacts."""

    def __init__(
        self, artifact_store: LocalFilesystemArtifactStore, *, max_output_bytes: int | None = 1_000_000
    ) -> None:
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

        stdout_artifact = self._write_output_artifact(request, result, "stdout", stdout_text, truncated=stdout_truncated)
        stderr_artifact = self._write_output_artifact(request, result, "stderr", stderr_text, truncated=stderr_truncated)
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
            timed_out=timed_out,
            cancelled=cancelled,
        )

    def _write_output_artifact(
        self,
        request: CommandRequestDto,
        result: CommandResultDto,
        stream_name: str,
        content: str,
        *,
        truncated: bool = False,
    ) -> StoredArtifact | None:
        return self._artifact_store.write_text_artifact(
            result.run_id,
            f"04_workflow_state/command_logs/{result.command_id}.{stream_name}.log",
            content,
            ArtifactType.TEXT_LOG,
            stage_id=result.stage_id,
            created_by="command-execution-worker",
            created_at=result.finished_at or result.started_at,
            input_hashes={"command_id": request.command_id, **({"truncated": "true"} if truncated else {})},
        )

    def _bound_text(self, value: str | bytes | None) -> tuple[str, bool]:
        if value is None:
            return "", False
        text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
        text = redact_prompt_text(text).redacted_text
        payload = text.encode("utf-8")
        if self._max_output_bytes is None or len(payload) <= self._max_output_bytes:
            return text, False
        bounded = payload[: self._max_output_bytes].decode("utf-8", errors="replace")
        return bounded + "\n[command output truncated]", True


class WorkerSupervisor:
    """Run approved processes with shell disabled and process-tree termination."""

    _SECRET_PATTERNS: tuple[str, ...] = (
        "TOKEN", "SECRET", "KEY", "PASSWORD", "CREDENTIAL",
        "HERMES_", "API_KEY", "ACCESS_KEY", "PRIVATE_KEY",
    )

    def __init__(self) -> None:
        self._jobs: dict[int, _WindowsJobObject] = {}
        self._jobs_lock = threading.Lock()

    @staticmethod
    def _build_safe_environment(allowlist: tuple[str, ...] = (), overrides: dict[str, str] | None = None) -> dict[str, str]:
        """Build a sanitized environment blocking secret and backend variables.

        Least privilege (F27-02): an empty allowlist forwards nothing from the
        ambient environment except the minimal PATH needed to resolve approved
        executables.  Explicit allowlists grant exactly the listed variables.
        """
        clean: dict[str, str] = {}
        effective = set(allowlist)
        if not effective:
            effective = {"PATH"}
        if os.name == "nt":
            effective.add("SYSTEMROOT")
        for var, value in os.environ.items():
            upper = var.upper()
            blocked = any(pattern in upper for pattern in WorkerSupervisor._SECRET_PATTERNS)
            if not blocked and var in effective:
                clean[var] = value
        for var, value in (overrides or {}).items():
            upper = var.upper()
            if any(pattern in upper for pattern in WorkerSupervisor._SECRET_PATTERNS):
                continue
            clean[var] = value
        return clean

    def run(
        self,
        request: StructuredCommandRequest,
        *,
        cancel_event: threading.Event | None = None,
        output_callback=None,
        process_started_callback=None,
    ) -> SupervisedProcessResult:
        command = list(self._verify_bound_executable(request))
        creationflags = 0
        popen_kwargs: dict[str, object] = {}
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True
        if os.name == "nt":
            resolved_executable = (
                sys.executable
                if command[0].lower() in {"python", "python.exe"}
                else shutil.which(command[0])
            )
            if resolved_executable:
                command[0] = resolved_executable
        process = subprocess.Popen(
            command,
            cwd=request.working_directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if request.stdin_text is not None else subprocess.DEVNULL,
            text=False,
            shell=False,
            env=self._build_safe_environment(request.environment_allowlist, request.environment_overrides),
            creationflags=creationflags,
            **popen_kwargs,
        )
        if request.stdin_text is not None and process.stdin is not None:
            process.stdin.write(request.stdin_text.encode("utf-8"))
            process.stdin.close()
        if os.name == "nt":
            try:
                job = _WindowsJobObject(process)
            except Exception:
                process.kill()
                process.wait()
                raise
            with self._jobs_lock:
                self._jobs[process.pid] = job
        if process_started_callback is not None:
            try:
                process_started_callback(process.pid)
            except Exception:
                self.terminate_process_tree(process)
                raise
        chunks: list[tuple[str, str]] = []
        output_queue: queue.Queue[tuple[str, str] | None] = queue.Queue()

        def read_stream(name: str, stream) -> None:
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            while True:
                raw = stream.read(4096)
                if not raw:
                    break
                text = decoder.decode(raw, final=False)
                if text:
                    item = (name, text)
                    chunks.append(item)
                    output_queue.put(item)
            tail = decoder.decode(b"", final=True)
            if tail:
                item = (name, tail)
                chunks.append(item)
                output_queue.put(item)
            output_queue.put(None)

        threads = [
            threading.Thread(target=read_stream, args=(name, stream), daemon=True)
            for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))
        ]
        for thread in threads:
            thread.start()
        deadline = monotonic() + request.dto.timeout_seconds
        completed_streams = 0
        timed_out = False
        cancelled = False
        while completed_streams < 2:
            if cancel_event is not None and cancel_event.is_set() and process.poll() is None:
                cancelled = True
                self.terminate_process_tree(process)
            if monotonic() >= deadline and process.poll() is None:
                timed_out = True
                cancelled = True
                self.terminate_process_tree(process)
            try:
                item = output_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            if item is None:
                completed_streams += 1
            elif output_callback is not None:
                output_callback(item[0], item[1])
        process.wait()
        for thread in threads:
            thread.join(timeout=1)
        stdout = "".join(value for name, value in chunks if name == "stdout")
        stderr = "".join(value for name, value in chunks if name == "stderr")
        if os.name == "nt":
            with self._jobs_lock:
                job = self._jobs.pop(process.pid, None)
            if job is not None:
                job.close()
        status = (
            CommandStatus.CANCELLED
            if cancelled
            else CommandStatus.SUCCEEDED
            if process.returncode == 0
            else CommandStatus.FAILED
        )
        return SupervisedProcessResult(
            status=status,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            cancelled=cancelled,
            output_chunks=tuple(chunks),
        )

    def terminate_process_tree(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            with self._jobs_lock:
                job = self._jobs.get(process.pid)
            if job is not None:
                job.terminate()
                process.wait(timeout=2)
                return
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

    def _verify_bound_executable(self, request: StructuredCommandRequest) -> tuple[str, ...]:
        """Fail-closed at the process boundary: a bound runtime must be exactly the executed path.

        Defensive against a change between policy validation and process launch; the
        authoritative guard lives in ``CommandPolicy.validate``.
        """
        if not request.runtime_bindings:
            return request.command
        kind = _executable_kind(request.command[0])
        binding = request.runtime_bindings.get(kind.value) if kind is not None else None
        if binding is None:
            return request.command
        command_path = Path(request.command[0])
        bound_path = Path(binding.resolved_path).resolve()
        if command_path.resolve() != bound_path:
            raise OSError(
                f"RUNTIME_BINDING_PATH_MISMATCH: command executable {request.command[0]} does not match "
                f"the bound runtime path {bound_path}"
            )
        import hashlib

        digest = hashlib.sha256()
        with bound_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        if digest.hexdigest() != binding.sha256:
            raise OSError(
                f"RUNTIME_EXECUTABLE_CHECKSUM_MISMATCH: bound {bound_path} checksum does not match "
                f"the expected {binding.sha256}"
            )
        return request.command


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

    def run(
        self,
        request: CommandRequestDto,
        *,
        cancel_event: threading.Event | None = None,
        output_callback=None,
        process_started_callback=None,
        stdin_text: str | None = None,
    ) -> CommandExecutionResult:
        replay = self._find_idempotent_result(request)
        if replay is not None:
            return CommandExecutionResult(
                result=replay.result,
                command_log_artifact=replay.command_log_artifact,
                stdout_artifact=replay.stdout_artifact,
                stderr_artifact=replay.stderr_artifact,
                idempotent_replay=True,
                timed_out=replay.timed_out,
                cancelled=replay.cancelled,
            )

        started_at = datetime.now(UTC)
        start_time = monotonic()
        normalized_request = self._apply_default_timeout(request)
        fallback_working_directory = self._policy.sandbox_root.resolve()
        command = (normalized_request.executable, *normalized_request.arguments)

        try:
            structured_request = self._policy.validate(normalized_request)
            if stdin_text is not None:
                structured_request = replace(structured_request, stdin_text=stdin_text)
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

        try:
            supervisor_kwargs = {
                "cancel_event": cancel_event,
                "output_callback": output_callback,
            }
            if process_started_callback is not None:
                supervisor_kwargs["process_started_callback"] = process_started_callback
            supervised = self._supervisor.run(
                structured_request,
                **supervisor_kwargs,
            )
        except OSError as exc:
            execution = self._record(
                normalized_request,
                CommandStatus.FAILED,
                started_at,
                start_time,
                command=structured_request.command,
                working_directory=structured_request.working_directory,
                stdout="",
                stderr=f"Unable to start approved command: {exc}",
                exit_code=None,
            )
            self._remember_idempotent_result(normalized_request, execution)
            return execution
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
