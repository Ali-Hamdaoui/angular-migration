"""Pure dependency-closure verification for the dependency-transition repair.

Reads package.json, package-lock.json (v3 "packages" schema), and the installed
node_modules metadata of the required Angular packages and reports whether the
manifest, lockfile, and installed tree all agree on the target major.
Deliberately dependency-free (stdlib json/re only).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# ponytail: no self-check, verified at runtime by the dependency-transition runner

_ANGULAR_BUILD_PACKAGES = frozenset({"@angular-devkit/build-angular", "@angular/build"})
_EXACT_VERSION = re.compile(
    r"\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


@dataclass(frozen=True)
class DependencyTransitionBundleMember:
    """One ordered exact target of a backend-owned dependency transition bundle."""

    package: str
    exact_version: str
    required: bool


@dataclass(frozen=True)
class DependencyTransitionBundle:
    """Immutable backend-owned transition bundle for one primary blocker."""

    primary_package: str
    angular_major: int
    members: tuple[DependencyTransitionBundleMember, ...]


# Package-owned release metadata frozen as backend policy: the builder aligns its
# major with Angular; jest-preset-angular 14.4.0 is its first Angular 19 release.
# Each entry is an ordered tuple of (package, exact version, required) members:
# "required" members are always installed; "align_if_present" members (required
# False) are installed only when the authoritative package.json already declares
# them. Order is the install order: required companions first, primary last.
_COMPATIBLE_REINSTALL_BUNDLES: dict[tuple[str, int], tuple[tuple[str, str, bool], ...]] = {
    # Angular 13's build tool declares a TypeScript ~4.4.3 peer.  npm may
    # select build-angular 13.0.4 for the planned 13.0.x transition, so the
    # governed detach/update/reattach path binds both exact package versions.
    ("@angular-devkit/build-angular", 13): (
        ("typescript", "4.4.4", True),
        ("@angular-devkit/build-angular", "13.0.4", True),
    ),
    ("@angular-builders/jest", 19): (("@angular-builders/jest", "19.0.0", True),),
    ("jest-preset-angular", 19): (("jest-preset-angular", "14.4.0", True),),
    ("jest-preset-angular", 20): (("jest-preset-angular", "14.6.2", True),),
    ("jest-preset-angular", 21): (
        ("jest", "30.4.2", True),
        ("jsdom", "26.1.0", True),
        ("@types/jest", "30.0.0", False),
        ("jest-preset-angular", "16.1.3", True),
    ),
}


def _compatible_reinstall_authority(
    package: str, target_major: int
) -> tuple[tuple[str, str, bool], ...]:
    authority = _COMPATIBLE_REINSTALL_BUNDLES.get((package, target_major))
    if authority is None:
        raise ValueError(
            "field=operations.0.target_state.target_version; "
            f"expected=backend-approved exact version for {package} at Angular {target_major}; "
            "observed=missing; artifact_id=unavailable; execution_id=unavailable; "
            "recovery=add verified package compatibility authority before retrying"
        )
    return authority


def _major(value: object) -> int | None:
    match = re.match(r"\s*[~^]?\s*(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def _read_json(path: Path) -> dict | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def is_exact_version(value: object) -> bool:
    return isinstance(value, str) and _EXACT_VERSION.fullmatch(value) is not None


def compatible_reinstall_version(package: str, target_major: int) -> str:
    """Resolve the backend-approved exact primary reinstall version, or fail closed."""
    authority = _compatible_reinstall_authority(package, target_major)
    primary = next((entry for entry in authority if entry[0] == package), None)
    if primary is None or not is_exact_version(primary[1]):
        raise ValueError(
            "field=operations.0.target_state.target_version; "
            f"expected=backend-approved exact version for {package} at Angular {target_major}; "
            "observed=missing; artifact_id=unavailable; execution_id=unavailable; "
            "recovery=add verified package compatibility authority before retrying"
        )
    return primary[1]


def compatible_reinstall_bundle(
    package: str, target_major: int, workspace: Path
) -> DependencyTransitionBundle:
    """Resolve the deterministic backend-owned transition bundle, or fail closed.

    The primary package remains identifiable as the ordered last member.
    Align-if-present members are included only when the authoritative
    package.json already declares them. Unknown package/Angular-major
    combinations fail closed.
    """
    authority = _compatible_reinstall_authority(package, target_major)
    manifest = _read_json(Path(workspace) / "package.json")
    if manifest is None:
        raise ValueError("authoritative package.json is missing or invalid")
    declared = {
        entry
        for section in ("dependencies", "devDependencies")
        if isinstance(manifest.get(section), dict)
        for entry in manifest[section]
    }
    raw_members = tuple(entry for entry in authority if entry[2] or entry[0] in declared)
    packages = [entry[0] for entry in raw_members]
    if len(set(packages)) != len(packages):
        raise ValueError("dependency transition bundle contains duplicate packages")
    if sum(entry[0] == package for entry in raw_members) != 1:
        raise ValueError(
            "dependency transition bundle primary package is missing or ambiguous"
        )
    for _, version, _ in raw_members:
        if not is_exact_version(version):
            raise ValueError("dependency transition bundle contains a non-exact version")
    return DependencyTransitionBundle(
        primary_package=package,
        angular_major=target_major,
        members=tuple(
            DependencyTransitionBundleMember(
                package=name, exact_version=version, required=required
            )
            for name, version, required in raw_members
        ),
    )


def _evidence_error(
    evidence: object,
    *,
    field: str,
    expected: str,
    observed: object,
    artifact_id: str | None,
    recovery: str,
) -> ValueError:
    execution_id = evidence.get("execution_id") if isinstance(evidence, dict) else None
    rendered = json.dumps(observed, sort_keys=True, default=str)
    return ValueError(
        f"field={field}; expected={expected}; observed={rendered}; "
        f"artifact_id={artifact_id or 'unavailable'}; "
        f"execution_id={execution_id or 'unavailable'}; recovery={recovery}"
    )


def installed_dependency_version(workspace: Path, package: str) -> str:
    """Resolve the exact installed package version from backend-owned state.

    npm lockfile v1 stores dependency records under ``dependencies`` rather
    than the npm v2+ ``packages`` map.  Check that authoritative lockfile
    shape before consulting ``node_modules``; recovery checkpoints deliberately
    omit the mutable install tree.
    """
    lock = _read_json(Path(workspace) / "package-lock.json") or {}
    lock_packages = lock.get("packages")
    lock_entry = lock_packages.get(f"node_modules/{package}") if isinstance(lock_packages, dict) else None
    lock_version = lock_entry.get("version") if isinstance(lock_entry, dict) else None
    if is_exact_version(lock_version):
        return lock_version

    def find_legacy_entry(dependencies: object) -> dict | None:
        if not isinstance(dependencies, dict):
            return None
        direct = dependencies.get(package)
        if isinstance(direct, dict):
            return direct
        for entry in dependencies.values():
            if not isinstance(entry, dict):
                continue
            nested = find_legacy_entry(entry.get("dependencies"))
            if nested is not None:
                return nested
        return None

    legacy_entry = find_legacy_entry(lock.get("dependencies"))
    legacy_version = legacy_entry.get("version") if legacy_entry else None
    if is_exact_version(legacy_version):
        return legacy_version

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
    artifact_id: str | None = None,
) -> dict[str, object]:
    """Return backend-derived transition facts, or fail closed."""
    if not isinstance(evidence, dict):
        raise ValueError("backend dependency evidence is missing")
    normalized = evidence.get("normalized_failure")
    diagnosis = normalized.get("failure_diagnosis") if isinstance(normalized, dict) else None
    supported_peer_conflict_evidence = (
        isinstance(normalized, dict)
        and (
            normalized.get("command_id") == "angular-update-exact"
            or (
                normalized.get("command_id") == "npm-lockfile-generate"
                and isinstance(diagnosis, dict)
                and diagnosis.get("source") == "npm_eresolve_peer_conflict"
            )
        )
    )
    if (
        not isinstance(normalized, dict)
        or not supported_peer_conflict_evidence
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
        raise _evidence_error(
            evidence,
            field="normalized_failure.failure_diagnosis.package",
            expected="non-empty blocking package parsed from the failed Angular command",
            observed=authority_package,
            artifact_id=artifact_id,
            recovery="reparse the immutable command failure with the npm package-name grammar",
        )
    if authority_package != package:
        raise ValueError("proposal package does not match the backend blocking package")
    installed_version = installed_version or evidence_installed_version
    if not is_exact_version(installed_version):
        raise _evidence_error(
            evidence,
            field="normalized_failure.failure_diagnosis.installed_version",
            expected="exact version present in package-lock.json and installed package metadata",
            observed=installed_version,
            artifact_id=artifact_id,
            recovery="rebind the exact installed version from authoritative workspace evidence",
        )
    if (
        not isinstance(peer_ranges, dict)
        or not peer_ranges
        or any(not isinstance(name, str) or not name for name in peer_ranges)
        or any(not isinstance(value, str) or not value.strip() for value in peer_ranges.values())
    ):
        raise _evidence_error(
            evidence,
            field="normalized_failure.failure_diagnosis.required_ranges",
            expected="non-empty peer package to incompatible range mapping",
            observed=peer_ranges,
            artifact_id=artifact_id,
            recovery="reparse the immutable Angular peer-conflict message",
        )
    if not isinstance(target_major, int) or target_major < 0:
        raise ValueError("approved Angular target major is invalid")
    proposed_version = diagnosis.get("proposed_angular_version")
    if proposed_version is not None and (
        not is_exact_version(proposed_version) or _major(proposed_version) != target_major
    ):
        raise ValueError("backend evidence proposed Angular version is invalid")
    try:
        target_version = compatible_reinstall_version(authority_package, target_major)
    except ValueError as error:
        raise _evidence_error(
            evidence,
            field="operations.0.target_state.target_version",
            expected=f"backend-approved exact version for {authority_package} at Angular {target_major}",
            observed=None,
            artifact_id=artifact_id,
            recovery="add verified package compatibility authority before retrying",
        ) from error
    return {
        "package": authority_package,
        "installed_version": installed_version,
        "peer_ranges": dict(peer_ranges),
        "target_major": target_major,
        "proposed_angular_version": proposed_version,
        "target_version": target_version,
    }


def verify_npm_eresolve_attempted_resolution_state(
    workspace: Path,
    *,
    diagnosis: dict[str, object],
) -> None:
    """Verify npm's rejected candidate against manifest/root intent only."""
    if diagnosis.get("source") != "npm_eresolve_peer_conflict":
        raise ValueError("attempted-resolution evidence source is invalid")
    package = diagnosis.get("package")
    package_version = diagnosis.get("package_version")
    blocking_dependency = diagnosis.get("blocking_dependency")
    required_peer_range = diagnosis.get("required_peer_range")
    required_ranges = diagnosis.get("required_ranges")
    if not isinstance(package, str) or not package.strip():
        raise ValueError("attempted-resolution evidence causal package is missing")
    if not is_exact_version(package_version):
        raise ValueError("attempted package version is missing or not exact")
    if not isinstance(blocking_dependency, str) or not blocking_dependency.strip():
        raise ValueError("attempted-resolution evidence blocking dependency is missing")
    if not isinstance(required_peer_range, str) or not required_peer_range.strip():
        raise ValueError("attempted-resolution evidence peer range is missing")
    if required_ranges != {blocking_dependency: required_peer_range}:
        raise ValueError("attempted-resolution evidence peer ranges are inconsistent")

    manifest = _read_json(Path(workspace) / "package.json")
    if manifest is None:
        raise ValueError("causal package intent is missing or invalid")
    package_sections = [
        section
        for section in ("dependencies", "devDependencies")
        if isinstance(manifest.get(section), dict) and package in manifest[section]
    ]
    if len(package_sections) != 1:
        raise ValueError("causal package intent is missing or ambiguous")
    package_intent = manifest[package_sections[0]][package]
    if not isinstance(package_intent, str) or not package_intent.strip():
        raise ValueError("causal package intent is missing or invalid")
    if is_exact_version(package_intent) and package_intent != package_version:
        raise ValueError("attempted package version conflicts with exact package intent")

    blocking_sections = [
        section
        for section in ("dependencies", "devDependencies")
        if isinstance(manifest.get(section), dict)
        and blocking_dependency in manifest[section]
    ]
    if len(blocking_sections) != 1:
        raise ValueError("blocking dependency is missing or ambiguous in root dependency state")


