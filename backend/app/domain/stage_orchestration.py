"""Dynamic stage-chain orchestration contracts (V2 F12).

Orchestrates an arbitrary adjacent-major stage chain (from the F10 route)
durably and resumably, with per-stage transition and gate hooks and repair
routing on stage failure.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


StageChainState = Literal["created", "running", "completed", "failed", "repairing"]


class StageRunRecord(_ImmutableModel):
    """One stage's execution record within a chain."""

    stage_order: int = Field(ge=1)
    stage_id: str = Field(min_length=1)
    source_major: int
    target_major: int
    status: Literal["pending", "running", "sealed", "failed", "repairing"] = "pending"
    gate_passed: bool = False
    failure_code: str | None = None


class StageChainStateRecord(_ImmutableModel):
    """The durable chain state: ordered stage records + overall status."""

    run_id: str = Field(min_length=1)
    source_major: int
    target_major: int
    catalogue_version: str
    status: StageChainState = "created"
    stages: tuple[StageRunRecord, ...] = Field(default_factory=tuple)
    checksum: str = ""

    def bind_checksum(self) -> StageChainStateRecord:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})
