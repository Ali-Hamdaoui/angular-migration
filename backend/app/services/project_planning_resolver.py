"""Resolve executable planning facts from the checked-out workspace evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.workspace_configuration_reader import WorkspaceConfigurationError, WorkspaceConfigurationReader


class ProjectPlanningResolutionError(ValueError):
    def __init__(self, code: str, *, cause: Exception | None = None) -> None:
        self.code = code
        self.cause = cause
        self.details = cause
        super().__init__(code)


class ResolvedTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    project: str
    target: str
    builder: str
    configuration: str | None = None


class ResolvedPlanningInputs(BaseModel):
    model_config = ConfigDict(frozen=True)

    package_manager: str
    scripts: dict[str, str] = Field(default_factory=dict)
    build_targets: tuple[ResolvedTarget, ...] = ()
    test_targets: tuple[ResolvedTarget, ...] = ()
    lint_targets: tuple[ResolvedTarget, ...] = ()
    findings: tuple[str, ...] = ()

    def select_build_target(self, *, project_name: str | None = None, target_name: str | None = None) -> ResolvedTarget:
        candidates = list(self.build_targets)
        if project_name is not None:
            candidates = [item for item in candidates if item.project == project_name]
        if target_name is not None:
            candidates = [item for item in candidates if item.target == target_name]
        if not candidates:
            raise ProjectPlanningResolutionError("ANGULAR_PROJECT_INVALID")
        application_candidates = [item for item in candidates if item.kind in {"application", "browser", "ssr"}]
        if project_name is None and len(application_candidates) == 1:
            return application_candidates[0]
        if len(candidates) == 1:
            return candidates[0]
        raise ProjectPlanningResolutionError("AMBIGUOUS_ANGULAR_PROJECT_SELECTION")


class ProjectPlanningResolver:
    """Read only resolver; it never writes or mutates the supplied workspace."""

    def resolve(self, workspace: Path) -> ResolvedPlanningInputs:
        workspace = Path(workspace)
        reader = WorkspaceConfigurationReader()
        package_path = workspace / "package.json"
        if not package_path.is_file():
            raise ProjectPlanningResolutionError("PACKAGE_JSON_NOT_FOUND")
        try:
            package = reader.read_json_object(package_path, logical_name="package.json").value
        except WorkspaceConfigurationError as error:
            raise ProjectPlanningResolutionError(f"PACKAGE_JSON_{error.code.removeprefix('WORKSPACE_JSON_')}", cause=error) from error

        lockfiles = {
            "package-lock.json": "npm",
            "npm-shrinkwrap.json": "npm",
            "pnpm-lock.yaml": "pnpm",
            "yarn.lock": "yarn",
        }
        selected = next((manager for filename, manager in lockfiles.items() if (workspace / filename).is_file()), None)
        if selected != "npm":
            raise ProjectPlanningResolutionError("UNSUPPORTED_PACKAGE_MANAGER")

        angular_path = workspace / "angular.json"
        try:
            angular = reader.read_json_object(angular_path, logical_name="angular.json").value
        except WorkspaceConfigurationError as error:
            raise ProjectPlanningResolutionError(error.code, cause=error) from error

        projects = angular.get("projects")
        if not isinstance(projects, dict):
            raise ProjectPlanningResolutionError("ANGULAR_PROJECTS_INVALID")

        builds: list[ResolvedTarget] = []
        tests: list[ResolvedTarget] = []
        lints: list[ResolvedTarget] = []
        findings: list[str] = []
        for project, config in projects.items():
            if not isinstance(config, dict):
                raise ProjectPlanningResolutionError("ANGULAR_PROJECT_INVALID")
            project_type = config.get("projectType") or "application"
            if project_type not in {"application", "library"}:
                raise ProjectPlanningResolutionError("ANGULAR_PROJECT_INVALID")
            architect = config.get("architect")
            targets_value = config.get("targets")
            if architect is not None and not isinstance(architect, dict):
                raise ProjectPlanningResolutionError("ANGULAR_TARGET_INVALID")
            if targets_value is not None and not isinstance(targets_value, dict):
                raise ProjectPlanningResolutionError("ANGULAR_TARGET_INVALID")
            targets = targets_value if targets_value is not None else architect if architect is not None else {}
            for target_name, target in targets.items():
                if not isinstance(target, dict):
                    raise ProjectPlanningResolutionError("ANGULAR_TARGET_INVALID")
                builder = target.get("builder")
                if not isinstance(builder, str) or not builder.strip():
                    raise ProjectPlanningResolutionError("ANGULAR_TARGET_INVALID")
                options = target.get("options")
                configurations = target.get("configurations")
                if options is not None and not isinstance(options, dict):
                    raise ProjectPlanningResolutionError("ANGULAR_TARGET_INVALID")
                if configurations is not None and not isinstance(configurations, dict):
                    raise ProjectPlanningResolutionError("ANGULAR_TARGET_INVALID")
                kind = self._kind(project_type, target_name, builder)
                configuration = "production" if target_name == "build" and configurations and "production" in configurations else None
                resolved = ResolvedTarget(kind=kind, project=str(project), target=str(target_name), builder=builder, configuration=configuration)
                if target_name == "build":
                    builds.append(resolved)
                    if configuration is None:
                        findings.append(f"PRODUCTION_CONFIGURATION_NOT_CONFIGURED:{project}")
                elif target_name == "test":
                    tests.append(resolved)
                elif target_name == "lint":
                    lints.append(resolved)

        if not builds:
            findings.append("BUILD_NOT_CONFIGURED")
        if not tests:
            findings.append("TEST_NOT_CONFIGURED")
        if not lints:
            findings.append("LINT_NOT_CONFIGURED")
        return ResolvedPlanningInputs(
            package_manager=selected,
            scripts={str(key): str(value) for key, value in (package.get("scripts") or {}).items()},
            build_targets=tuple(builds),
            test_targets=tuple(tests),
            lint_targets=tuple(lints),
            findings=tuple(dict.fromkeys(findings)),
        )

    @staticmethod
    def _kind(project_type: str, target: str, builder: str) -> str:
        if project_type == "library" or "ng-packagr" in builder:
            return "library"
        if target == "server" or ":server" in builder or ":ssr" in builder:
            return "ssr"
        if ":browser" in builder:
            return "browser"
        if ":application" in builder:
            return "application"
        return "custom"
