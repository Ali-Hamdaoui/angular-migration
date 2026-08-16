"""Immutable migration route contracts (V2 F10).

A migration route is the deterministic adjacent-major stage chain from a source
Angular major to a target major, derived from the compatibility catalogue and
frozen by a checksum.  Same input always yields the same route; a persisted
route is immutable.
"""

from __future__ import annotations

import hashlib
import json
from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


ENVELOPE_MIN_MAJOR = 11
ENVELOPE_MAX_MAJOR = 21


class RouteStage(_ImmutableModel):
    """One adjacent-major stage in a migration route."""

    stage_order: int = Field(ge=1)
    source_major: int = Field(ge=ENVELOPE_MIN_MAJOR)
    target_major: int = Field(ge=ENVELOPE_MIN_MAJOR)
    source_family: str = Field(min_length=1)
    target_family: str = Field(min_length=1)
    support_level: str = Field(min_length=1)


class MigrationRoute(_ImmutableModel):
    """The deterministic stage chain for one source -> target migration."""

    source_major: int = Field(ge=ENVELOPE_MIN_MAJOR, le=ENVELOPE_MAX_MAJOR)
    target_major: int = Field(ge=ENVELOPE_MIN_MAJOR, le=ENVELOPE_MAX_MAJOR)
    catalogue_version: str = Field(min_length=1)
    stages: tuple[RouteStage, ...] = Field(min_length=1)
    checksum: str = ""

    def bind_checksum(self) -> "MigrationRoute":
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


def validate_envelope(source_major: int, target_major: int) -> str | None:
    """Validate source/target within the supported Angular 11-21 envelope.

    Returns a blocker code, or None when the pair is in-envelope.
    """
    if source_major < ENVELOPE_MIN_MAJOR or source_major > ENVELOPE_MAX_MAJOR:
        return f"SOURCE_OUT_OF_ENVELOPE:{source_major}"
    if target_major < ENVELOPE_MIN_MAJOR or target_major > ENVELOPE_MAX_MAJOR:
        return f"TARGET_OUT_OF_ENVELOPE:{target_major}"
    if source_major >= target_major:
        return f"ROUTE_DIRECTION_INVALID:{source_major}->{target_major}"
    return None


