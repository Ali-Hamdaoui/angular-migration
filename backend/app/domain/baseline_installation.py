"""Deterministic rules for the S1-F11 frozen baseline installation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.command_execution.worker import CommandExecutionResult, ExecutionWorker
from app.domain.contracts import CancellationPolicy, CommandRequestDto, CommandStatus


class BaselineInstallationError(ValueError):
    """Raised when frozen-install prerequisites or evidence are invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BaselineInstallPrerequisites:
    g02_approved: bool
    execution_profile_selected: bool
    baseline_workspace_ready: bool
    install_authorized: bool
    lockfile_valid: bool

    def validate(self) -> None:
        checks = (
            ("BASELINE_G02_REQUIRED", self.g02_approved),
            ("EXECUTION_PROFILE_REQUIRED", self.execution_profile_selected),
            ("BASELINE_WORKSPACE_REQUIRED", self.baseline_workspace_ready),
            ("BASELINE_INSTALL_AUTHORIZATION_REQUIRED", self.install_authorized),
            ("BASELINE_LOCKFILE_REQUIRED", self.lockfile_valid),
        )
        for code, valid in checks:
            if not valid:
                raise BaselineInstallationError(code, f"{code} prerequisite is not satisfied.")

@dataclass(frozen=True)
class FrozenBaselineCommand:
    command_id: str
    executable: str
    arguments: tuple[str, ...]
    shell: bool
    working_directory_alias: str
    network_profile: str
    recovery_category: str

    def request(self, *, run_id: str, runtime_profile_id: str, timeout_seconds: int, idempotency_key: str, actor: str, requested_at: datetime) -> CommandRequestDto:
        return CommandRequestDto(
            command_id=self.command_id, run_id=run_id, requested_by=actor,
            requester=actor, executable=self.executable, arguments=list(self.arguments),
            shell=self.shell, working_directory_alias=self.working_directory_alias,
            runtime_profile_id=runtime_profile_id, timeout_seconds=timeout_seconds,
            network_profile=self.network_profile,
            cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
            idempotency_key=idempotency_key, requested_at=requested_at,
        )


class FrozenBaselineCommandPolicy:
    """Create the only permitted baseline installation command."""

    COMMAND_ID = "npm-ci-bootstrap"
    POLICY_VERSION = "baseline-install-v1"

    def __init__(self, executable: str = "npm") -> None:
        self.executable = executable

    def create(self) -> FrozenBaselineCommand:
        return FrozenBaselineCommand(
            command_id=self.COMMAND_ID, executable=self.executable, arguments=("ci",), shell=False,
            working_directory_alias="BASELINE_SANDBOX",
            network_profile="approved-registries-only",
            recovery_category="reconstruct-baseline-sandbox",
        )


@dataclass(frozen=True)
class FileFingerprint:
    path: str
    checksum: str
    present: bool


@dataclass(frozen=True)
class DependencyTreeVerification:
    status: str
    package_count: int
    checksum: str
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class BaselineInstallationInspection:
    status: str
    package_json: FileFingerprint
    lockfile: FileFingerprint
    dependency_tree: DependencyTreeVerification | None
    reconstruction_required: bool
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class BaselineInstallationExecution:
    command: CommandExecutionResult
    inspection: "BaselineInstallationInspection"


class BaselineInstallationService:
    """Authorize, execute, and inspect one frozen baseline npm ci command."""

    def __init__(self, worker: ExecutionWorker, *, command_policy: FrozenBaselineCommandPolicy | None = None, inspection: "FrozenBaselineInspectionService" | None = None) -> None:
        self._worker = worker
        self._command_policy = command_policy or FrozenBaselineCommandPolicy()
        self._inspection = inspection or FrozenBaselineInspectionService()

    def execute(self, request: CommandRequestDto, *, sandbox: Path, prerequisites: BaselineInstallPrerequisites, cancel_event=None, output_callback=None) -> BaselineInstallationExecution:
        prerequisites.validate()
        command = self._command_policy.create()
        if (
            request.command_id != command.command_id
            or request.executable != command.executable
            or tuple(request.arguments) != command.arguments
            or request.shell is not False
            or request.working_directory_alias != command.working_directory_alias
            or request.network_profile != command.network_profile
        ):
            raise BaselineInstallationError("BASELINE_COMMAND_NOT_FROZEN", "Only the exact npm ci baseline command is permitted.")
        before_package_json, before_lockfile = self._inspection.inspect_before(sandbox)
        execution = self._worker.run(request, cancel_event=cancel_event, output_callback=output_callback)
        inspection = self._inspection.inspect_after(sandbox, before_package_json=before_package_json, before_lockfile=before_lockfile, command_status=execution.result.status)
        return BaselineInstallationExecution(execution, inspection)

class FrozenBaselineInspectionService:
    """Verify immutable package inputs and the npm-generated dependency tree."""

    def inspect_before(self, sandbox: Path) -> tuple[FileFingerprint, FileFingerprint]:
        return self._fingerprint(sandbox / "package.json"), self._lockfile_fingerprint(sandbox)

    def inspect_after(self, sandbox: Path, *, before_package_json: FileFingerprint, before_lockfile: FileFingerprint, command_status: CommandStatus) -> BaselineInstallationInspection:
        package_json = self._fingerprint(sandbox / "package.json")
        lockfile = self._fingerprint(Path(before_lockfile.path))
        blockers: list[str] = []
        if package_json != before_package_json:
            blockers.append("PACKAGE_JSON_CHANGED_AFTER_INSTALL")
        if lockfile != before_lockfile:
            blockers.append("PACKAGE_LOCK_CHANGED_AFTER_INSTALL")
        dependency_tree = None
        if command_status is CommandStatus.SUCCEEDED and not blockers:
            dependency_tree = self._dependency_tree(sandbox)
            blockers.extend(dependency_tree.blockers)
        interrupted = command_status is not CommandStatus.SUCCEEDED
        return BaselineInstallationInspection(
            status="succeeded" if command_status is CommandStatus.SUCCEEDED and not blockers else "blocked" if blockers else command_status.value.lower(),
            package_json=package_json, lockfile=lockfile, dependency_tree=dependency_tree,
            reconstruction_required=interrupted or bool(blockers),
            blockers=tuple(dict.fromkeys(blockers)),
        )

    @staticmethod
    def _fingerprint(path: Path) -> FileFingerprint:
        if not path.is_file():
            return FileFingerprint(str(path), "", False)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return FileFingerprint(str(path), f"sha256:{digest}", True)

    @staticmethod
    def _lockfile_fingerprint(sandbox: Path) -> FileFingerprint:
        for name in ("package-lock.json", "npm-shrinkwrap.json"):
            candidate = sandbox / name
            if candidate.is_file():
                return FrozenBaselineInspectionService._fingerprint(candidate)
        return FrozenBaselineInspectionService._fingerprint(sandbox / "package-lock.json")

    def _dependency_tree(self, sandbox: Path) -> DependencyTreeVerification:
        path = sandbox / "node_modules" / ".package-lock.json"
        if not path.is_file():
            return DependencyTreeVerification("blocked", 0, "", ("DEPENDENCY_TREE_MISSING",))
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return DependencyTreeVerification("blocked", 0, "", ("DEPENDENCY_TREE_INVALID",))
        packages = payload.get("packages") if isinstance(payload, dict) else None
        if not isinstance(packages, dict):
            return DependencyTreeVerification("blocked", 0, "", ("DEPENDENCY_TREE_INVALID",))
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        return DependencyTreeVerification("verified", max(0, len(packages) - (1 if "" in packages else 0)), f"sha256:{checksum}")
