"""Backend-owned safety policy for ``dependency_add`` version intent.

A ``dependency_add`` operation inserts a package that the failure evidence
proves absent from the authoritative package.json. The LLM expresses intent
(package, section, requested registry semver spec); the backend validates only
the intent's controlled semantics: npm package-name grammar, allowed section,
and a registry semver expression. The concrete exact resolved version is
OBSERVED from the governed lockfile after npm resolution — it is never
predeclared here. Pure data + validation: no execution logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEPENDENCY_ADDITION_POLICY_VERSION = "dependency-addition-policy-v1"

DEPENDENCY_ADDITION_SECTIONS = frozenset({"dependencies", "devDependencies"})

MAX_VERSION_SPEC_LENGTH = 128

# npm package-name grammar: unscoped "name" or scoped "@scope/name";
# lowercase start, no whitespace, no shell syntax, no paths/URLs.
_PACKAGE_NAME = re.compile(r"^(?:@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*$")

# Registry semver expressions only: digits, dots, carets, tildes, comparators,
# unions, wildcards, prerelease/build hyphens/plus, and range whitespace.
_VERSION_SPEC_CHARS = re.compile(r"^[0-9A-Za-z.^*~<>=|+\- ]+$")
_VERSION_SPEC_HAS_NUMERIC = re.compile(r"\d")
# The first character of a registry semver expression (leading whitespace is
# rejected separately, so this is the true first byte).
_VERSION_SPEC_START = frozenset("0123456789~^<>=*xX")

_FORBIDDEN_VERSION_PREFIXES = (
    "http:",
    "https:",
    "git:",
    "git+",
    "file:",
    "workspace:",
    "npm:",
    "ssh:",
    "github:",
)


class DependencyAdditionPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class DependencyAdditionIntent:
    package: str
    section: str
    version_spec: str
    policy_version: str


class DependencyAdditionPolicy:
    """Validate ``dependency_add`` intent; never resolves a concrete version.

    The resolved exact version is the governed npm lockfile-generation step's
    output, observed after G10 approval — not this policy's job.
    """

    def validate(
        self,
        *,
        package: str,
        section: str,
        version_spec: str,
    ) -> DependencyAdditionIntent:
        if (
            not isinstance(package, str)
            or not package
            or _PACKAGE_NAME.fullmatch(package) is None
        ):
            raise DependencyAdditionPolicyError(
                "field=package; "
                "expected=npm package-name grammar (scoped or unscoped, lowercase, "
                "no whitespace, no shell syntax, no paths/URLs); "
                f"observed={package!r}; "
                "recovery=emit a registry package name only"
            )
        if section not in DEPENDENCY_ADDITION_SECTIONS:
            raise DependencyAdditionPolicyError(
                "field=section; "
                "expected=dependency_add in 'dependencies' or 'devDependencies'; "
                f"observed={section!r}; "
                "recovery=emit dependency_add only for dependencies or devDependencies"
            )
        if not isinstance(version_spec, str) or not version_spec:
            raise DependencyAdditionPolicyError(
                "field=version_spec; "
                "expected=non-empty registry semver expression; "
                f"observed={version_spec!r}; "
                "recovery=emit an exact version, caret, tilde, or comparator range"
            )
        if len(version_spec) > MAX_VERSION_SPEC_LENGTH:
            raise DependencyAdditionPolicyError(
                "field=version_spec; "
                f"expected=registry semver expression up to {MAX_VERSION_SPEC_LENGTH} characters; "
                f"observed={len(version_spec)} characters; "
                "recovery=emit a bounded semver expression"
            )
        if version_spec != version_spec.strip():
            raise DependencyAdditionPolicyError(
                "field=version_spec; "
                "expected=registry semver expression without leading or trailing whitespace; "
                f"observed={version_spec!r}; "
                "recovery=emit the semver expression without surrounding whitespace"
            )
        lowered = version_spec.lower()
        if any(lowered.startswith(prefix) for prefix in _FORBIDDEN_VERSION_PREFIXES):
            raise DependencyAdditionPolicyError(
                "field=version_spec; "
                "expected=registry semver expression only; "
                f"observed={version_spec!r}; "
                "recovery=latest/next/dist-tags, URLs, git specs, file specs, workspace specs, "
                "and npm aliases are not registry semver expressions"
            )
        if version_spec.startswith(("/", "./", "../")):
            raise DependencyAdditionPolicyError(
                "field=version_spec; "
                "expected=registry semver expression only; "
                f"observed={version_spec!r}; "
                "recovery=local paths are not registry semver expressions"
            )
        if version_spec[0] not in _VERSION_SPEC_START:
            raise DependencyAdditionPolicyError(
                "field=version_spec; "
                "expected=registry semver expression starting with a numeric version, "
                "caret, tilde, comparator, or wildcard; "
                f"observed={version_spec!r}; "
                "recovery=dist-tags (for example latest, next) are not registry semver expressions"
            )
        if version_spec.startswith("~") and len(version_spec) > 1 and not version_spec[1].isdigit():
            raise DependencyAdditionPolicyError(
                "field=version_spec; "
                "expected=registry tilde range (for example ~1.2.3); "
                f"observed={version_spec!r}; "
                "recovery=tilde git specs are not registry semver expressions"
            )
        if _VERSION_SPEC_CHARS.fullmatch(version_spec) is None:
            raise DependencyAdditionPolicyError(
                "field=version_spec; "
                "expected=registry semver characters only; "
                f"observed={version_spec!r}; "
                "recovery=shell syntax and path separators are not registry semver expressions"
            )
        if _VERSION_SPEC_HAS_NUMERIC.search(version_spec) is None:
            raise DependencyAdditionPolicyError(
                "field=version_spec; "
                "expected=registry semver expression with numeric version semantics; "
                f"observed={version_spec!r}; "
                "recovery=dist-tags and bare wildcards are not registry semver expressions"
            )
        return DependencyAdditionIntent(
            package=package,
            section=section,
            version_spec=version_spec,
            policy_version=DEPENDENCY_ADDITION_POLICY_VERSION,
        )
