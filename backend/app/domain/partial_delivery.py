"""Partial migration delivery contracts (V2 F26).

Delivers a partial migration at the furthest sealed stage: the workspace at the
last sealed stage is validated, delivered, and the remaining work is recorded so
the migration can resume later.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PartialDeliveryDecision(_ImmutableModel):
    """One deterministic partial delivery outcome."""

    run_id: str = Field(min_length=1)
    delivered_at_stage: int | None = None
    delivered_fingerprint: str = Field(default="")
    validated: bool = False
    remaining_stages: tuple[str, ...] = Field(default_factory=tuple)
    resumable: bool = True
    checksum: str = ""

    def bind_checksum(self) -> PartialDeliveryDecision:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


def now_utc() -> datetime:
    return datetime.now(UTC)
