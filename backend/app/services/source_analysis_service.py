"""Deterministic, read-only Angular source eligibility analysis."""

import hashlib
import json
import re
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.domain.source_analysis import (
    DetectedVersion,
    SourceAnalysisRequest,
    SourceAnalysisResult,
    SourceAnalysisSnapshot,
    WorkspaceTopology,
)

class SourceAnalysisService:
    policy_version = "source-analysis-v1"
    tracked_packages = ("@angular/core", "@angular/cli", "@angular/material", "@angular/cdk", "typescript", "rxjs", "zone.js")

    def __init__(self, *, now_provider: Callable[[], object] | None = None) -> None:
        self._now_provider = now_provider

    def analyze(self, request: SourceAnalysisRequest) -> SourceAnalysisResult:
        source = Path(request.source_path).expanduser().resolve(strict=False)
        blockers: list[str] = []
        warnings: list[str] = []
        package = self._read_json(source / "package.json")
        lockfile_name = next((name for name in ("package-lock.json", "npm-shrinkwrap.json") if (source / name).is_file()), None)
        lockfile = self._read_json(source / lockfile_name) if lockfile_name else {}
        if not package:
            blockers.append("PACKAGE_JSON_MISSING")
        if lockfile_name is None:
            blockers.append("NPM_LOCKFILE_MISSING")
        elif not lockfile:
            blockers.append("NPM_LOCKFILE_INVALID")

        declared = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
        resolved = self._resolved_versions(lockfile)
        versions = [
            DetectedVersion(
                package=name,
                declared=declared.get(name),
                resolved=resolved.get(name),
                family=self._family(resolved.get(name) or declared.get(name)),
                confidence="high" if resolved.get(name) else ("medium" if declared.get(name) else "unknown"),
            )
            for name in self.tracked_packages
            if name in declared or name in resolved
        ]
        angular_core = next((item for item in versions if item.package == "@angular/core"), None)
        if angular_core is None:
            if any("angular" in name.lower() and "@" not in name for name in declared):
                blockers.append("ANGULARJS_DETECTED")
            else:
                blockers.append("ANGULAR_NOT_DETECTED")
        else:
            major = self._major(angular_core.family)
            if major is not None and major <= 10:
                blockers.append("ANGULAR_VERSION_UNSUPPORTED")
            elif major is not None and 11 <= major <= 17:
                warnings.append("ANGULAR_VERSION_REVIEW_REQUIRED")
            elif major is None:
                blockers.append("ANGULAR_VERSION_UNRESOLVED")

        topology = self._topology(source)
        if topology.classification == "unknown":
            warnings.append("WORKSPACE_TOPOLOGY_UNKNOWN")
        if topology.has_custom_builder:
            warnings.append("CUSTOM_BUILDER_DETECTED")
        status = "blocked" if blockers else ("review_required" if warnings else "accepted")
        payload = {
            "analysis_id": f"analysis-{uuid4().hex[:12]}",
            "policy_version": self.policy_version,
            "status": status,
            "source_path": str(source),
            "package_manager": "npm" if lockfile_name else "unknown",
            "lockfile": lockfile_name,
            "versions": [item.model_dump(mode="json") for item in versions],
            "topology": topology.model_dump(mode="json"),
            "blockers": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
        }
        return SourceAnalysisResult(
            snapshot=SourceAnalysisSnapshot(
                **payload,
                checksum=self._checksum(payload),
            )
        )

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _resolved_versions(lockfile: dict) -> dict[str, str]:
        packages = lockfile.get("packages", {})
        result: dict[str, str] = {}
        for name in SourceAnalysisService.tracked_packages:
            node = packages.get(f"node_modules/{name}", {})
            if isinstance(node, dict) and isinstance(node.get("version"), str):
                result[name] = node["version"]
        # npm lockfile v1 stores installed versions in the top-level
        # dependencies map instead of the v2+ packages map.
        legacy_dependencies = lockfile.get("dependencies", {})
        for name in SourceAnalysisService.tracked_packages:
            if name in result:
                continue
            node = legacy_dependencies.get(name, {})
            if isinstance(node, dict) and isinstance(node.get("version"), str):
                result[name] = node["version"]
        return result

    @staticmethod
    def _family(version: str | None) -> str | None:
        if not version:
            return None
        match = re.search(r"(\d+)(?:\.\d+)?", version)
        return f"{match.group(1)}.x" if match else None

    @staticmethod
    def _major(family: str | None) -> int | None:
        try:
            return int(family.split(".")[0]) if family else None
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _topology(source: Path) -> WorkspaceTopology:
        angular = SourceAnalysisService._read_json(source / "angular.json")
        projects = list((angular.get("projects") or {}).keys())
        libraries = [name for name, item in (angular.get("projects") or {}).items() if item.get("projectType") == "library"]
        custom = any(
            builder and not str(builder).startswith("@angular-devkit/build-angular:")
            for item in (angular.get("projects") or {}).values()
            for builder in (item.get("architect") or {}).values()
            if isinstance(builder, dict)
        )
        classification = "multi-application" if len(projects) > 1 else ("single-application" if projects else "unknown")
        return WorkspaceTopology(
            projects=projects,
            libraries=libraries,
            is_nx=(source / "nx.json").is_file(),
            has_custom_builder=custom,
            classification=classification,
        )

    @staticmethod
    def _checksum(payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
