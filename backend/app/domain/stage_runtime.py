"""Stage-scoped runtime requirement and binding contracts (V2 F02).

A migration stage declares WHAT runtime it requires (``StageRuntimeRequirement``),
derived deterministically from the compatibility catalogue for its adjacent-major
transition.  ``StageRuntimeBinding`` freezes the concrete machine descriptors that
satisfy that requirement at resolve time.  The stage requirement is distinct from
the machine installation: the same stage requirement may bind to different
machine runtimes on different hosts.

This module has no process, filesystem, database, or network side effects.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.runtime_execution import (
    RuntimeExecutableDescriptor,
    RuntimeExecutableKind,
    RuntimeRequirement,
    RuntimeRequirementBinding,
)


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StageRuntimeRequirement(_ImmutableModel):
    """What one adjacent-major stage requires from the machine runtime."""

    stage_id: str = Field(min_length=1)
    source_family: str = Field(min_length=1)
    target_family: str = Field(min_length=1)
    catalogue_version: str = Field(min_length=1)
    requirements: tuple[RuntimeRequirement, ...] = Field(min_length=1)

    def requirement_for(self, kind: RuntimeExecutableKind) -> RuntimeRequirement | None:
        for requirement in self.requirements:
            if requirement.kind is kind:
                return requirement
        return None


class StageRuntimeBinding(_ImmutableModel):
    """The concrete machine bindings that satisfy a stage requirement."""

    stage_id: str
    requirement: StageRuntimeRequirement
    bindings: tuple[RuntimeRequirementBinding, ...] = ()
    status: Literal["bound", "blocked"]
    blocked_reason: str | None = None
    resolved_at: datetime
    checksum: str = ""

    def descriptor_for(self, kind: RuntimeExecutableKind) -> RuntimeExecutableDescriptor | None:
        for binding in self.bindings:
            if binding.requirement.kind is kind and binding.descriptor is not None:
                return binding.descriptor
        return None

    def bind_checksum(self) -> StageRuntimeBinding:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(
            __import__("json").dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


def stage_binding_checksum(binding: StageRuntimeBinding) -> str:
    return binding.checksum or binding.bind_checksum().checksum


def now_utc() -> datetime:
    return datetime.now(UTC)
