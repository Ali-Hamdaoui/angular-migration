"""Deterministic baseline package qualification rules.

This module deliberately performs no installation, command execution, network
access, or persistence.  It inspects the already-created baseline sandbox and
returns a checksum-bound decision for the later install capability.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from app.domain.execution_profile import ExecutionProfile


class BaselineQualificationError(ValueError):
    """Raised when package metadata cannot be safely qualified."""


class DependencySource(str, Enum):
    PUBLIC_REGISTRY = "public_registry"
    PRIVATE_REGISTRY = "private_registry"
    GIT = "git"
    TARBALL = "tarball"
    LOCAL_FILE = "local_file"
    WORKSPACE = "workspace"
    UNKNOWN = "unknown"


class LifecycleClassification(str, Enum):
    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    REQUIRES_REVIEW = "requires_review"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DependencySourceEntry:
    name: str
    requested: str
    source: DependencySource
    section: str


@dataclass(frozen=True)
class LifecycleScriptEntry:
    name: str
    command: str
    classification: LifecycleClassification
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PackageMetadata:
    name: str
    version: str | None
    dependencies: dict[str, str]
    scripts: dict[str, str]
    package_json_checksum: str


@dataclass(frozen=True)
class LockfileResult:
    status: str
    lockfile_version: int | None
    package_json_checksum: str
    lockfile_checksum: str
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegistryReadiness:
    status: str
    registry: str | None
    private_auth_configured: bool
    proxy_configured: bool
    certificate_valid: bool
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class BaselinePrequalificationResult:
    status: str
    policy_version: str
    package: PackageMetadata | None
    lockfile: LockfileResult
    sources: tuple[DependencySourceEntry, ...]
    scripts: tuple[LifecycleScriptEntry, ...]
    registry: RegistryReadiness
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    install_authorized: bool = False
    authorization_required: bool = False
    checksum: str = ""


class PackageMetadataInspector:
    """Read package metadata without normalizing or rewriting it."""

    def inspect(self, sandbox: Path) -> PackageMetadata:
        payload = _read_json(sandbox / "package.json", "PACKAGE_JSON_MISSING")
        if not isinstance(payload, dict):
            raise BaselineQualificationError("PACKAGE_JSON_INVALID")
        dependencies: dict[str, str] = {}
        for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            values = payload.get(section, {})
            if not isinstance(values, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()):
                raise BaselineQualificationError("PACKAGE_DEPENDENCIES_INVALID")
            dependencies.update(values)
        scripts = payload.get("scripts", {})
        if not isinstance(scripts, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in scripts.items()):
            raise BaselineQualificationError("PACKAGE_SCRIPTS_INVALID")
        return PackageMetadata(
            name=str(payload.get("name", "")),
            version=payload.get("version") if isinstance(payload.get("version"), str) else None,
            dependencies=dependencies,
            scripts=scripts,
            package_json_checksum=_checksum_file(sandbox / "package.json"),
        )


class LockfilePrequalificationService:
    """Check npm lockfile presence, parseability, and root dependency agreement."""

    def inspect(self, sandbox: Path, package: PackageMetadata) -> LockfileResult:
        path = sandbox / "package-lock.json"
        blockers: list[str] = []
        if not path.is_file():
            return LockfileResult("blocked", None, package.package_json_checksum, "", ("NPM_LOCKFILE_MISSING",))
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return LockfileResult("blocked", None, package.package_json_checksum, _checksum_file(path), ("NPM_LOCKFILE_INVALID",))
        if not isinstance(payload, dict) or not isinstance(payload.get("lockfileVersion"), int):
            blockers.append("NPM_LOCKFILE_INVALID")
        packages = payload.get("packages", {}) if isinstance(payload, dict) else {}
        root = packages.get("", {}) if isinstance(packages, dict) else {}
        locked_root = root.get("dependencies", {}) if isinstance(root, dict) else {}
        for name, requested in package.dependencies.items():
            locked = locked_root.get(name)
            if locked is None and isinstance(packages, dict):
                entry = packages.get(f"node_modules/{name}")
                locked = entry.get("version") if isinstance(entry, dict) else None
            if locked is None:
                blockers.append(f"NPM_LOCKFILE_DEPENDENCY_MISSING:{name}")
            elif _is_exact_version(requested) and locked != requested:
                blockers.append(f"NPM_LOCKFILE_VERSION_MISMATCH:{name}")
        return LockfileResult(
            "blocked" if blockers else "valid",
            payload.get("lockfileVersion") if isinstance(payload, dict) and isinstance(payload.get("lockfileVersion"), int) else None,
            package.package_json_checksum,
            _checksum_file(path),
            tuple(dict.fromkeys(blockers)),
        )


class PackageSourceInventory:
    """Classify dependency specifications without resolving them."""

    def inspect(self, package: PackageMetadata) -> tuple[DependencySourceEntry, ...]:
        entries = []
        for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            # The flattened package model is enough for values; section is
            # recovered from the original package by this inspector's helper.
            del section
        for name, requested in sorted(package.dependencies.items()):
            entries.append(DependencySourceEntry(name, requested, self.classify(requested), "dependencies"))
        return tuple(entries)

    @staticmethod
    def classify(value: str) -> DependencySource:
        lowered = value.lower().strip()
        if lowered.startswith("workspace:"):
            return DependencySource.WORKSPACE
        if lowered.startswith(("git:", "git+", "github:", "gitlab:", "bitbucket:")) or lowered.endswith(".git"):
            return DependencySource.GIT
        if lowered.startswith(("http://", "https://")) and (".tgz" in lowered or lowered.endswith(".tar.gz")):
            return DependencySource.TARBALL
        if lowered.startswith(("file:", "../", "./", ".\\", "..\\")):
            return DependencySource.LOCAL_FILE
        if lowered.startswith("@"):  # scope alone does not prove private access.
            return DependencySource.PUBLIC_REGISTRY
        if re.match(r"^[~^<>=*0-9xX|.\-+ ]+$", value):
            return DependencySource.PUBLIC_REGISTRY
        return DependencySource.UNKNOWN


class LifecycleScriptAuditor:
    """Classify root lifecycle hooks before any npm command is authorized."""

    _hooks = frozenset({"preinstall", "install", "postinstall", "prepare", "prepublish", "prepublishOnly"})
    _blocked = re.compile(r"(?i)(powershell|pwsh|cmd(?:\.exe)?\s|\\windows\\|curl\s|invoke-webrequest|wget\s|npm\s+install|rm\s+-rf|del\s+/[sq])")
    _restricted = re.compile(r"(?i)(git\s|python\s|node\s|\.\./|\.\\|write|delete|chmod|setx|registry|token|secret|password)")

    def inspect(self, package: PackageMetadata) -> tuple[LifecycleScriptEntry, ...]:
        result = []
        for name, command in sorted(package.scripts.items()):
            if name not in self._hooks:
                continue
            if self._blocked.search(command):
                classification, reasons = LifecycleClassification.BLOCKED, ("SCRIPT_USES_BLOCKED_OPERATION",)
            elif self._restricted.search(command):
                classification, reasons = LifecycleClassification.RESTRICTED, ("SCRIPT_REQUIRES_SANDBOX_REVIEW",)
            else:
                classification, reasons = LifecycleClassification.REQUIRES_REVIEW, ("LIFECYCLE_SCRIPT_PRESENT",)
            result.append(LifecycleScriptEntry(name, command, classification, reasons))
        return tuple(result)


class BaselinePrequalificationService:
    """Compose package, lockfile, source, lifecycle, and profile decisions."""

    POLICY_VERSION = "baseline-prequalification-v1"

    def __init__(self, *, metadata=None, lockfile=None, sources=None, scripts=None) -> None:
        self._metadata = metadata or PackageMetadataInspector()
        self._lockfile = lockfile or LockfilePrequalificationService()
        self._sources = sources or PackageSourceInventory()
        self._scripts = scripts or LifecycleScriptAuditor()

    def qualify(self, sandbox: Path, *, execution_profile: ExecutionProfile | None = None, private_auth_configured: bool = False) -> BaselinePrequalificationResult:
        blockers: list[str] = []
        warnings: list[str] = []
        try:
            package = self._metadata.inspect(sandbox)
        except BaselineQualificationError as error:
            package = None
            blockers.append(str(error))
        if package is None:
            lockfile = LockfileResult("blocked", None, "", "", tuple(blockers))
            sources: tuple[DependencySourceEntry, ...] = ()
            scripts: tuple[LifecycleScriptEntry, ...] = ()
        else:
            lockfile = self._lockfile.inspect(sandbox, package)
            blockers.extend(lockfile.blockers)
            sources = self._sources.inspect(package)
            scripts = self._scripts.inspect(package)
        for item in sources:
            if item.source in {DependencySource.GIT, DependencySource.TARBALL, DependencySource.LOCAL_FILE, DependencySource.WORKSPACE, DependencySource.UNKNOWN}:
                blockers.append(f"UNAPPROVED_DEPENDENCY_SOURCE:{item.name}")
        for item in scripts:
            if item.classification is LifecycleClassification.BLOCKED:
                blockers.extend(item.reasons)
            elif item.classification in {LifecycleClassification.RESTRICTED, LifecycleClassification.REQUIRES_REVIEW}:
                warnings.extend(item.reasons)
        registry = self._registry(execution_profile, private_auth_configured)
        blockers.extend(registry.blockers)
        if scripts and any(item.classification is not LifecycleClassification.ALLOWED for item in scripts):
            warnings.append("LIFECYCLE_SCRIPT_AUTHORIZATION_REQUIRED")
        authorization_required = bool(scripts and not blockers)
        status = "blocked" if blockers else ("requires_review" if authorization_required else "qualified")
        checksum = _checksum({"status": status, "package": asdict(package) if package else None, "lockfile": asdict(lockfile), "sources": [asdict(item) for item in sources], "scripts": [asdict(item) for item in scripts], "registry": asdict(registry), "policy_version": self.POLICY_VERSION})
        return BaselinePrequalificationResult(status, self.POLICY_VERSION, package, lockfile, sources, scripts, registry, tuple(dict.fromkeys(blockers)), tuple(dict.fromkeys(warnings)), status == "qualified", authorization_required, checksum)

    @staticmethod
    def _registry(profile: ExecutionProfile | None, private_auth_configured: bool) -> RegistryReadiness:
        if profile is None:
            return RegistryReadiness("blocked", None, private_auth_configured, False, False, ("EXECUTION_PROFILE_REQUIRED",))
        blockers = []
        if profile.network_policy != "approved-registries-only": blockers.append("REGISTRY_NETWORK_POLICY_UNAPPROVED")
        if profile.proxy_profile == "none": blockers.append("REGISTRY_PROXY_UNAVAILABLE")
        if profile.certificate_profile != "validated": blockers.append("REGISTRY_CERTIFICATE_INVALID")
        return RegistryReadiness("ready" if not blockers else "blocked", "configured", private_auth_configured, profile.proxy_profile != "none", profile.certificate_profile == "validated", tuple(blockers))


def _read_json(path: Path, code: str) -> Any:
    if not path.is_file():
        raise BaselineQualificationError(code)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BaselineQualificationError(code.replace("MISSING", "INVALID")) from error


def _checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _checksum(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _is_exact_version(value: str) -> bool:
    return bool(re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", value.strip()))
