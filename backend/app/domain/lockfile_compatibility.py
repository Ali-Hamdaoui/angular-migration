"""Lockfile dependency-set compatibility contracts (V2 F08).

A parsed package-lock.json dependency set is validated deterministically against
the compatibility catalogue for a stage's target Angular major.  Pure domain:
no filesystem, database, or network side effects.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.execution_profile import Version


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LockfileDependencySet(_ImmutableModel):
    """The resolved dependency set frozen by a package-lock.json."""

    lockfile_version: int | None = None
    root_dependencies: dict[str, str] = Field(default_factory=dict)
    resolved_packages: dict[str, str] = Field(default_factory=dict)  # name -> resolved version
    checksum: str = ""

    def resolved_version(self, name: str) -> str | None:
        if name in self.resolved_packages:
            return self.resolved_packages[name]
        return self.root_dependencies.get(name)


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
