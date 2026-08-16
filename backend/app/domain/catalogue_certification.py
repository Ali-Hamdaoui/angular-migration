"""Catalogue certification pipeline contracts (V2 F30).

The pipeline runtime-proves each compatibility catalogue entry by driving a
fixture migration through the V2 stages; PASS promotes the entry to
certified, FAIL rejects it with durable evidence.  Outcomes are
deterministic: identical fixture + identical runtime proof -> identical
outcome.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CertificationStatus(str, Enum):
    """A catalogue entry's pipeline outcome (F30-03)."""

    CERTIFIED = "certified"
    REJECTED = "rejected"


class CatalogueCertificationCase(_ImmutableModel):
    """One catalogue entry to certify via a runtime proof (F30-01)."""

    case_id: str = Field(min_length=1)
    source_family: str = Field(pattern=r"^angular-\d+\.x$")
    target_family: str = Field(pattern=r"^angular-\d+\.x$")


class CatalogueCertificationOutcome(_ImmutableModel):
    """One entry's deterministic certification result (F30-03)."""

    case_id: str
    source_family: str
    target_family: str
    status: CertificationStatus
    runtime_proof: tuple[tuple[str, str], ...] = Field(default_factory=tuple)
    evidence: tuple[str, ...] = Field(default_factory=tuple)
    reason: str = ""
    checksum: str = ""

    def bind_checksum(self) -> CatalogueCertificationOutcome:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


class CatalogueCertificationRun(_ImmutableModel):
    """One versioned pipeline run over a set of entries."""

    run_id: str = Field(min_length=1)
    catalogue_version: str = Field(min_length=1)
    outcomes: tuple[CatalogueCertificationOutcome, ...] = Field(default_factory=tuple)
    certified_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    deterministic: bool = True
    ran_at: datetime
    checksum: str = ""

    def bind_checksum(self) -> CatalogueCertificationRun:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        canonical.pop("ran_at", None)
        canonical.pop("run_id", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})
