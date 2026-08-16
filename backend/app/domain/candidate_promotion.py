"""Candidate workspace promotion contracts (V2 F22).

A candidate workspace is applied from approved diffs, validated, and promoted
atomically to a new workspace generation.  Promotion uses the workspace
authority's monotonic generation guard; on validation failure the candidate is
rejected and the last-good generation remains active (rollback safety).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


CandidatePromotionStatus = Literal["candidate_ready", "validated", "promoted", "rejected", "rollback_required"]


class CandidatePromotionDecision(_ImmutableModel):
    """One deterministic candidate promotion outcome."""

    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    alias: str = Field(min_length=1)
    candidate_fingerprint: str = Field(min_length=1)
    generation: int = Field(ge=1)
    status: CandidatePromotionStatus
    validated: bool = False
    blockers: tuple[str, ...] = Field(default_factory=tuple)
    previous_generation: int | None = None
    checksum: str = ""

    def bind_checksum(self) -> CandidatePromotionDecision:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


def now_utc() -> datetime:
    return datetime.now(UTC)
