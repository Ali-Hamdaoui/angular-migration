"""Lockfile dependency-set compatibility contracts (V2 F08 / V2.2 P0-2).

A parsed package-lock.json dependency set is validated deterministically against
the compatibility catalogue for a stage's target Angular major.  Pure domain:
no database, network, or LLM side effects.  Filesystem reads are confined to
authority selection and reader construction over an explicit workspace path.

V2.2 P0-2 adds the one canonical npm-capability-aware lock authority selector
(``LockfileAuthorityPolicy``/``select_lockfile_authority``), the section-aware
root-requested-intent contract (``DependencyIntent``), and the single V1/V2/V3
resolved-state reader (``PackageLockReader``).  Transformer services never
choose lock filenames or inspect ``packages[""]`` directly.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from pathlib import Path
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.execution_profile import Version


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _payload_checksum(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class LockfileDependencySet(_ImmutableModel):
    """The resolved dependency set frozen by a package-lock.json.

    ``top_level_resolved`` holds exact resolved versions only.  Historical
    serialized evidence using the pre-rename ``root_dependencies`` field is
    mapped into ``top_level_resolved`` on read; it is never treated as
    requested root intent.
    """

    lockfile_version: int | None = None
    top_level_resolved: dict[str, str] = Field(default_factory=dict)
    resolved_packages: dict[str, str] = Field(default_factory=dict)  # name -> resolved version
    checksum: str = ""

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_root_field(cls, data):
        if isinstance(data, dict) and "root_dependencies" in data and "top_level_resolved" not in data:
            # Map the pre-rename serialized field into its successor and strip
            # the legacy key so extra="forbid" accepts historical records.
            mapped = {key: value for key, value in data.items() if key != "root_dependencies"}
            mapped["top_level_resolved"] = data.get("root_dependencies") or {}
            return mapped
        return data

    @property
    def root_dependencies(self) -> dict[str, str]:
        """Deprecated read-compat alias; exact resolved versions only."""
        return self.top_level_resolved

    def resolved_version(self, name: str) -> str | None:
        if name in self.resolved_packages:
            return self.resolved_packages[name]
        return self.top_level_resolved.get(name)


class LockfileCompatibilityFinding(_ImmutableModel):
    """One deterministic compatibility finding for a resolved package."""

    package: str
    expected: str | None = None
    resolved: str | None = None
    status: str  # "ok" | "mismatch" | "missing"
    detail: str = ""


class LockfileCompatibilityVerdict(_ImmutableModel):
    """Deterministic validation result for a lockfile against a stage target."""

    source_family: str
    target_family: str
    status: str  # "valid" | "blocked"
    findings: tuple[LockfileCompatibilityFinding, ...] = ()
    blockers: tuple[str, ...] = ()


def version_satisfies(
    resolved: str | None,
    expected: str | None,
    *,
    minimum: str | None = None,
    exclusive_maximum: str | None = None,
    allowed_ranges: tuple[str, ...] | None = None,
) -> bool:
    """Resolved version satisfies an exact expectation, a semver minimum, an
    exclusive maximum, or an allowed caret-range alternative set."""
    if resolved is None:
        return False
    parsed = Version.parse(resolved)
    if parsed is None:
        return False
    if expected is not None:
        return resolved == expected
    if allowed_ranges is not None:
        if not _satisfies_any(parsed, allowed_ranges):
            return False
        # When alternatives are authoritative, still enforce minimum/maximum if
        # provided (defensive; RxJS uses alternatives only, TS uses min/max).
        if minimum is not None:
            minimum_parsed = Version.parse(minimum)
            if minimum_parsed is None or not parsed.at_least(minimum_parsed):
                return False
        if exclusive_maximum is not None:
            max_parsed = Version.parse(exclusive_maximum)
            if max_parsed is None or parsed.at_least(max_parsed):
                return False
        return True
    if minimum is not None:
        minimum_parsed = Version.parse(minimum)
        if minimum_parsed is None or not parsed.at_least(minimum_parsed):
            return False
    if exclusive_maximum is not None:
        max_parsed = Version.parse(exclusive_maximum)
        if max_parsed is None or parsed.at_least(max_parsed):
            return False
    return True


def _satisfies_caret(version: Version, value: str) -> bool:
    if not value.startswith("^"):
        return False
    minimum = Version.parse(value[1:])
    return bool(minimum and version.at_least(minimum) and version.major == minimum.major)


def _satisfies_any(version: Version, ranges: tuple[str, ...]) -> bool:
    return any(_satisfies_caret(version, v) for v in ranges)


def evaluate_lockfile_compatibility(
    dependency_set: LockfileDependencySet,
    *,
    source_family: str,
    target_family: str,
    catalogue_expected: dict[str, str | None],
    catalogue_minimums: dict[str, str],
    catalogue_exclusive_maximums: dict[str, str] | None = None,
    catalogue_allowed_ranges: dict[str, tuple[str, ...]] | None = None,
) -> LockfileCompatibilityVerdict:
    """Validate the resolved dependency set against catalogue expectations.

    ``catalogue_expected`` maps package name -> exact expected version (when the
    catalogue pins one).  ``catalogue_minimums`` maps package name -> minimum
    version for packages the catalogue constrains by a floor.
    ``catalogue_exclusive_maximums`` maps package -> exclusive upper bound
    (``<max``).  ``catalogue_allowed_ranges`` maps package -> tuple of caret
    alternatives (e.g. RxJS ``^6.5.3`` || ``^7.4.0``).
    """
    findings: list[LockfileCompatibilityFinding] = []
    blockers: list[str] = []
    catalogue_exclusive_maximums = catalogue_exclusive_maximums or {}
    catalogue_allowed_ranges = catalogue_allowed_ranges or {}
    packages = set(catalogue_expected) | set(catalogue_minimums) | set(catalogue_exclusive_maximums) | set(catalogue_allowed_ranges)
    for package in sorted(packages):
        resolved = dependency_set.resolved_version(package)
        expected = catalogue_expected.get(package)
        minimum = catalogue_minimums.get(package)
        exclusive_maximum = catalogue_exclusive_maximums.get(package)
        allowed_ranges = catalogue_allowed_ranges.get(package)
        if resolved is None:
            findings.append(
                LockfileCompatibilityFinding(package=package, expected=expected, resolved=None, status="missing", detail="package not present in lockfile dependency set")
            )
            blockers.append(f"LOCKFILE_DEPENDENCY_MISSING:{package}")
            continue
        if version_satisfies(resolved, expected, minimum=minimum, exclusive_maximum=exclusive_maximum, allowed_ranges=allowed_ranges):
            findings.append(
                LockfileCompatibilityFinding(package=package, expected=expected, resolved=resolved, status="ok", detail="resolved version satisfies catalogue constraint")
            )
        else:
            display_expected: str | None = expected
            if display_expected is None and allowed_ranges:
                display_expected = " || ".join(allowed_ranges)
            elif display_expected is None and minimum and exclusive_maximum:
                display_expected = f">={minimum} <{exclusive_maximum}"
            elif display_expected is None:
                display_expected = minimum or exclusive_maximum
            findings.append(
                LockfileCompatibilityFinding(
                    package=package, expected=display_expected, resolved=resolved,
                    status="mismatch", detail=f"resolved {resolved} does not satisfy catalogue constraint",
                )
            )
            blockers.append(f"LOCKFILE_VERSION_INCOMPATIBLE:{package}")
    return LockfileCompatibilityVerdict(
        source_family=source_family,
        target_family=target_family,
        status="blocked" if blockers else "valid",
        findings=tuple(findings),
        blockers=tuple(dict.fromkeys(blockers)),
    )


# ---------------------------------------------------------------------------
# V2.2 P0-2 — npm-capability lock authority, section-aware intent, and the
# one canonical V1/V2/V3 resolved-state reader.
# ---------------------------------------------------------------------------


class LockfileAuthorityError(ValueError):
    """Fail-closed lock authority selection error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PackageLockError(ValueError):
    """Fail-closed canonical lock read error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DependencyIntentKind(str, Enum):
    REQUIRED = "REQUIRED"
    DEV = "DEV"
    OPTIONAL = "OPTIONAL"
    PEER = "PEER"
    OPTIONAL_PEER = "OPTIONAL_PEER"


class DependencyIntent(_ImmutableModel):
    """Immutable section-preserving root requested-dependency intent.

    Built once from package.json; sections are never flattened before
    section-aware root-sync evaluation.  ``peerDependenciesMeta[package]
    .optional == true`` classifies that peer as ``OPTIONAL_PEER``.
    """

    schema_version: Literal["dependency-intent-v1"] = "dependency-intent-v1"
    dependencies: Mapping[str, str] = Field(default_factory=dict)
    dev_dependencies: Mapping[str, str] = Field(default_factory=dict)
    optional_dependencies: Mapping[str, str] = Field(default_factory=dict)
    peer_dependencies: Mapping[str, str] = Field(default_factory=dict)
    peer_dependencies_meta: Mapping[str, Mapping[str, object]] = Field(default_factory=dict)
    checksum: str

    @classmethod
    def from_package_json(cls, payload: Mapping[str, object]) -> "DependencyIntent":
        sections: dict[str, object] = {}
        for key, source in (
            ("dependencies", "dependencies"),
            ("dev_dependencies", "devDependencies"),
            ("optional_dependencies", "optionalDependencies"),
            ("peer_dependencies", "peerDependencies"),
        ):
            values = payload.get(source, {})
            if not isinstance(values, dict) or any(
                not isinstance(name, str) or not isinstance(spec, str) for name, spec in values.items()
            ):
                raise PackageLockError("DEPENDENCY_INTENT_INVALID", f"package.json section {source} is invalid")
            sections[key] = dict(values)
        meta = payload.get("peerDependenciesMeta", {})
        if not isinstance(meta, dict) or any(
            not isinstance(name, str) or not isinstance(value, dict) for name, value in meta.items()
        ):
            raise PackageLockError("DEPENDENCY_INTENT_INVALID", "package.json peerDependenciesMeta is invalid")
        sections["peer_dependencies_meta"] = {name: dict(value) for name, value in meta.items()}
        checksum = _payload_checksum({k: v for k, v in sections.items()})
        return cls(**sections, checksum=checksum)  # type: ignore[arg-type]

    @model_validator(mode="after")
    def bind_checksum(self) -> "DependencyIntent":
        payload = {
            "dependencies": dict(self.dependencies),
            "dev_dependencies": dict(self.dev_dependencies),
            "optional_dependencies": dict(self.optional_dependencies),
            "peer_dependencies": dict(self.peer_dependencies),
            "peer_dependencies_meta": {k: dict(v) for k, v in self.peer_dependencies_meta.items()},
        }
        expected = _payload_checksum(payload)
        if self.checksum != expected:
            raise ValueError("dependency intent checksum does not bind its sections")
        return self

    def kind_for(self, package: str, section: str) -> DependencyIntentKind:
        if section == "peerDependencies":
            meta = self.peer_dependencies_meta.get(package) or {}
            if meta.get("optional") is True:
                return DependencyIntentKind.OPTIONAL_PEER
            return DependencyIntentKind.PEER
        return {
            "dependencies": DependencyIntentKind.REQUIRED,
            "devDependencies": DependencyIntentKind.DEV,
            "optionalDependencies": DependencyIntentKind.OPTIONAL,
            "peerDependencies": DependencyIntentKind.PEER,
        }.get(section, DependencyIntentKind.REQUIRED)

    def iter_section(self, section: str) -> tuple[tuple[str, str], ...]:
        values = {
            "dependencies": self.dependencies,
            "devDependencies": self.dev_dependencies,
            "optionalDependencies": self.optional_dependencies,
            "peerDependencies": self.peer_dependencies,
        }.get(section, {})
        return tuple(sorted((name, spec) for name, spec in values.items()))


class LockfileAuthorityPolicy(_ImmutableModel):
    """Package-manager capability policy selected by the bound exact npm."""

    npm_exact_version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
    npm_major: int = Field(ge=0)
    shrinkwrap_behavior: Literal["PREFERRED", "UNSUPPORTED"]
    unsupported_shrinkwrap_action: Literal["BLOCK", "IGNORE_WITH_PACKAGE_LOCK", "MIGRATE_AND_REMOVE"] | None
    peer_auto_install: Literal["NOT_AUTOMATIC", "NPM_SOLVER"]
    optional_peer_absence_allowed: bool
    optional_dependency_omission: Literal["ALLOWED_WITH_NPM_EVIDENCE", "DEFER_TO_NPM"]
    dev_dependencies_required: bool
    policy_version: str
    checksum: str

    @classmethod
    def build_for_npm(
        cls,
        npm_exact_version: str,
        *,
        unsupported_shrinkwrap_action: Literal[
            "BLOCK", "IGNORE_WITH_PACKAGE_LOCK", "MIGRATE_AND_REMOVE"
        ]
        | None = None,
    ) -> "LockfileAuthorityPolicy":
        """Deterministic capability policy for one bound exact npm version."""
        match = re.fullmatch(r"(\d+)\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", npm_exact_version.strip())
        if match is None:
            raise LockfileAuthorityError(
                "LOCK_AUTHORITY_POLICY_UNSUPPORTED",
                f"cannot derive npm major from {npm_exact_version!r}",
            )
        major = int(match.group(1))
        if 6 <= major <= 11:
            fields = dict(
                shrinkwrap_behavior="PREFERRED",
                unsupported_shrinkwrap_action=None,
                peer_auto_install="NOT_AUTOMATIC" if major <= 6 else "NPM_SOLVER",
                optional_peer_absence_allowed=True,
                optional_dependency_omission="ALLOWED_WITH_NPM_EVIDENCE",
                dev_dependencies_required=True,
                policy_version="lockfile-authority-policy-v1",
            )
        elif major >= 12:
            if unsupported_shrinkwrap_action is None:
                raise LockfileAuthorityError(
                    "LOCK_AUTHORITY_POLICY_UNSUPPORTED",
                    "npm 12+ requires an explicit unsupported-shrinkwrap action",
                )
            fields = dict(
                shrinkwrap_behavior="UNSUPPORTED",
                unsupported_shrinkwrap_action=unsupported_shrinkwrap_action,
                peer_auto_install="NPM_SOLVER",
                optional_peer_absence_allowed=True,
                optional_dependency_omission="ALLOWED_WITH_NPM_EVIDENCE",
                dev_dependencies_required=True,
                policy_version="lockfile-authority-policy-v1",
            )
        else:
            raise LockfileAuthorityError(
                "LOCK_AUTHORITY_POLICY_UNSUPPORTED",
                f"npm major {major} has no governed lockfile authority policy",
            )
        checksum_payload = {"npm_exact_version": npm_exact_version, "npm_major": major, **fields}
        checksum = _payload_checksum(checksum_payload)
        return cls(npm_exact_version=npm_exact_version, npm_major=major, checksum=checksum, **fields)  # type: ignore[arg-type]


class LockfileAuthority(_ImmutableModel):
    """The single selected authoritative lockfile for a workspace."""

    path: Path
    kind: Literal["SHRINKWRAP", "PACKAGE_LOCK"]
    filename: Literal["npm-shrinkwrap.json", "package-lock.json"]
    lockfile_version: Literal[1, 2, 3]
    sha256: str
    policy_checksum: str


def select_lockfile_authority(workspace: Path, *, policy: LockfileAuthorityPolicy) -> LockfileAuthority:
    """Select exactly one authoritative lockfile under the bound npm capability.

    Deterministic and read-only.  npm 6-11 prefer ``npm-shrinkwrap.json`` over
    ``package-lock.json``; when both exist the shrinkwrap is the sole
    authority.  npm 12+ treats shrinkwrap as unsupported and honors only an
    explicit ``unsupported_shrinkwrap_action``.  A malformed or unsupported
    selected authority never falls through to another file.  A lone yarn.lock
    is never selected.
    """
    if policy.npm_major < 6 or (policy.npm_major >= 12 and policy.shrinkwrap_behavior != "UNSUPPORTED"):
        raise LockfileAuthorityError(
            "LOCK_AUTHORITY_POLICY_UNSUPPORTED",
            f"npm {policy.npm_exact_version} cannot select a lockfile authority",
        )
    shrinkwrap = workspace / "npm-shrinkwrap.json"
    package_lock = workspace / "package-lock.json"
    if shrinkwrap.is_file():
        if policy.shrinkwrap_behavior == "PREFERRED":
            return _build_authority(shrinkwrap, "SHRINKWRAP", "npm-shrinkwrap.json", policy)
        # npm 12+: shrinkwrap is unsupported.
        action = policy.unsupported_shrinkwrap_action
        if action == "IGNORE_WITH_PACKAGE_LOCK" and package_lock.is_file():
            return _build_authority(package_lock, "PACKAGE_LOCK", "package-lock.json", policy)
        if action == "MIGRATE_AND_REMOVE" and package_lock.is_file():
            return _build_authority(package_lock, "PACKAGE_LOCK", "package-lock.json", policy)
        raise LockfileAuthorityError(
            "SHRINKWRAP_UNSUPPORTED_BY_NPM",
            "npm-shrinkwrap.json is unsupported by the bound npm and no explicit migration policy authorizes a change",
        )
    if package_lock.is_file():
        return _build_authority(package_lock, "PACKAGE_LOCK", "package-lock.json", policy)
    raise LockfileAuthorityError("PACKAGE_LOCK_MISSING", "no authoritative npm lockfile is present")


def _build_authority(path: Path, kind, filename, policy: LockfileAuthorityPolicy) -> LockfileAuthority:
    raw = path.read_bytes()
    sha256 = "sha256:" + hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackageLockError("PACKAGE_LOCK_MALFORMED", f"{filename} is not valid JSON") from error
    version = payload.get("lockfileVersion") if isinstance(payload, dict) else None
    if not isinstance(version, int):
        raise PackageLockError("PACKAGE_LOCK_MALFORMED", f"{filename} lacks an integer lockfileVersion")
    if version not in {1, 2, 3}:
        raise PackageLockError("PACKAGE_LOCK_VERSION_UNSUPPORTED", f"lockfileVersion {version} is unsupported")
    return LockfileAuthority(
        path=path, kind=kind, filename=filename, lockfile_version=version,
        sha256=sha256, policy_checksum=policy.checksum,
    )


_EXACT_SPEC = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
_SIMPLE_CARET_SPEC = re.compile(r"^\^(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]+)?$")


def evaluate_static_spec(spec: str, resolved: str | None) -> str:
    """Bounded static registry-spec check.

    Only already-proven simple forms are evaluated (exact and simple caret);
    everything else returns ``DEFER_TO_NPM`` without guessing npm semver
    behavior.  An allowlisted spec with no resolution is an explicit
    ``MISMATCH`` (the caller distinguishes missing from version mismatch);
    result is an evaluation capability, not workflow success.
    """
    if _EXACT_SPEC.fullmatch(spec):
        if resolved is None:
            return "MISMATCH"
        return "VERIFIED" if resolved == spec else "MISMATCH"
    caret = _SIMPLE_CARET_SPEC.fullmatch(spec)
    if caret is None:
        return "DEFER_TO_NPM"
    if resolved is None:
        return "MISMATCH"
    resolved_parsed = Version.parse(resolved)
    lower = Version.parse(spec[1:])
    if resolved_parsed is None or lower is None:
        return "DEFER_TO_NPM"
    if not resolved_parsed.at_least(lower):
        return "MISMATCH"
    # npm caret semantics: ^x.y.z stays within x for x>0; ^0.y.z within 0.y;
    # ^0.0.z is patch-only.
    major, minor = int(caret.group(1)), int(caret.group(2))
    if major > 0:
        return "VERIFIED" if resolved_parsed.major == major else "MISMATCH"
    if minor > 0:
        return "VERIFIED" if resolved_parsed.major == 0 and resolved_parsed.minor == minor else "MISMATCH"
    return "VERIFIED" if (
        resolved_parsed.major == lower.major
        and resolved_parsed.minor == lower.minor
        and resolved_parsed.patch == lower.patch
    ) else "MISMATCH"


class RootSyncFinding(_ImmutableModel):
    """One immutable section-aware manifest-intent versus resolution finding."""

    package: str
    section: Literal["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"]
    kind: DependencyIntentKind
    peer_metadata: Mapping[str, object] | None = None
    requested_spec: str
    resolved_version: str | None = None
    npm_capability_policy_checksum: str
    static_result: Literal["STATIC_CHECK", "VERIFIED", "MISMATCH", "DEFER_TO_NPM"]
    status: str  # descriptive evidence, e.g. ROOT_REQUIRED_VERIFIED
    absence_semantics: str | None = None
    reason_code: str
    deferred_npm_evidence_ref: str | None = None


class LockfileRootSyncResult(_ImmutableModel):
    """Section-aware root-sync outcome over one DependencyIntent."""

    findings: tuple[RootSyncFinding, ...]
    status: Literal["synchronized", "deferred", "mismatched"]
    npm_capability_policy_checksum: str
    dependency_intent_checksum: str
    checksum: str

    @classmethod
    def create(
        cls,
        *,
        findings: tuple[RootSyncFinding, ...],
        status: Literal["synchronized", "deferred", "mismatched"],
        npm_capability_policy_checksum: str,
        dependency_intent_checksum: str,
    ) -> "LockfileRootSyncResult":
        payload = {
            "status": status,
            "npm_capability_policy_checksum": npm_capability_policy_checksum,
            "dependency_intent_checksum": dependency_intent_checksum,
            "findings": [finding.model_dump(mode="json") for finding in findings],
        }
        return cls(
            findings=findings,
            status=status,
            npm_capability_policy_checksum=npm_capability_policy_checksum,
            dependency_intent_checksum=dependency_intent_checksum,
            checksum=_payload_checksum(payload),
        )

    @model_validator(mode="after")
    def bind_checksum(self) -> "LockfileRootSyncResult":
        payload = {
            "status": self.status,
            "npm_capability_policy_checksum": self.npm_capability_policy_checksum,
            "dependency_intent_checksum": self.dependency_intent_checksum,
            "findings": [finding.model_dump(mode="json") for finding in self.findings],
        }
        expected = _payload_checksum(payload)
        if self.checksum != expected:
            raise ValueError("root sync result checksum does not bind its findings")
        return self


class PackageLockReader:
    """The single canonical V1/V2/V3 resolved-state reader.

    Callers receive the same resolved-state contract regardless of lockfile
    schema and never inspect either representation directly.  Original root
    requested ranges are never reconstructed from V1 data.
    """

    def __init__(self, authority: LockfileAuthority, payload: Mapping[str, object], raw_sha256: str) -> None:
        self._authority = authority
        self._payload = payload
        self._raw_sha256 = raw_sha256

    @classmethod
    def from_authority(cls, authority: LockfileAuthority) -> "PackageLockReader":
        try:
            raw = Path(authority.path).read_bytes()
        except OSError as error:
            raise PackageLockError("PACKAGE_LOCK_MISSING", f"authoritative lock unreadable: {authority.filename}") from error
        sha256 = "sha256:" + hashlib.sha256(raw).hexdigest()
        if sha256 != authority.sha256:
            raise PackageLockError(
                "PACKAGE_LOCK_MALFORMED",
                "authoritative lock bytes drifted from the selected authority checksum",
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PackageLockError("PACKAGE_LOCK_MALFORMED", f"{authority.filename} is not valid JSON") from error
        if not isinstance(payload, dict):
            raise PackageLockError("PACKAGE_LOCK_MALFORMED", f"{authority.filename} payload is not an object")
        reader = cls(authority, payload, sha256)
        reader.detect_version()
        return reader

    # -- identity -------------------------------------------------------

    @property
    def authority(self) -> LockfileAuthority:
        return self._authority

    def detect_version(self) -> Literal[1, 2, 3]:
        version = self._payload.get("lockfileVersion")
        if not isinstance(version, int) or version not in {1, 2, 3}:
            raise PackageLockError(
                "PACKAGE_LOCK_MALFORMED" if not isinstance(version, int) else "PACKAGE_LOCK_VERSION_UNSUPPORTED",
                f"unsupported lockfileVersion: {version!r}",
            )
        return version  # type: ignore[return-value]

    @property
    def raw_sha256(self) -> str:
        return self._raw_sha256

    # -- resolved state --------------------------------------------------

    def _packages(self) -> Mapping[str, object]:
        packages = self._payload.get("packages")
        return packages if isinstance(packages, dict) else {}

    def _v1_root(self) -> Mapping[str, object]:
        dependencies = self._payload.get("dependencies")
        return dependencies if isinstance(dependencies, dict) else {}

    @staticmethod
    def _entry_version(entry: object) -> str | None:
        if isinstance(entry, dict) and isinstance(entry.get("version"), str):
            return entry["version"]
        return None

    def top_level_resolved_version(self, package: str) -> str | None:
        packages = self._packages()
        if packages:
            entry = packages.get(f"node_modules/{package}")
            version = self._entry_version(entry)
            if version is not None:
                return version
        # V1: direct child of the root dependencies tree (scoped names are
        # single keys).  Never delegates back into nested resolution.
        return self._entry_version(self._v1_root().get(package))

    def resolved_version(self, package: str, *, parent_path: str | None = None) -> str | None:
        prefix = "" if not parent_path else parent_path.rstrip("/") + "/"
        packages = self._packages()
        if packages:
            entry = packages.get(f"{prefix}node_modules/{package}")
            version = self._entry_version(entry)
            if version is not None:
                return version
        return self._resolved_v1_nested(package, parent_path)

    def _resolved_v1_nested(self, package: str, parent_path: str | None) -> str | None:
        node = self._v1_root()
        names = self._v1_chain_names(parent_path)
        for name in names:
            entry = node.get(name) if isinstance(node, dict) else None
            node = entry.get("dependencies") if isinstance(entry, dict) and isinstance(entry.get("dependencies"), dict) else {}
        entry = node.get(package) if isinstance(node, dict) else None
        version = self._entry_version(entry)
        if version is not None:
            return version
        # npm hoisting: fall back toward strictly shorter ancestor chains,
        # then to the root; never re-enter with the identical query.
        for index in reversed(range(len(names))):
            ancestor = "node_modules/" + "/node_modules/".join(names[:index])
            candidate = self.resolved_version(package, parent_path=ancestor)
            if candidate is not None:
                return candidate
        return self.top_level_resolved_version(package)

    def dependency_edges(self, package: str, *, parent_path: str | None = None) -> Mapping[str, str]:
        """Resolved child versions of one installed package."""
        prefix = "" if not parent_path else parent_path.rstrip("/") + "/"
        packages = self._packages()
        edges: dict[str, str] = {}
        if packages:
            own_prefix = f"{prefix}node_modules/{package}"
            entry = packages.get(own_prefix)
            if isinstance(entry, dict) and isinstance(entry.get("dependencies"), dict):
                for child in sorted(entry["dependencies"]):
                    version = self.resolved_version(child, parent_path=own_prefix)
                    if version is not None:
                        edges[child] = version
                return edges
        v1_entry = self._v1_lookup_v1_node(package, parent_path)
        if isinstance(v1_entry, dict) and isinstance(v1_entry.get("dependencies"), dict):
            for child, spec in sorted(v1_entry["dependencies"].items()):
                version = self.resolved_version(child, parent_path=self._v1_child_parent(parent_path, package))
                if version is not None and (not isinstance(spec, str) or True):
                    edges[child] = version
        return edges

    def requested_edges(self, package: str, *, parent_path: str | None = None) -> Mapping[str, str]:
        """Declared requested specs of one installed package (never V1-root ranges).

        V2/V3 read the declaration mirror under ``packages``; V1 reads the
        entry's ``requires`` map.
        """
        prefix = "" if not parent_path else parent_path.rstrip("/") + "/"
        packages = self._packages()
        if packages:
            entry = packages.get(f"{prefix}node_modules/{package}")
            if isinstance(entry, dict) and isinstance(entry.get("dependencies"), dict):
                return {
                    name: spec
                    for name, spec in entry["dependencies"].items()
                    if isinstance(spec, str)
                }
        v1_entry = self._v1_lookup_v1_node(package, parent_path)
        if isinstance(v1_entry, dict):
            requires = v1_entry.get("requires")
            if isinstance(requires, dict):
                return {name: spec for name, spec in requires.items() if isinstance(spec, str)}
        return {}

    def integrity(self, package: str, *, parent_path: str | None = None) -> str | None:
        prefix = "" if not parent_path else parent_path.rstrip("/") + "/"
        packages = self._packages()
        if packages:
            entry = packages.get(f"{prefix}node_modules/{package}")
            if isinstance(entry, dict) and isinstance(entry.get("integrity"), str):
                return entry["integrity"]
        v1_entry = self._v1_lookup_v1_node(package, parent_path)
        if isinstance(v1_entry, dict) and isinstance(v1_entry.get("integrity"), str):
            return v1_entry["integrity"]
        return None

    def package_exists(self, package: str, *, parent_path: str | None = None) -> bool:
        return self.resolved_version(package, parent_path=parent_path) is not None

    def _v1_lookup_v1_node(self, package: str, parent_path: str | None):
        node = self._v1_root()
        names = self._v1_chain_names(parent_path)
        for name in names:
            entry = node.get(name) if isinstance(node, dict) else None
            node = entry.get("dependencies") if isinstance(entry, dict) and isinstance(entry.get("dependencies"), dict) else {}
        return node.get(package) if isinstance(node, dict) else None

    @staticmethod
    def _v1_chain_names(parent_path: str | None) -> list[str]:
        """Package names along a V1 parent path; scoped names keep their slash."""
        if not parent_path:
            return []
        parts = [part for part in parent_path.split("/") if part]
        names: list[str] = []
        index = 0
        while index < len(parts):
            part = parts[index]
            if part == "node_modules":
                index += 1
                continue
            if part.startswith("@") and index + 1 < len(parts):
                names.append(part + "/" + parts[index + 1])
                index += 2
            else:
                names.append(part)
                index += 1
        return names

    @staticmethod
    def _v1_child_parent(parent_path: str | None, package: str) -> str | None:
        base = (parent_path or "").rstrip("/")
        return f"{base}/node_modules/{package}" if base else f"node_modules/{package}"

    # -- aggregate set ----------------------------------------------------

    def dependency_set(self) -> LockfileDependencySet:
        top_level: dict[str, str] = {}
        resolved: dict[str, str] = {}
        packages = self._packages()
        if packages:
            for key, entry in sorted(packages.items()):
                if not isinstance(key, str) or not key.startswith("node_modules/"):
                    continue
                name = key[len("node_modules/"):]
                version = self._entry_version(entry)
                if version is None:
                    continue
                if "/" not in name:
                    top_level.setdefault(name, version)
                    resolved.setdefault(name, version)
                elif name.startswith("@") and name.count("/") == 1:
                    top_level.setdefault(name, version)
                    resolved.setdefault(name, version)
                else:
                    resolved.setdefault(name.rsplit("/", 1)[-1] if not name.startswith("@") else name, version)
                    resolved.setdefault(name, version)
        else:
            def walk(node: object, depth: int) -> None:
                if not isinstance(node, dict):
                    return
                for name, entry in node.items():
                    if not isinstance(entry, dict):
                        continue
                    version = self._entry_version(entry)
                    if version is not None:
                        resolved.setdefault(name, version)
                        if depth == 0:
                            top_level.setdefault(name, version)
                    walk(entry.get("dependencies"), depth + 1)

            walk(self._v1_root(), 0)
        payload = {
            "lockfile_version": self.detect_version(),
            "top_level_resolved": top_level,
            "resolved_packages": resolved,
        }
        return LockfileDependencySet(
            lockfile_version=payload["lockfile_version"],
            top_level_resolved=top_level,
            resolved_packages=resolved,
            checksum=_payload_checksum(payload),
        )

    # -- section-aware root sync -------------------------------------------

    def root_sync_with_manifest(
        self,
        dependency_intent: DependencyIntent,
        npm_capability_policy: LockfileAuthorityPolicy,
        *,
        npm_evidence: Mapping[str, object] | None = None,
    ) -> LockfileRootSyncResult:
        """Prove manifest intent against resolved state without becoming an npm solver.

        Required/dev entries must materialize; optional and optional-peer
        absence follow their governed semantics; npm<=6 peer absence is not an
        ordinary mismatch; npm7+ peer outcomes defer to bound npm evidence.  A
        contradictory npm tree overrides any permissive static finding.
        """
        evidence = dict(npm_evidence or {})
        tree_invalid = bool(evidence.get("dependency_tree_invalid"))
        findings: list[RootSyncFinding] = []
        for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            for package, spec in dependency_intent.iter_section(section):
                kind = dependency_intent.kind_for(package, section)
                resolved = self.top_level_resolved_version(package)
                static = evaluate_static_spec(spec, resolved)
                finding = self._classify_finding(
                    package=package, section=section, kind=kind, spec=spec,
                    resolved=resolved, static=static, policy=npm_capability_policy,
                    intent=dependency_intent, evidence=evidence, tree_invalid=tree_invalid,
                )
                findings.append(finding)
        has_mismatch = any(finding.static_result == "MISMATCH" for finding in findings)
        has_deferred = any(finding.static_result in {"DEFER_TO_NPM", "STATIC_CHECK"} for finding in findings)
        status = "mismatched" if has_mismatch else ("deferred" if has_deferred else "synchronized")
        return LockfileRootSyncResult.create(
            findings=tuple(findings),
            status=status,  # type: ignore[arg-type]
            npm_capability_policy_checksum=npm_capability_policy.checksum,
            dependency_intent_checksum=dependency_intent.checksum,
        )

    def _classify_finding(
        self,
        *,
        package: str,
        section: str,
        kind: DependencyIntentKind,
        spec: str,
        resolved: str | None,
        static: str,
        policy: LockfileAuthorityPolicy,
        intent: DependencyIntent,
        evidence: Mapping[str, object],
        tree_invalid: bool,
    ) -> RootSyncFinding:
        deferred_ref = evidence.get("evidence_ref")
        deferred_ref = deferred_ref if isinstance(deferred_ref, str) else None
        base = dict(
            package=package,
            section=section,  # type: ignore[arg-type]
            kind=kind,
            peer_metadata=dict(intent.peer_dependencies_meta.get(package)) if intent.peer_dependencies_meta.get(package) else None,
            requested_spec=spec,
            resolved_version=resolved,
            npm_capability_policy_checksum=policy.checksum,
        )
        if tree_invalid:
            return RootSyncFinding(**base, static_result="MISMATCH", status="ROOT_CONTRADICTED_BY_NPM_TREE", reason_code="NPM_TREE_INVALID", deferred_npm_evidence_ref=deferred_ref)
        absent = resolved is None
        if kind is DependencyIntentKind.REQUIRED:
            if static == "DEFER_TO_NPM":
                return RootSyncFinding(**base, static_result="DEFER_TO_NPM", status="ROOT_REQUIRED_DEFERRED_TO_NPM", reason_code="SPEC_NOT_STATICALLY_EVALUABLE", deferred_npm_evidence_ref=deferred_ref)
            if static == "VERIFIED":
                return RootSyncFinding(**base, static_result="VERIFIED", status="ROOT_REQUIRED_VERIFIED", reason_code="ROOT_REQUIRED_SATISFIED")
            missing = absent
            return RootSyncFinding(**base, static_result="MISMATCH", status="ROOT_REQUIRED_MISSING_RESOLUTION" if missing else "ROOT_REQUIRED_VERSION_MISMATCH", reason_code="REQUIRED_UNRESOLVED" if missing else "REQUIRED_INCOMPATIBLE")
        if kind is DependencyIntentKind.DEV:
            if static == "DEFER_TO_NPM":
                return RootSyncFinding(**base, static_result="DEFER_TO_NPM", status="ROOT_DEV_DEFERRED_TO_NPM", reason_code="SPEC_NOT_STATICALLY_EVALUABLE", deferred_npm_evidence_ref=deferred_ref)
            if static == "VERIFIED":
                return RootSyncFinding(**base, static_result="VERIFIED", status="ROOT_DEV_VERIFIED", reason_code="ROOT_DEV_SATISFIED")
            missing = absent
            return RootSyncFinding(**base, static_result="MISMATCH", status="ROOT_DEV_MISSING_RESOLUTION" if missing else "ROOT_DEV_VERSION_MISMATCH", reason_code="DEV_UNRESOLVED" if missing else "DEV_INCOMPATIBLE")
        if kind is DependencyIntentKind.OPTIONAL:
            if absent:
                omission_evidence = evidence.get("optional_omission_evidence")
                if policy.optional_dependency_omission == "ALLOWED_WITH_NPM_EVIDENCE" and isinstance(omission_evidence, str) and omission_evidence:
                    return RootSyncFinding(**base, static_result="STATIC_CHECK", status="ROOT_OPTIONAL_ABSENT_ALLOWED", absence_semantics="OPTIONAL_ABSENT_ALLOWED_WITH_NPM_EVIDENCE", reason_code="OPTIONAL_OMISSION_EVIDENCED", deferred_npm_evidence_ref=omission_evidence)
                return RootSyncFinding(**base, static_result="DEFER_TO_NPM", status="ROOT_OPTIONAL_ABSENT_DEFERRED", absence_semantics="OPTIONAL_ABSENCE_REQUIRES_NPM_EVIDENCE", reason_code="OPTIONAL_ABSENCE_UNEVIDENCED", deferred_npm_evidence_ref=deferred_ref)
            if static == "VERIFIED":
                return RootSyncFinding(**base, static_result="VERIFIED", status="ROOT_OPTIONAL_VERIFIED", reason_code="ROOT_OPTIONAL_SATISFIED")
            if static == "DEFER_TO_NPM":
                return RootSyncFinding(**base, static_result="DEFER_TO_NPM", status="ROOT_OPTIONAL_DEFERRED_TO_NPM", reason_code="SPEC_NOT_STATICALLY_EVALUABLE", deferred_npm_evidence_ref=deferred_ref)
            return RootSyncFinding(**base, static_result="MISMATCH", status="ROOT_OPTIONAL_INCOMPATIBLE", reason_code="OPTIONAL_INCOMPATIBLE")
        if kind is DependencyIntentKind.OPTIONAL_PEER:
            if absent:
                return RootSyncFinding(**base, static_result="STATIC_CHECK", status="OPTIONAL_PEER_ABSENT_ALLOWED", absence_semantics="OPTIONAL_PEER_ABSENT_ALLOWED", reason_code="OPTIONAL_PEER_ABSENT")
            if static == "VERIFIED":
                return RootSyncFinding(**base, static_result="VERIFIED", status="ROOT_OPTIONAL_PEER_VERIFIED", reason_code="OPTIONAL_PEER_SATISFIED")
            if static == "DEFER_TO_NPM":
                return RootSyncFinding(**base, static_result="DEFER_TO_NPM", status="ROOT_OPTIONAL_PEER_DEFERRED_TO_NPM", reason_code="SPEC_NOT_STATICALLY_EVALUABLE", deferred_npm_evidence_ref=deferred_ref)
            return RootSyncFinding(**base, static_result="MISMATCH", status="ROOT_OPTIONAL_PEER_INCOMPATIBLE", reason_code="OPTIONAL_PEER_INCOMPATIBLE")
        # PEER
        npm6 = policy.npm_major <= 6 or policy.peer_auto_install == "NOT_AUTOMATIC"
        if npm6:
            if absent:
                return RootSyncFinding(**base, static_result="DEFER_TO_NPM", status="ROOT_PEER_ABSENT_NPM6_ALLOWED_OR_DEFERRED", absence_semantics="NPM6_PEER_ABSENCE_NOT_A_REQUIRED_MISMATCH", reason_code="NPM6_PEER_ABSENT", deferred_npm_evidence_ref=deferred_ref)
            if static == "VERIFIED":
                return RootSyncFinding(**base, static_result="VERIFIED", status="ROOT_PEER_VERIFIED", reason_code="PEER_SATISFIED")
            if static == "DEFER_TO_NPM":
                return RootSyncFinding(**base, static_result="DEFER_TO_NPM", status="ROOT_PEER_DEFERRED_TO_NPM", reason_code="SPEC_NOT_STATICALLY_EVALUABLE", deferred_npm_evidence_ref=deferred_ref)
            return RootSyncFinding(**base, static_result="MISMATCH", status="ROOT_PEER_INCOMPATIBLE", reason_code="PEER_INCOMPATIBLE")
        # npm 7+: governed npm evidence owns final peer success AND failure;
        # Python may only record a static evaluation capability.
        if evidence.get("peer_conflict") is True:
            return RootSyncFinding(**base, static_result="MISMATCH", status="ROOT_PEER_CONFLICT_BY_NPM", reason_code="PEER_CONFLICT_FROM_NPM", deferred_npm_evidence_ref=deferred_ref)
        if evidence.get("peer_tree_clean") is True and static == "VERIFIED":
            return RootSyncFinding(**base, static_result="VERIFIED", status="ROOT_PEER_VERIFIED_BY_NPM", reason_code="PEER_SOLVED_BY_NPM", deferred_npm_evidence_ref=deferred_ref)
        return RootSyncFinding(**base, static_result="STATIC_CHECK", status="ROOT_PEER_PENDING_NPM_SOLVER", reason_code="PEER_OWNED_BY_NPM_SOLVER", deferred_npm_evidence_ref=deferred_ref)