def verify_dependency_transition_evidence_for_source(
    workspace: Path,
    *,
    diagnosis: dict[str, object],
    package: str,
    installed_version: str,
    peer_ranges: dict[str, str],
) -> None:
    """Verify transition pre-state according to its immutable evidence source."""
    if diagnosis.get("source") == "npm_eresolve_peer_conflict":
        verify_npm_eresolve_attempted_resolution_state(workspace, diagnosis=diagnosis)
        return
    verify_dependency_transition_state(
        workspace,
        package=package,
        installed_version=installed_version,
        peer_ranges=peer_ranges,
        allow_missing_installed_metadata=diagnosis.get("source") is None,
    )


def verify_dependency_transition_state(
    workspace: Path,
    *,
    package: str,
    installed_version: str,
    peer_ranges: dict[str, str],
    allow_missing_installed_metadata: bool = False,
) -> None:
    """Prove the package was present in the authoritative pre-transition state.

    Immutable recovery checkpoints may omit ``node_modules``. In that case
    the exact lockfile version is authoritative; installed metadata is still
    checked whenever it is present. Both npm v1 and npm v2+ lockfile layouts
    are supported.
    """
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
    lock = _read_json(Path(workspace) / "package-lock.json")
    lock_packages = lock.get("packages") if lock is not None else None
    lock_entry = (
        lock_packages.get(f"node_modules/{package}")
        if isinstance(lock_packages, dict)
        else None
    )
    lock_root = lock_packages.get("") if isinstance(lock_packages, dict) else None
    if isinstance(lock_root, dict):
        lock_present = [
            section
            for section in ("dependencies", "devDependencies")
            if isinstance(lock_root.get(section), dict) and package in lock_root[section]
        ]
    else:
        legacy_dependencies = lock.get("dependencies") if isinstance(lock, dict) else None
        lock_present = [
            "dependencies"
            if isinstance(legacy_dependencies, dict) and package in legacy_dependencies
            else ""
        ]
        lock_present = [item for item in lock_present if item]
        lock_entry = (
            legacy_dependencies.get(package)
            if isinstance(legacy_dependencies, dict)
            else None
        )
    if (
        not isinstance(lock_entry, dict)
        or lock_entry.get("version") != installed_version
        or len(lock_present) != 1
    ):
        raise ValueError("package-lock.json blocking package state does not match backend evidence")
    installed = _read_json(Path(workspace) / "node_modules" / package / "package.json")
    if installed is None and allow_missing_installed_metadata:
        return
    if installed is None or installed.get("version") != installed_version:
        raise ValueError("installed blocking package version does not match backend evidence")
    if not peer_ranges:
        raise ValueError("conflicting peer range evidence is missing")
    installed_peers = installed.get("peerDependencies") if installed is not None else None
    if not isinstance(installed_peers, dict) or any(
        installed_peers.get(name) != version_range
        for name, version_range in peer_ranges.items()
    ):
        raise ValueError("installed package peer ranges do not match backend conflict evidence")


