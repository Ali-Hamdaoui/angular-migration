"""Pure dependency-closure verification for the dependency-transition repair.

Reads package.json, package-lock.json (v3 "packages" schema), and the installed
node_modules metadata of the required Angular packages and reports whether the
manifest, lockfile, and installed tree all agree on the target major.
Deliberately dependency-free (stdlib json/re only).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# ponytail: no self-check, verified at runtime by the dependency-transition runner

_ANGULAR_BUILD_PACKAGES = frozenset({"@angular-devkit/build-angular", "@angular/build"})
_EXACT_VERSION = re.compile(
    r"\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def _major(value: object) -> int | None:
    match = re.match(r"\s*[~^]?\s*(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def _read_json(path: Path) -> dict | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def is_exact_version(value: object) -> bool:
    return isinstance(value, str) and _EXACT_VERSION.fullmatch(value) is not None


def installed_dependency_version(workspace: Path, package: str) -> str:
    """Resolve the exact installed package version from backend-owned state."""
    lock = _read_json(Path(workspace) / "package-lock.json") or {}
    lock_packages = lock.get("packages")
    lock_entry = lock_packages.get(f"node_modules/{package}") if isinstance(lock_packages, dict) else None
    lock_version = lock_entry.get("version") if isinstance(lock_entry, dict) else None
    if is_exact_version(lock_version):
        return lock_version
    installed = _read_json(Path(workspace) / "node_modules" / package / "package.json")
    installed_version = installed.get("version") if installed is not None else None
    if is_exact_version(installed_version):
        return installed_version
    raise ValueError("backend could not identify an exact installed package version")


def validate_dependency_transition_evidence(
    evidence: object,
    *,
    package: str,
    target_major: int,
    installed_version: str | None = None,
) -> dict[str, object]:
    """Return backend-derived transition facts, or fail closed."""
    if not isinstance(evidence, dict):
        raise ValueError("backend dependency evidence is missing")
    normalized = evidence.get("normalized_failure")
    diagnosis = normalized.get("failure_diagnosis") if isinstance(normalized, dict) else None
    if (
        not isinstance(normalized, dict)
        or normalized.get("command_id") != "angular-update-exact"
        or not isinstance(normalized.get("exit_code"), int)
        or normalized["exit_code"] == 0
        or not isinstance(diagnosis, dict)
        or diagnosis.get("kind") != "peer_dependency_conflict"
    ):
        raise ValueError("backend evidence does not prove an Angular peer-dependency conflict")
    authority_package = diagnosis.get("package")
    evidence_installed_version = diagnosis.get("installed_version")
    peer_ranges = diagnosis.get("required_ranges")
    if not isinstance(authority_package, str) or not authority_package.strip():
        raise ValueError("backend evidence did not identify the blocking package")
    if authority_package != package:
        raise ValueError("proposal package does not match the backend blocking package")
    installed_version = installed_version or evidence_installed_version
    if not is_exact_version(installed_version):
        raise ValueError("backend evidence did not identify the installed package version")
    if (
        not isinstance(peer_ranges, dict)
        or not peer_ranges
        or any(not isinstance(name, str) or not name for name in peer_ranges)
        or any(not isinstance(value, str) or not value.strip() for value in peer_ranges.values())
    ):
        raise ValueError("backend evidence did not identify a conflicting peer range")
    if not isinstance(target_major, int) or target_major < 0:
        raise ValueError("approved Angular target major is invalid")
    proposed_version = diagnosis.get("proposed_angular_version")
    if proposed_version is not None and (
        not is_exact_version(proposed_version) or _major(proposed_version) != target_major
    ):
        raise ValueError("backend evidence proposed Angular version is invalid")
    return {
        "package": authority_package,
        "installed_version": installed_version,
        "peer_ranges": dict(peer_ranges),
        "target_major": target_major,
        "proposed_angular_version": proposed_version,
    }


def verify_dependency_transition_state(
    workspace: Path, *, package: str, installed_version: str, peer_ranges: dict[str, str]
) -> None:
    """Prove the package was present in the authoritative pre-transition state."""
    manifest = _read_json(Path(workspace) / "package.json")
    if manifest is None:
        raise ValueError("authoritative package.json is missing or invalid")
    present = [
        section
        for section in ("dependencies", "devDependencies")
        if isinstance(manifest.get(section), dict) and package in manifest[section]
    ]
    if len(present) != 1:
        raise ValueError("blocking package is missing or ambiguous in current dependency state")
    installed = _read_json(Path(workspace) / "node_modules" / package / "package.json")
    if installed is None or installed.get("version") != installed_version:
        raise ValueError("installed blocking package version does not match backend evidence")
    if not peer_ranges:
        raise ValueError("conflicting peer range evidence is missing")


def angular_build_package(workspace: Path) -> str:
    """Resolve the build package from package.json and Angular builder entries."""
    workspace = Path(workspace)
    manifest = _read_json(workspace / "package.json")
    if manifest is None:
        raise ValueError("package.json is missing or invalid")
    declared = {
        package
        for section in ("dependencies", "devDependencies")
        for package in ((manifest.get(section) or {}).keys() if isinstance(manifest.get(section), dict) else ())
        if package in _ANGULAR_BUILD_PACKAGES
    }
    angular_path = workspace / "angular.json"
    angular = _read_json(angular_path) if angular_path.is_file() else None
    if angular_path.is_file() and angular is None:
        raise ValueError("angular.json is missing or invalid")
    builders: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            builder = value.get("builder")
            if isinstance(builder, str):
                package = builder.split(":", 1)[0]
                if package in _ANGULAR_BUILD_PACKAGES:
                    builders.add(package)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(angular)
    if len(builders) > 1:
        raise ValueError("angular.json uses multiple Angular build packages")
    if builders:
        selected = next(iter(builders))
        if declared and selected not in declared:
            raise ValueError("angular.json build package is absent from package.json")
        return selected
    if len(declared) != 1:
        raise ValueError("Angular build package authority is missing or ambiguous")
    return next(iter(declared))


def verify_dependency_closure(
    workspace: Path, *, target_major: int, required_packages: tuple[str, ...]
) -> dict:
    """Verify manifest/lockfile/installed agreement for every required package.

    For each package the entry carries the package.json range (manifest_range),
    the lockfile "packages"["node_modules/<pkg>"].version (lockfile_version),
    the root "packages"[""] dependency/devDependency range (lockfile_manifest_range),
    the installed node_modules/<pkg>/package.json version (installed_version),
    the parsed major of each, and agreement = all three majors present and equal
    to target_major. Missing files or entries surface as violations.
    """
    workspace = Path(workspace)
    manifest = _read_json(workspace / "package.json")
    lock = _read_json(workspace / "package-lock.json")
    lockfile_schema_version = lock.get("lockfileVersion") if lock is not None else None
    lock_packages = (lock or {}).get("packages")
    lock_packages = lock_packages if isinstance(lock_packages, dict) else {}
    root_entry = lock_packages.get("")
    root_entry = root_entry if isinstance(root_entry, dict) else {}
    root_ranges = {}
    for section in ("dependencies", "devDependencies"):
        value = root_entry.get(section)
        if isinstance(value, dict):
            root_ranges.update(value)
    packages: list[dict] = []
    violations: list[str] = []
    try:
        build_package = angular_build_package(workspace)
    except ValueError as error:
        build_package = None
        violations.append(str(error))
    packages_to_verify = list(dict.fromkeys(required_packages))
    if build_package and build_package not in packages_to_verify:
        packages_to_verify.append(build_package)
    for package in packages_to_verify:
        manifest_range = None
        if manifest is not None:
            for section in ("dependencies", "devDependencies"):
                value = manifest.get(section)
                if isinstance(value, dict) and isinstance(value.get(package), str):
                    manifest_range = value[package]
                    break
        manifest_major = _major(manifest_range)
        lock_entry = lock_packages.get(f"node_modules/{package}")
        lock_entry = lock_entry if isinstance(lock_entry, dict) else {}
        lockfile_version = lock_entry.get("version")
        lockfile_version = lockfile_version if isinstance(lockfile_version, str) else None
        lockfile_range = root_ranges.get(package)
        lockfile_range = lockfile_range if isinstance(lockfile_range, str) else None
        lockfile_manifest_major = _major(lockfile_range)
        lockfile_major = _major(lockfile_version)
        installed = _read_json(workspace / "node_modules" / package / "package.json")
        installed_version = installed.get("version") if installed is not None else None
        installed_version = installed_version if isinstance(installed_version, str) else None
        installed_major = _major(installed_version)
        agreement = (
            manifest_major is not None
            and lockfile_manifest_major is not None
            and lockfile_major is not None
            and installed_major is not None
            and manifest_major == target_major
            and lockfile_manifest_major == target_major
            and lockfile_major == target_major
            and installed_major == target_major
        )
        entry = {
            "package": package,
            "manifest_range": manifest_range,
            "manifest_major": manifest_major,
            "lockfile_version": lockfile_version,
            "lockfile_manifest_range": lockfile_range,
            "lockfile_manifest_major": lockfile_manifest_major,
            "lockfile_major": lockfile_major,
            "installed_version": installed_version,
            "installed_major": installed_major,
            "agreement": agreement,
        }
        packages.append(entry)
        if not agreement:
            violations.append(
                f"{package}: manifest_major={manifest_major}, "
                f"lockfile_manifest_major={lockfile_manifest_major}, "
                f"lockfile_major={lockfile_major}, installed_major={installed_major}, "
                f"target_major={target_major}"
            )
    if manifest is None:
        violations.append("package.json is missing or invalid")
    if lock is None:
        violations.append("package-lock.json is missing or invalid")
    elif not isinstance(lockfile_schema_version, int) or lockfile_schema_version < 3:
        violations.append(
            f"package-lock.json lockfileVersion={lockfile_schema_version} is not v3; "
            "resolved package entries cannot be verified"
        )
    return {
        "ok": not violations,
        "target_major": target_major,
        "build_package": build_package,
        "packages": packages,
        "violations": violations,
    }
