"""Deterministic discovery and result rules for S1-F12 baseline validation.

This module does not mutate the source workspace or invent validation targets.
It turns the already-installed project metadata into registered, structured
target descriptions and normalizes executor outcomes for the later persistence
and API slices.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from app.services.workspace_configuration_reader import WorkspaceConfigurationError, WorkspaceConfigurationReader


class BaselineMatrixError(ValueError):
    """Raised when baseline metadata cannot be safely inspected."""


class BaselineTargetKind(str, Enum):
    BUILD = "build"
    TEST = "test"
    LINT = "lint"


class BaselineTargetStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED_NOT_CONFIGURED = "skipped_not_configured"
    SKIPPED_NOT_APPLICABLE = "skipped_not_applicable"
    BLOCKED = "blocked"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class BaselineTarget:
    target_id: str
    kind: BaselineTargetKind
    project: str | None
    configuration: str | None
    command_id: str
    executable: str
    arguments: tuple[str, ...]
    working_directory_alias: str = "BASELINE_SANDBOX"
    supported: bool = True
    blocker: str | None = None
    builder: str | None = None
    canonical_target_id: str | None = None
    support_reason: str | None = None


@dataclass(frozen=True)
class BaselineTargetInventory:
    targets: tuple[BaselineTarget, ...]
    package_json_checksum: str
    angular_json_present: bool


@dataclass(frozen=True)
class BaselineTargetResult:
    target_id: str
    kind: BaselineTargetKind
    status: BaselineTargetStatus
    exit_code: int | None = None
    duration_ms: int | None = None
    warnings: tuple[str, ...] = ()
    test_count: int | None = None
    failed_tests: tuple[str, ...] = ()
    output_location: str | None = None
    artifact_ids: tuple[str, ...] = ()
    blocker: str | None = None


class BaselineTargetDiscoveryService:
    """Discover only configured Angular targets and approved package scripts."""

    def discover(self, sandbox: Path) -> BaselineTargetInventory:
        package_path = sandbox / "package.json"
        if not package_path.is_file():
            raise BaselineMatrixError("PACKAGE_JSON_MISSING")
        try:
            package = WorkspaceConfigurationReader().read_json_object(package_path, logical_name="package.json").value
        except WorkspaceConfigurationError as error:
            raise BaselineMatrixError("PACKAGE_JSON_INVALID") from error
        if not isinstance(package, dict):
            raise BaselineMatrixError("PACKAGE_JSON_INVALID")

        angular = self._read_optional_json(sandbox / "angular.json")
        targets: list[BaselineTarget] = []
        if angular is not None:
            projects = angular.get("projects", {})
            if not isinstance(projects, dict):
                raise BaselineMatrixError("ANGULAR_PROJECTS_INVALID")
            for project_name in sorted(projects):
                project = projects[project_name]
                if not isinstance(project, dict):
                    continue
                configured = project.get("architect", project.get("targets", {}))
                if not isinstance(configured, dict):
                    continue
                for kind in BaselineTargetKind:
                    definition = configured.get(kind.value)
                    if isinstance(definition, dict):
                        targets.extend(self._angular_targets(project_name, kind, definition, scripts=package.get("scripts", {})))

        scripts = package.get("scripts", {})
        if not isinstance(scripts, dict):
            raise BaselineMatrixError("PACKAGE_SCRIPTS_INVALID")
        for kind in BaselineTargetKind:
            script_name = kind.value
            script = scripts.get(script_name)
            if isinstance(script, str) and script.strip():
                target_id = f"script:{script_name}"
                if not any(item.target_id == target_id for item in targets):
                    targets.append(BaselineTarget(target_id, kind, None, None, target_id.replace(":", "__"), "npm", ("run", script_name)))

        # Keep the matrix honest: absent test/lint configuration is represented
        # explicitly and never interpreted as a successful command.
        for kind in (BaselineTargetKind.TEST, BaselineTargetKind.LINT):
            if not any(item.kind is kind for item in targets):
                targets.append(BaselineTarget(f"not-configured:{kind.value}", kind, None, None, "", "", (), supported=False, blocker="NOT_CONFIGURED"))
        return BaselineTargetInventory(tuple(targets), _checksum(package_path), angular is not None)

    def _angular_targets(self, project: str, kind: BaselineTargetKind, definition: dict[str, Any], *, scripts: Any) -> Iterable[BaselineTarget]:
        builder = definition.get("builder")
        configurations = definition.get("configurations", {})
        if not isinstance(configurations, dict):
            configurations = {}
        selected = ["production"] if "production" in configurations else [None]
        if not selected:
            selected = [None]
        for configuration in selected:
            suffix = f":{configuration}" if configuration else ""
            target_id = f"angular:{project}:{kind.value}{suffix}"
            if kind is BaselineTargetKind.TEST and self._jest_alias(builder, scripts, definition):
                yield BaselineTarget(target_id, kind, project, configuration, target_id.replace(":", "__"), "", (), supported=False, blocker="EQUIVALENT_CANONICAL_TARGET", builder=builder, canonical_target_id="script:test", support_reason="Approved @angular-builders/jest:run target is equivalent to the root npm test script; the canonical script:test execution is reused.")
                continue
            if not isinstance(builder, str) or not self._supported_builder(kind, builder):
                yield BaselineTarget(target_id, kind, project, configuration, target_id.replace(":", "__"), "", (), supported=False, blocker="UNSUPPORTED_CUSTOM_TARGET", builder=builder if isinstance(builder, str) else None)
                continue
            arguments = ["ng", kind.value, project]
            if configuration:
                arguments.extend(("--configuration", configuration))
            yield BaselineTarget(target_id, kind, project, configuration, target_id.replace(":", "__"), "npx", tuple(arguments), builder=builder)

    @staticmethod
    def _jest_alias(builder: Any, scripts: Any, definition: dict[str, Any]) -> bool:
        """Recognize only the governed Jest builder/script equivalence."""
        if builder != "@angular-builders/jest:run" or not isinstance(scripts, dict):
            return False
        command = scripts.get("test")
        if not isinstance(command, str) or not command.strip():
            return False
        tokens = command.strip().split()
        if not tokens or tokens[0].lower() not in {"jest", "jest.cmd"}:
            return False
        options = definition.get("options", {})
        return not options or isinstance(options, dict) and not any(key in options for key in ("config", "jestConfig", "runInBand", "watch", "coverage"))

    @staticmethod
    def _supported_builder(kind: BaselineTargetKind, builder: str) -> bool:
        return builder.startswith("@angular-devkit/build-angular:") and builder.rsplit(":", 1)[-1] in {
            "browser", "browser-esbuild", "application", "dev-server", "karma", "tslint", "ng-packagr",
        } or kind is BaselineTargetKind.LINT and builder.endswith(":lint")

    @staticmethod
    def _read_optional_json(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            return WorkspaceConfigurationReader().read_json_object(path, logical_name="angular.json").value
        except WorkspaceConfigurationError as error:
            raise BaselineMatrixError(error.code) from error


def normalize_command_result(target: BaselineTarget, *, exit_code: int | None, duration_ms: int | None, cancelled: bool = False, interrupted: bool = False, warnings: Iterable[str] = (), test_count: int | None = None, failed_tests: Iterable[str] = ()) -> BaselineTargetResult:
    if not target.supported:
        status = BaselineTargetStatus.SKIPPED_NOT_CONFIGURED if target.blocker == "NOT_CONFIGURED" else BaselineTargetStatus.SKIPPED_NOT_APPLICABLE if target.blocker == "EQUIVALENT_CANONICAL_TARGET" else BaselineTargetStatus.BLOCKED
    elif cancelled:
        status = BaselineTargetStatus.CANCELLED
    elif interrupted:
        status = BaselineTargetStatus.INTERRUPTED
    elif exit_code == 0:
        status = BaselineTargetStatus.PASSED
    else:
        status = BaselineTargetStatus.FAILED
    return BaselineTargetResult(target.target_id, target.kind, status, exit_code, duration_ms, tuple(warnings), test_count, tuple(failed_tests), blocker=target.blocker)


def _checksum(path: Path) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
