"""Stage rollback and resume contracts (V2 F25).

Rollback returns a failed chain to the last sealed stage and resumes from there
deterministically, preserving sealed evidence immutably.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StageRollbackDecision(_ImmutableModel):
    """One deterministic rollback outcome."""

    run_id: str = Field(min_length=1)
    rollback_point_stage_order: int | None = None
    sealed_stage_count: int = Field(default=0, ge=0)
    evidence_preserved: bool = True
    status: Literal["rolled_back", "no_rollback_point", "not_started"] = "rolled_back"
    checksum: str = ""

    def bind_checksum(self) -> StageRollbackDecision:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


def now_utc() -> datetime:
    return datetime.now(UTC)
