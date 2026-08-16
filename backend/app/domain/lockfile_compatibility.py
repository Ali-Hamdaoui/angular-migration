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


def version_satisfies(resolved: str | None, expected: str | None, *, minimum: str | None = None) -> bool:
    """Resolved version satisfies an exact expectation or a semver minimum."""
    if resolved is None:
        return False
    parsed = Version.parse(resolved)
    if parsed is None:
        return False
    if expected is not None:
        return resolved == expected
    if minimum is not None:
        minimum_parsed = Version.parse(minimum)
        return minimum_parsed is not None and parsed.at_least(minimum_parsed)
    return True


def evaluate_lockfile_compatibility(
    dependency_set: LockfileDependencySet,
    *,
    source_family: str,
    target_family: str,
    catalogue_expected: dict[str, str | None],
    catalogue_minimums: dict[str, str],
) -> LockfileCompatibilityVerdict:
    """Validate the resolved dependency set against catalogue expectations.

    ``catalogue_expected`` maps package name -> exact expected version (when the
    catalogue pins one).  ``catalogue_minimums`` maps package name -> minimum
    version for packages the catalogue constrains by a floor.
    """
    findings: list[LockfileCompatibilityFinding] = []
    blockers: list[str] = []
    packages = set(catalogue_expected) | set(catalogue_minimums)
    for package in sorted(packages):
        resolved = dependency_set.resolved_version(package)
        expected = catalogue_expected.get(package)
        minimum = catalogue_minimums.get(package)
        if resolved is None:
            findings.append(
                LockfileCompatibilityFinding(package=package, expected=expected, resolved=None, status="missing", detail="package not present in lockfile dependency set")
            )
            blockers.append(f"LOCKFILE_DEPENDENCY_MISSING:{package}")
            continue
        if version_satisfies(resolved, expected, minimum=minimum):
            findings.append(
                LockfileCompatibilityFinding(package=package, expected=expected, resolved=resolved, status="ok", detail="resolved version satisfies catalogue constraint")
            )
        else:
            findings.append(
                LockfileCompatibilityFinding(
                    package=package, expected=expected or minimum, resolved=resolved,
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
