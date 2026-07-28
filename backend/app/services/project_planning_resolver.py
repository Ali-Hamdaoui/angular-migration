"""Resolve executable planning facts from the checked-out workspace evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectPlanningResolutionError(ValueError):
    pass


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


class ProjectPlanningResolver:
    """Read only resolver; it never writes or mutates the supplied workspace."""

    def resolve(self, workspace: Path) -> ResolvedPlanningInputs:
        workspace = Path(workspace)
        package_path = workspace / "package.json"
        if not package_path.is_file():
            raise ProjectPlanningResolutionError("PACKAGE_JSON_NOT_FOUND")
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ProjectPlanningResolutionError("PACKAGE_JSON_INVALID") from error

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
        if not angular_path.is_file():
            raise ProjectPlanningResolutionError("ANGULAR_JSON_NOT_FOUND")
        try:
            angular = json.loads(angular_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ProjectPlanningResolutionError("ANGULAR_JSON_INVALID") from error

        builds: list[ResolvedTarget] = []
        tests: list[ResolvedTarget] = []
        lints: list[ResolvedTarget] = []
        findings: list[str] = []
        for project, config in (angular.get("projects") or {}).items():
            project_type = str(config.get("projectType") or "application")
            targets = config.get("targets") or config.get("architect") or {}
            for target_name, target in targets.items():
                builder = str((target or {}).get("builder") or "")
                if not builder:
                    continue
                kind = self._kind(project_type, target_name, builder)
                configuration = "production" if target_name == "build" and "production" in ((target or {}).get("configurations") or {}) else None
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
