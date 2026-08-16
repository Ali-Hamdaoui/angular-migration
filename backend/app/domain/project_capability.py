"""Project capability model contracts (V2 F13).

A ``ProjectCapability`` is a deterministic, immutable fact about a source
project's ability to undergo migration (toolchain, workspace structure,
dependency health).  Capabilities are derived from the project by inspection and
frozen by a checksum; per-stage snapshots track how capabilities evolve through
the migration.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectCapability(_ImmutableModel):
    """One deterministic capability fact about a source project."""

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    detail: str = ""


class ProjectCapabilitySnapshot(_ImmutableModel):
    """The immutable capability set of a project at a point in time."""

    run_id: str = Field(min_length=1)
    stage_id: str | None = None
    source_root: str = Field(min_length=1)
    angular_major: int | None = None
    capabilities: tuple[ProjectCapability, ...] = Field(default_factory=tuple)
    checksum: str = ""

    def bind_checksum(self) -> ProjectCapabilitySnapshot:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


def snapshot_checksum(snapshot: ProjectCapabilitySnapshot) -> str:
    return snapshot.checksum or snapshot.bind_checksum().checksum


def now_utc() -> datetime:
    return datetime.now(UTC)
