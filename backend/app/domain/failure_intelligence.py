"""Failure intelligence contracts (V2 F19).

A coherent intelligence layer over diagnostic packs: a typed classification
taxonomy, stable grouping keys, deterministic root-cause resolution, and a
failure dependency graph.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


FailureTaxonomy = Literal["environment", "command", "dependency", "workflow", "state", "transport", "llm", "policy", "unknown"]


class FailureGroup(_ImmutableModel):
    """A stable group of related failures keyed deterministically."""

    group_key: str = Field(min_length=1)
    taxonomy: FailureTaxonomy = "unknown"
    fault_codes: tuple[str, ...] = Field(default_factory=tuple)
    member_count: int = Field(ge=1)
    first_seen: datetime
    last_seen: datetime
    signature: str = Field(default="")
    checksum: str = ""

    def bind_checksum(self) -> FailureGroup:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


class FailureRootCause(_ImmutableModel):
    """The deterministic root cause of a failure group."""

    group_key: str = Field(min_length=1)
    root_cause_code: str = Field(min_length=1)
    taxonomy: FailureTaxonomy = "unknown"
    explanation: str = Field(default="")
    confidence: Literal["high", "medium", "low"] = "medium"
    contributing_codes: tuple[str, ...] = Field(default_factory=tuple)


class FailureDependencyEdge(_ImmutableModel):
    """A dependency between two failure groups (blocker -> dependent)."""

    depends_on: str = Field(min_length=1)  # the failure that blocks
    dependent: str = Field(min_length=1)   # the failure that follows
    reason: str = Field(default="")


class FailureDependencyGraph(_ImmutableModel):
    """The dependency graph among failure groups."""

    nodes: tuple[FailureGroup, ...] = Field(default_factory=tuple)
    edges: tuple[FailureDependencyEdge, ...] = Field(default_factory=tuple)
    checksum: str = ""

    def bind_checksum(self) -> FailureDependencyGraph:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


def now_utc() -> datetime:
    return datetime.now(UTC)