def verify_dependency_add_state(
    workspace: Path,
    *,
    package: str,
    section: str,
    approved_version_spec: str,
) -> dict[str, object]:
    """Verify a governed dependency_add post-state from the approved version spec.

    The approved package.json version spec is human-approved truth. Governed
    lockfile generation and npm ci are package-manager evidence that the locked
    tree satisfies the manifest; this verifier does not independently resolve
    the range. It fails closed when:
      * package.json does not declare the package at the approved spec
      * the lockfile root does not declare the package at the approved spec
      * the lockfile exact package entry or its version is missing
      * the installed exact version is missing
      * the lockfile exact version differs from the installed exact version
    The exact resolved version is OBSERVED from the lockfile, never
    predeclared here.
    """
    workspace = Path(workspace)
    if not isinstance(approved_version_spec, str) or not approved_version_spec:
        raise ValueError(
            "field=approved_version_spec; "
            f"expected=non-empty approved version spec for {package}; "
            f"observed={json.dumps(approved_version_spec)}; "
            "recovery=rebind the approved dependency-addition version spec before retrying"
        )
    if section not in ("dependencies", "devDependencies"):
        raise ValueError(
            "field=section; "
            "expected=dependency-addition section 'dependencies' or 'devDependencies'; "
            f"observed={json.dumps(section)}; "
            "recovery=declare the package in dependencies or devDependencies only"
        )
    violations: list[str] = []
    manifest_value = None
    manifest = _read_json(workspace / "package.json")
    if manifest is None:
        violations.append("package.json is missing or invalid")
    else:
        declared = [
            name
            for name in ("dependencies", "devDependencies")
            if isinstance(manifest.get(name), dict) and package in manifest[name]
        ]
        if not declared:
            violations.append(f"package.json declares {package} in no dependency section")
        elif len(declared) != 1 or declared[0] != section:
            violations.append(
                f"package.json declares {package} in {','.join(declared)}; expected only {section}"
            )
        else:
            manifest_value = manifest[section][package]
            if manifest_value != approved_version_spec:
                violations.append(
                    f"package.json {section}.{package}={json.dumps(manifest_value)}; "
                    f"expected approved spec={approved_version_spec}"
                )
    lockfile_manifest_value = None
    resolved_exact_version = None
    lock = _read_json(workspace / "package-lock.json")
    lockfile_schema_version = lock.get("lockfileVersion") if lock is not None else None
    lock_packages = (lock or {}).get("packages") if lock is not None else {}
    if lock is None:
        violations.append("package-lock.json is missing or invalid")
    elif not isinstance(lockfile_schema_version, int) or lockfile_schema_version < 3:
        violations.append(
            f"package-lock.json lockfileVersion={lockfile_schema_version} is not v3; "
            "resolved package entries cannot be verified"
        )
    else:
        lock_packages = lock_packages if isinstance(lock_packages, dict) else {}
        root_entry = lock_packages.get("")
        if not isinstance(root_entry, dict):
            violations.append('package-lock.json packages[""] root entry is missing')
        else:
            root_section = root_entry.get(section)
            if not isinstance(root_section, dict) or package not in root_section:
                violations.append(
                    f'package-lock.json packages[""][{section}][{package}] is missing'
                )
            else:
                lockfile_manifest_value = root_section[package]
                if lockfile_manifest_value != approved_version_spec:
                    violations.append(
                        f'package-lock.json packages[""][{section}].{package}='
                        f"{json.dumps(lockfile_manifest_value)}; "
                        f"expected approved spec={approved_version_spec}"
                    )
        lock_entry = lock_packages.get(f"node_modules/{package}")
        if not isinstance(lock_entry, dict):
            violations.append(
                f'package-lock.json packages["node_modules/{package}"] entry is missing'
            )
        elif not is_exact_version(lock_entry.get("version")):
            violations.append(
                f"package-lock.json node_modules/{package} has no exact resolved version"
            )
        else:
            resolved_exact_version = lock_entry["version"]
    installed_version = None
    installed = _read_json(workspace / "node_modules" / package / "package.json")
    if installed is None:
        violations.append(f"node_modules/{package}/package.json is missing or invalid")
    else:
        installed_version = installed.get("version")
        if not is_exact_version(installed_version):
            violations.append(
                f"node_modules/{package} has no exact installed version"
            )
        elif resolved_exact_version is not None and installed_version != resolved_exact_version:
            violations.append(
                f"installed {package} version={json.dumps(installed_version)}; "
                f"expected lockfile resolved version={json.dumps(resolved_exact_version)}"
            )
    return {
        "package": package,
        "section": section,
        "approved_version_spec": approved_version_spec,
        "manifest_value": manifest_value,
        "lockfile_manifest_value": lockfile_manifest_value,
        "resolved_exact_version": resolved_exact_version,
        "installed_version": installed_version,
        "agreement": not violations,
        "violations": violations,
    }


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
    workspace: Path,
    *,
    target_major: int,
    required_packages: tuple[str, ...],
    exact_versions: dict[str, str] | None = None,
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
    exact_versions = exact_versions or {}
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
        expected_exact = exact_versions.get(package)
        agreement = (
            manifest_range == expected_exact
            and lockfile_range == expected_exact
            and lockfile_version == expected_exact
            and installed_version == expected_exact
            if expected_exact is not None
            else
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
            "expected_exact": expected_exact,
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
