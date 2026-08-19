"""Deterministic pre-G10 dependency state validation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.stage_knowledge_service import StageKnowledgeRegistry


class DependencyRepairPreflightError(ValueError):
    def __init__(self, code: str, message: str, evidence: dict[str, object]):
        super().__init__(message)
        self.code = code
        self.message = message
        self.evidence = evidence


class DependencyRepairPreflightService:
    """Prove the proposed dependency state is internally target-compatible."""

    def validate(
        self,
        *,
        workspace: Path,
        proposal: dict[str, object],
        source_family: str,
        target_family: str,
        catalogue_version: str | None = None,
    ) -> dict[str, object]:
        current = self._read_json(workspace / "package.json")
        proposed = self._proposed_manifest(current, proposal)
        source_major = self._major(source_family)
        target_major = self._major(target_family)
        catalogue = CompatibilityCatalogueProvider().load(catalogue_version or CompatibilityCatalogueProvider.CURRENT_VERSION)
        entry = catalogue.entry_for(source_family, target_family)
        if entry is None:
            raise DependencyRepairPreflightError(
                "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                f"No compatibility catalogue entry for {source_family} -> {target_family}",
                {"source_family": source_family, "target_family": target_family},
            )
        knowledge = StageKnowledgeRegistry().entry(source_major, target_major)
        findings: list[dict[str, object]] = []
        dependencies = self._dependencies(proposed)
        for package, spec in dependencies.items():
            if self._angular_package(package):
                major = self._spec_major(spec)
                if major != target_major:
                    findings.append({
                        "code": "ANGULAR_PACKAGE_MAJOR_MISMATCH",
                        "package": package,
                        "proposed_spec": spec,
                        "proposed_major": major,
                        "target_major": target_major,
                    })
        typescript = dependencies.get("typescript")
        if typescript is not None and not self._range_overlaps_target(
            typescript, entry.typescript_minimum, entry.typescript_exclusive_maximum
        ):
            findings.append({
                "code": "TYPESCRIPT_OUTSIDE_CATALOGUE",
                "package": "typescript",
                "proposed_spec": typescript,
                "minimum": entry.typescript_minimum,
                "exclusive_maximum": entry.typescript_exclusive_maximum,
            })
        rxjs = dependencies.get("rxjs")
        if rxjs is not None and not any(
            self._ranges_overlap(rxjs, rng)
            for rng in entry.rxjs_ranges
        ):
            findings.append({
                "code": "RXJS_OUTSIDE_CATALOGUE",
                "package": "rxjs",
                "proposed_spec": rxjs,
                "allowed_ranges": list(entry.rxjs_ranges),
            })
        peer_metadata = self._peer_metadata(workspace, dependencies, target_major)
        for finding in peer_metadata:
            findings.append(finding)
        evidence = {
            "status": "passed" if not findings else "failed",
            "source_family": source_family,
            "target_family": target_family,
            "target_major": target_major,
            "catalogue_version": catalogue.version,
            "catalogue_checksum": catalogue.checksum,
            "stage_knowledge_version": knowledge.version,
            "proposed_dependencies": dependencies,
            "peer_metadata": peer_metadata,
            "findings": findings,
        }
        if findings:
            raise DependencyRepairPreflightError(
                "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                "Proposed dependency state is incompatible: " + json.dumps(findings, sort_keys=True),
                evidence,
            )
        return evidence

    def classify_current_state(
        self, *, workspace: Path, source_family: str, target_family: str
    ) -> dict[str, object]:
        """Classify manifest/lock/install drift without asking the repair model."""
        manifest = self._read_json(workspace / "package.json")
        try:
            compatibility = self.validate(
                workspace=workspace,
                proposal={
                    "operations": [
                        {
                            "operation": "replace_text_file",
                            "path": "package.json",
                            "new_text": json.dumps(manifest, sort_keys=True),
                        }
                    ]
                },
                source_family=source_family,
                target_family=target_family,
            )
        except DependencyRepairPreflightError as error:
            return {"classification": "MANIFEST_CONFLICT", "evidence": error.evidence}

        target_major = self._major(target_family)
        dependencies = self._dependencies(manifest)
        target_packages = {
            package: spec
            for package, spec in dependencies.items()
            if self._angular_package(package) and self._spec_major(spec) == target_major
        }
        lock = self._read_optional_json(workspace / "package-lock.json")
        lock_versions = {
            package: self._resolved_version(lock, package) for package in target_packages
        }
        installed_versions = {
            package: self._installed_version(workspace, package) for package in target_packages
        }
        stale_lock = sorted(
            package
            for package, version in lock_versions.items()
            if self._spec_major(version or "") != target_major
        )
        stale_install = sorted(
            package
            for package, version in installed_versions.items()
            if version is not None and self._spec_major(version) != target_major
        )
        classification = (
            "TARGET_MANIFEST_AHEAD"
            if stale_lock
            else "INSTALL_TREE_STALE"
            if stale_install
            else "COHERENT_SOURCE_STATE"
        )
        return {
            "classification": classification,
            "manifest_target_packages": target_packages,
            "lock_versions": lock_versions,
            "installed_versions": installed_versions,
            "stale_lock_packages": stale_lock,
            "stale_install_packages": stale_install,
            "compatibility": compatibility,
        }

    @staticmethod
    def _read_optional_json(path: Path) -> dict[str, object]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _resolved_version(lock: dict[str, object], package: str) -> str | None:
        packages = lock.get("packages")
        if isinstance(packages, dict):
            entry = packages.get(f"node_modules/{package}")
            if isinstance(entry, dict) and isinstance(entry.get("version"), str):
                return entry["version"]
        dependencies = lock.get("dependencies")
        entry = dependencies.get(package) if isinstance(dependencies, dict) else None
        return entry.get("version") if isinstance(entry, dict) and isinstance(entry.get("version"), str) else None

    @staticmethod
    def _installed_version(workspace: Path, package: str) -> str | None:
        try:
            value = json.loads(
                (workspace / "node_modules" / Path(package) / "package.json").read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value.get("version") if isinstance(value, dict) and isinstance(value.get("version"), str) else None

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DependencyRepairPreflightError(
                "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                "Authoritative package.json is missing or invalid",
                {"path": str(path)},
            ) from error
        if not isinstance(value, dict):
            raise DependencyRepairPreflightError(
                "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                "Authoritative package.json is not an object",
                {"path": str(path)},
            )
        return value

    @classmethod
    def _proposed_manifest(cls, current: dict[str, object], proposal: dict[str, object]) -> dict[str, object]:
        proposed = dict(current)
        operations = proposal.get("operations")
        if not isinstance(operations, list) or not operations:
            raise DependencyRepairPreflightError(
                "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                "Dependency proposal has no operations",
                {"operations": operations},
            )
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            if operation.get("path") == "package.json" and isinstance(operation.get("new_text"), str):
                try:
                    value = json.loads(operation["new_text"])
                except json.JSONDecodeError as error:
                    raise DependencyRepairPreflightError(
                        "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                        "Dependency proposal package.json is invalid JSON",
                        {},
                    ) from error
                if not isinstance(value, dict):
                    raise DependencyRepairPreflightError(
                        "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                        "Dependency proposal package.json is not an object",
                        {},
                    )
                proposed = value
                continue
            if operation.get("operation") == "dependency_transition":
                target_state = operation.get("target_state")
                package = target_state.get("package") if isinstance(target_state, dict) else None
                version = (
                    target_state.get("target_version")
                    if isinstance(target_state, dict)
                    else None
                )
                sections = [
                    section
                    for section in ("dependencies", "devDependencies")
                    if isinstance(proposed.get(section), dict)
                    and isinstance(package, str)
                    and package in proposed[section]
                ]
                if len(sections) != 1 or not isinstance(version, str):
                    raise DependencyRepairPreflightError(
                        "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                        "Dependency transition target is missing or ambiguous in package.json",
                        {"package": package, "target_version": version, "sections": sections},
                    )
                proposed[sections[0]][package] = version
                continue
            package = operation.get("package")
            section = operation.get("section")
            version = operation.get("new_version")
            target_state = operation.get("target_state")
            if isinstance(target_state, dict):
                version = target_state.get("version") or target_state.get("target_version")
            if isinstance(package, str) and isinstance(section, str) and isinstance(version, str):
                proposed.setdefault(section, {})[package] = version
        return proposed

    @staticmethod
    def _dependencies(manifest: dict[str, object]) -> dict[str, str]:
        result: dict[str, str] = {}
        for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            values = manifest.get(section)
            if isinstance(values, dict):
                result.update({name: value for name, value in values.items() if isinstance(name, str) and isinstance(value, str)})
        return result

    @staticmethod
    def _angular_package(package: str) -> bool:
        return package.startswith("@angular/") or package == "@angular-devkit/build-angular"

    @staticmethod
    def _major(value: str) -> int:
        match = re.search(r"\d+", value or "")
        if match is None:
            raise DependencyRepairPreflightError(
                "REPAIR_DEPENDENCY_PREFLIGHT_FAILED",
                f"Invalid Angular family: {value}",
                {"family": value},
            )
        return int(match.group(0))

    @staticmethod
    def _spec_major(value: str) -> int | None:
        match = re.search(r"\d+", value or "")
        return int(match.group(0)) if match else None

    @classmethod
    def _range_overlaps_target(cls, spec: str, minimum: str | None, exclusive_maximum: str | None) -> bool:
        lower, upper = cls._range_interval(spec)
        if lower is None:
            return False
        minimum_value = cls._version_tuple(minimum) if minimum else None
        if minimum_value is not None and (upper is not None and upper <= minimum_value):
            return False
        if exclusive_maximum is not None and lower >= cls._version_tuple(exclusive_maximum):
            return False
        return True

    @classmethod
    def _ranges_overlap(cls, left: str, right: str) -> bool:
        for left_branch in left.split("||"):
            left_lower, left_upper = cls._range_interval(left_branch)
            if left_lower is None:
                continue
            for right_branch in right.split("||"):
                right_lower, right_upper = cls._range_interval(right_branch)
                if right_lower is None:
                    return True
                if (left_upper is None or right_lower < left_upper) and (
                    right_upper is None or left_lower < right_upper
                ):
                    return True
        return False

    @staticmethod
    def _range_minimum(value: str) -> str:
        match = re.search(r"\d+(?:\.\d+){0,2}", value or "")
        return match.group(0) if match else ""

    @classmethod
    def _range_upper(cls, value: str) -> tuple[int, int, int] | None:
        lower = cls._version_tuple(cls._range_minimum(value))
        if lower is None:
            return None
        if value.lstrip().startswith("~"):
            return (lower[0], lower[1] + 1, 0)
        if value.lstrip().startswith("^"):
            return (lower[0] + 1, 0, 0) if lower[0] else (0, lower[1] + 1, 0)
        return lower

    @classmethod
    def _range_interval(
        cls, value: str
    ) -> tuple[tuple[int, int, int] | None, tuple[int, int, int] | None]:
        value = value.strip()
        if not value or value in {"*", "x", "X"}:
            return None, None
        if value.startswith("^") or value.startswith("~"):
            lower = cls._version_tuple(cls._range_minimum(value))
            return lower, cls._range_upper(value)
        tokens = value.split()
        if len(tokens) == 1 and re.fullmatch(r"\d+(?:\.\d+){0,2}", value):
            lower = cls._version_tuple(value)
            return lower, cls._next_patch(lower)
        lower_bound = None
        upper_bound = None
        for token in tokens:
            match = re.match(r"(>=|>|<=|<)?(\d+(?:\.\d+){0,2})$", token)
            if match is None:
                return None, None
            version = cls._version_tuple(match.group(2))
            operator = match.group(1) or "="
            if operator in {">=", ">", "="}:
                candidate = cls._next_patch(version) if operator == ">" else version
                lower_bound = max(lower_bound, candidate) if lower_bound else candidate
                if operator == "=":
                    upper_bound = cls._next_patch(version)
            else:
                candidate = cls._next_patch(version) if operator == "<=" else version
                upper_bound = min(upper_bound, candidate) if upper_bound else candidate
        return lower_bound, upper_bound

    @staticmethod
    def _next_patch(value: tuple[int, int, int] | None) -> tuple[int, int, int] | None:
        return (value[0], value[1], value[2] + 1) if value is not None else None

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, int, int] | None:
        parts = value.split(".") if value else []
        if not parts or not all(part.isdigit() for part in parts):
            return None
        numbers = [int(part) for part in parts]
        return tuple((numbers + [0, 0])[:3])

    @classmethod
    def _peer_metadata(cls, workspace: Path, dependencies: dict[str, str], target_major: int) -> list[dict[str, object]]:
        findings: list[dict[str, object]] = []
        for package, spec in dependencies.items():
            if not cls._angular_package(package) or cls._spec_major(spec) != target_major:
                continue
            metadata_path = workspace / "node_modules" / Path(package) / "package.json"
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            installed_major = cls._spec_major(str(metadata.get("version") or ""))
            if installed_major != target_major:
                continue
            peers = metadata.get("peerDependencies")
            if not isinstance(peers, dict):
                continue
            for peer, peer_spec in peers.items():
                if (
                    peer in dependencies
                    and isinstance(peer_spec, str)
                    and not cls._ranges_overlap(dependencies[peer], peer_spec)
                ):
                    findings.append({
                        "code": "PEER_DEPENDENCY_RANGE_MISMATCH",
                        "package": package,
                        "peer": peer,
                        "peer_range": peer_spec,
                        "proposed_peer_spec": dependencies[peer],
                    })
        return findings
