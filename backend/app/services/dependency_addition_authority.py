"""Frozen backend-owned authority for inserting new package dependencies.

A ``dependency_add`` operation inserts a package that the failure evidence
proves absent from the authoritative package.json. The LLM may only express
intent (package, section, requested range); the final exact version is bound
here, never by the proposer. Pure data + validation: no execution logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.dependency_closure_service import is_exact_version

DEPENDENCY_ADDITION_POLICY_VERSION = "dependency-addition-authority-v1"

_DEPENDENCY_ADDITION_SECTIONS = frozenset({"dependencies", "devDependencies"})

# Frozen backend-owned phase-1 authority: (package, section, Angular major) ->
# exact version. Every entry must satisfy is_exact_version. Unknown keys fail
# closed with recovery guidance.
_DEPENDENCY_ADDITION_AUTHORITY: dict[tuple[str, str, int], str] = {
    ("jest-environment-jsdom", "devDependencies", 21): "30.4.1",
}


class DependencyAdditionAuthorityError(ValueError):
    pass


@dataclass(frozen=True)
class DependencyAdditionAuthorityEntry:
    package: str
    section: str
    target_angular_major: int
    exact_version: str
    policy_version: str


class DependencyAdditionAuthority:
    def resolve(
        self, *, package: str, section: str, target_angular_major: int
    ) -> DependencyAdditionAuthorityEntry:
        if section not in _DEPENDENCY_ADDITION_SECTIONS:
            raise DependencyAdditionAuthorityError(
                "field=section; "
                "expected=dependency_add in 'dependencies' or 'devDependencies'; "
                f"observed={section!r}; "
                "recovery=emit dependency_add only for dependencies or devDependencies"
            )
        exact_version = _DEPENDENCY_ADDITION_AUTHORITY.get(
            (package, section, target_angular_major)
        )
        if exact_version is None:
            raise DependencyAdditionAuthorityError(
                "field=package/section/target_angular_major; "
                f"expected=backend-approved exact version for {package} in {section} "
                f"at Angular {target_angular_major}; observed=missing; "
                "recovery=add verified dependency-addition authority before retrying"
            )
        if not is_exact_version(exact_version):
            raise DependencyAdditionAuthorityError(
                "field=exact_version; "
                f"expected=exact semver for {package} in {section} at Angular "
                f"{target_angular_major}; observed={exact_version!r}; "
                "recovery=add verified dependency-addition authority before retrying"
            )
        return DependencyAdditionAuthorityEntry(
            package=package,
            section=section,
            target_angular_major=target_angular_major,
            exact_version=exact_version,
            policy_version=DEPENDENCY_ADDITION_POLICY_VERSION,
        )
