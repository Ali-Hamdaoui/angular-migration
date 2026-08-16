"""Immutable execution audit trail contracts (V2 F27-03).

Every governed command execution appends one immutable, hash-chained audit
entry.  Entries are never updated or deleted; integrity is verified by
recomputing the chain from the first entry.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ExecutionAuditEvent(str, Enum):
    """The append-only lifecycle events recorded on the trail."""

    AUTHORIZATION_REJECTED = "authorization_rejected"
    AUTHORIZATION_ACCEPTED = "authorization_accepted"
    EXECUTION_QUEUED = "execution_queued"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_SUCCEEDED = "execution_succeeded"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_TIMED_OUT = "execution_timed_out"
    EXECUTION_CANCELLED = "execution_cancelled"
    EXECUTION_INTERRUPTED = "execution_interrupted"


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExecutionAuditEntry(_ImmutableModel):
    """One immutable, hash-chained execution audit record (F27-03)."""

    entry_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    stage_id: str | None = None
    execution_id: str | None = None
    command_id: str = Field(min_length=1)
    command_class: str = Field(min_length=1)
    event: ExecutionAuditEvent
    actor: str | None = None
    executable: str = ""
    arguments: tuple[str, ...] = Field(default_factory=tuple)
    policy_version: str = ""
    state_version: int | None = None
    network_profile: str | None = None
    reason: str = ""
    prev_checksum: str = "GENESIS"
    checksum: str = ""
    occurred_at: datetime

    def bind_checksum(self, prev_checksum: str) -> ExecutionAuditEntry:
        """Bind this entry to the previous entry in the chain.

        ``occurred_at`` is canonicalized to naive UTC so the checksum is
        invariant to timezone-aware/naive round-trips through storage.
        """
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        canonical["prev_checksum"] = prev_checksum
        occurred = self.occurred_at
        canonical["occurred_at"] = (
            occurred.astimezone(UTC).replace(tzinfo=None).isoformat()
            if occurred.tzinfo is not None
            else occurred.isoformat()
        )
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}", "prev_checksum": prev_checksum})
