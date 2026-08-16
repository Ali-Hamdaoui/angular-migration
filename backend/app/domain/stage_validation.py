"""Stage validation and sealing contracts (V2 F24).

Each stage is validated deterministically and sealed with an evidence freeze:
the validation summary, workspace fingerprint, and checksum are persisted and
immutable once sealed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StageValidationResult(_ImmutableModel):
    """One deterministic stage validation outcome."""

    stage_id: str = Field(min_length=1)
    checks: tuple[str, ...] = Field(default_factory=tuple)  # e.g. ("build", "test")
    passed: bool
    blockers: tuple[str, ...] = Field(default_factory=tuple)
    workspace_fingerprint: str = Field(default="")
    checksum: str = ""

    def bind_checksum(self) -> StageValidationResult:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


class StageSeal(_ImmutableModel):
    """The immutable seal of a stage's validated evidence."""

    stage_id: str = Field(min_length=1)
    source_major: int
    target_major: int
    validation_checksum: str = Field(min_length=1)
    workspace_fingerprint: str = Field(default="")
    sealed_at: datetime
    checksum: str = ""

    def bind_checksum(self) -> StageSeal:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})
