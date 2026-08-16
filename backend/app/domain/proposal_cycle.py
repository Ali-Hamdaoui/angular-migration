"""Governed repair proposal-cycle contracts (V2 F21).

An immutable proposal cycle records one LLM proposal and its human reviewer
decision (accept/reject/request-change).  A request-change decision creates a
child cycle carrying hints and diffs, forming the cycle lineage.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


ProposalDecision = Literal["pending", "accepted", "rejected", "request_changes"]


class ProposalCycle(_ImmutableModel):
    """One immutable proposal-revision cycle for a repair attempt."""

    cycle_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    cycle_number: int = Field(ge=1)
    proposal_checksum: str = Field(min_length=1)
    decision: ProposalDecision = "pending"
    reviewer: str | None = None
    hints: tuple[str, ...] = Field(default_factory=tuple)
    parent_cycle_id: str | None = None
    checksum: str = ""

    def bind_checksum(self) -> ProposalCycle:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


def cycle_checksum(cycle: ProposalCycle) -> str:
    return cycle.checksum or cycle.bind_checksum().checksum


def now_utc() -> datetime:
    return datetime.now(UTC)
