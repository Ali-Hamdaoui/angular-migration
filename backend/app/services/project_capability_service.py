"""Project capability derivation and snapshot persistence (V2 F13)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.domain.project_capability import ProjectCapability, ProjectCapabilitySnapshot
from app.repositories.models import MigrationRunModel, ProjectCapabilityModel
from app.repositories.session import session_scope


class ProjectCapabilityError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_ANGULAR_MAJOR = re.compile(r"@angular/core[^\n]*(\d+)\.\d+\.\d+")


class ProjectCapabilityService:
    """Deterministically derive project capabilities and persist snapshots."""

    def __init__(
        self,
        *,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def derive(self, source_root: Path) -> list[ProjectCapability]:
        """Inspect a project root and derive deterministic capability facts."""
        capabilities: list[ProjectCapability] = []

        package_json = source_root / "package.json"
        angular_json = source_root / "angular.json"
        tsconfig = source_root / "tsconfig.json"

        if not package_json.is_file():
            capabilities.append(ProjectCapability(key="package_json", value="missing", detail="no package.json found"))
            return capabilities
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            capabilities.append(ProjectCapability(key="package_json", value="invalid", detail="package.json is not valid JSON"))
            return capabilities

        angular_version = _package_version(package, "@angular/core")
        cli_version = _package_version(package, "@angular/cli")
        typescript_version = _package_version(package, "typescript")
        rxjs_version = _package_version(package, "rxjs")
        zone_js_version = _package_version(package, "zone.js")
        package_manager = _package_manager(package)

        capabilities.extend(
            [
                ProjectCapability(key="angular_core", value=angular_version or "absent", detail="resolved @angular/core version"),
                ProjectCapability(key="angular_cli", value=cli_version or "absent", detail="resolved @angular/cli version"),
                ProjectCapability(key="typescript", value=typescript_version or "absent", detail="resolved typescript version"),
                ProjectCapability(key="rxjs", value=rxjs_version or "absent", detail="resolved rxjs version"),
                ProjectCapability(key="zone_js", value=zone_js_version or "absent", detail="resolved zone.js version"),
                ProjectCapability(key="package_manager", value=package_manager, detail="detected package manager"),
            ]
        )

        workspace = "single_application" if angular_json.is_file() else "not_angular_cli"
        capabilities.append(ProjectCapability(key="workspace_type", value=workspace, detail="angular.json presence"))
        capabilities.append(ProjectCapability(key="tsconfig", value="present" if tsconfig.is_file() else "absent", detail="tsconfig.json presence"))
        capabilities.append(ProjectCapability(key="node_modules", value="present" if (source_root / "node_modules").is_dir() else "absent", detail="node_modules presence"))
        capabilities.append(
            ProjectCapability(
                key="lockfile", value=_lockfile(source_root), detail="package-lock.json / yarn.lock / pnpm-lock.yaml presence"
            )
        )

        scripts = package.get("scripts", {}) if isinstance(package.get("scripts", {}), dict) else {}
        capabilities.append(ProjectCapability(key="build_script", value="present" if scripts.get("build") else "absent", detail="build script presence"))
        capabilities.append(ProjectCapability(key="test_script", value="present" if scripts.get("test") else "absent", detail="test script presence"))
        return capabilities

    def snapshot(self, run_id: str, source_root: Path, stage_id: str | None = None) -> ProjectCapabilitySnapshot:
        """Derive and persist an immutable capability snapshot for a run/stage."""
        capabilities = self.derive(source_root)
        angular_major = _angular_major_from(capabilities)
        snapshot = ProjectCapabilitySnapshot(
            run_id=run_id,
            stage_id=stage_id,
            source_root=str(source_root),
            angular_major=angular_major,
            capabilities=tuple(capabilities),
        ).bind_checksum()
        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise ProjectCapabilityError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            existing = session.scalar(
                select(ProjectCapabilityModel).where(
                    ProjectCapabilityModel.run_id == run_id,
                    ProjectCapabilityModel.checksum == snapshot.checksum,
                )
            )
            if existing is not None:
                return snapshot
            session.add(
                ProjectCapabilityModel(
                    id="cap-" + hashlib_short(run_id, snapshot.checksum),
                    run_id=run_id,
                    stage_id=stage_id,
                    source_root=str(source_root),
                    angular_major=angular_major,
                    capabilities=[c.model_dump(mode="json") for c in capabilities],
                    checksum=snapshot.checksum,
                    created_at=self._now_provider(),
                )
            )
            session.commit()
        return snapshot

    def readiness(self, capabilities: list) -> tuple[str, list[str]]:
        """Deterministic migration-readiness verdict from a capability set (F13-04)."""
        by_key: dict[str, str] = {}
        for capability in capabilities:
            key = capability["key"] if isinstance(capability, dict) else capability.key
            value = capability["value"] if isinstance(capability, dict) else capability.value
            by_key[key] = value
        blockers: list[str] = []
        if by_key.get("package_json") != "present" and by_key.get("package_json") is not None:
            blockers.append("CAPABILITY_PACKAGE_JSON_INVALID")
        if by_key.get("angular_core", "absent") == "absent":
            blockers.append("CAPABILITY_ANGULAR_CORE_ABSENT")
        if by_key.get("workspace_type") == "not_angular_cli":
            blockers.append("CAPABILITY_NOT_ANGULAR_CLI_WORKSPACE")
        return ("blocked" if blockers else "ready", blockers)

    def list_run_snapshots(self, run_id: str) -> list[ProjectCapabilityModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(ProjectCapabilityModel)
                    .where(ProjectCapabilityModel.run_id == run_id)
                    .order_by(ProjectCapabilityModel.created_at.asc())
                ).all()
            )


def _package_version(package: dict, name: str) -> str | None:
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        value = (package.get(section) or {}).get(name)
        if isinstance(value, str):
            return _strip_range(value)
    return None


def _strip_range(value: str) -> str:
    return value.lstrip("^~>=< ").split(" ")[0].strip()


def _package_manager(package: dict) -> str:
    if "packageManager" in package:
        return str(package["packageManager"]).split("@")[0]
    return "npm"


def _lockfile(source_root: Path) -> str:
    if (source_root / "package-lock.json").is_file():
        return "package-lock"
    if (source_root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (source_root / "yarn.lock").is_file():
        return "yarn"
    return "absent"


def _angular_major_from(capabilities: list[ProjectCapability]) -> int | None:
    value = next((c.value for c in capabilities if c.key == "angular_core"), None)
    if not value or value == "absent":
        return None
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else None


def hashlib_short(run_id: str, checksum: str) -> str:
    import hashlib

    return hashlib.sha256(f"{run_id}:{checksum}".encode()).hexdigest()[:24]
