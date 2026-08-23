"""Immutable runtime requirement and executable descriptor contracts (V2).

Separates WHAT a migration stage requires (``RuntimeRequirement``) from WHERE and
WHAT concretely exists on the machine (``RuntimeExecutableDescriptor``).  The two
must never be conflated: a requirement is a policy statement, a descriptor is a
probed, checksum-bound fact about a resolved executable.

This module deliberately has no process, filesystem, database, or network side
effects.  Resolution authority lives in ``services.runtime_resolver_authority``;
this module only models the immutable facts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.execution_profile import Version


class RuntimeExecutableKind(str, Enum):
    """The executable families the resolver authority can bind."""

    NODE = "node"
    NPM = "npm"
    NPX = "npx"


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _validate_version(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized[:1] in {"v", "V"} and normalized[1:2].isdigit():
        normalized = normalized[1:]
    if Version.parse(normalized) is None:
        raise ValueError(f"version must be a x.y.z semver, got {value!r}")
    return normalized


class RuntimeRequirement(_ImmutableModel):
    """What a migration stage requires from the machine runtime.

    ``runtime_id`` identifies a named runtime instance (for example ``node18``).
    A requirement may pin an exact version, a minimum version, or both.
    """

    kind: RuntimeExecutableKind
    runtime_id: str = Field(min_length=1)
    version_exact: str | None = None
    minimum_version: str | None = None
    required_sha256: str | None = None
    allowed_major_versions: tuple[int, ...] = ()

    @field_validator("version_exact", "minimum_version")
    @classmethod
    def _require_semver(cls, value: str | None) -> str | None:
        return _validate_version(value)

    @model_validator(mode="after")
    def require_some_constraint(self) -> RuntimeRequirement:
        if not self.version_exact and not self.minimum_version and not self.required_sha256:
            raise ValueError("RuntimeRequirement must constrain at least one of version or checksum")
        return self

    def satisfied_by(self, descriptor: RuntimeExecutableDescriptor) -> bool:
        """Deterministic check of whether a descriptor satisfies this requirement."""
        if descriptor.kind is not self.kind:
            return False
        if self.required_sha256 and descriptor.sha256 != self.required_sha256:
            return False
        version = Version.parse(descriptor.version_exact or "") if descriptor.version_exact else None
        if version is None:
            return False
        if self.allowed_major_versions and version.major not in self.allowed_major_versions:
            return False
        if self.version_exact and descriptor.version_exact != self.version_exact:
            return False
        if self.minimum_version and not version.at_least(Version.parse(self.minimum_version)):
            return False
        return True


class RuntimeExecutableDescriptor(_ImmutableModel):
    """A concrete, immutable fact about one resolved runtime executable.

    ``resolved_path`` is an absolute path bound by the resolver authority, never a
    bare PATH name.  ``sha256`` is the SHA-256 of the executable file bytes and is
    the fail-closed identity used by the execution guard.
    """

    kind: RuntimeExecutableKind
    executable_name: str = Field(min_length=1)
    resolved_path: str = Field(min_length=1)
    version_exact: str | None = None
    sha256: str = Field(min_length=64, max_length=64)
    operating_system: str = Field(default="linux", min_length=1)
    architecture: str = Field(default="amd64", min_length=1)
    installation_root: str | None = None
    installation_variant: str | None = None
    source: str = Field(default="runtime-matrix", min_length=1)
    runtime_id: str | None = None
    probed_at: datetime

    @field_validator("version_exact")
    @classmethod
    def _require_semver(cls, value: str | None) -> str | None:
        return _validate_version(value)

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        try:
            int(value, 16)
        except ValueError as exc:
            raise ValueError("sha256 must be a hex digest") from exc
        return value.lower()

    def matches(self, other: RuntimeExecutableDescriptor) -> bool:
        """Identity comparison used by the fail-closed execution guard."""
        return self.kind is other.kind and self.resolved_path == other.resolved_path and self.sha256 == other.sha256


class RuntimeRequirementBinding(_ImmutableModel):
    """Pair a stage requirement with the descriptor that satisfies it.

    ``descriptor`` stays ``None`` when the machine cannot satisfy the requirement;
    callers treat that as an explicit failure, never as a silent PATH fallback.
    """

    requirement: RuntimeRequirement
    descriptor: RuntimeExecutableDescriptor | None = None
    blocked_reason: str | None = None
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
