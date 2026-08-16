"""Preflight check orchestration contracts (V2 F16).

A preflight runs a composed set of deterministic checks; each check produces a
per-check evidence record; the aggregate is a deterministic verdict.  Run start
is gated on the verdict.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreflightCheckResult(_ImmutableModel):
    """Per-check evidence: one deterministic check outcome."""

    check_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    passed: bool
    blockers: tuple[str, ...] = Field(default_factory=tuple)
    detail: str = ""


class PreflightVerdict(_ImmutableModel):
    """Deterministic aggregate of a composed preflight."""

    run_id: str = Field(min_length=1)
    status: Literal["passed", "warnings", "blocked"]
    checks: tuple[PreflightCheckResult, ...] = Field(default_factory=tuple)
    blockers: tuple[str, ...] = Field(default_factory=tuple)
    checksum: str = ""

    def bind_checksum(self) -> PreflightVerdict:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})


def aggregate_verdict(run_id: str, checks: list[PreflightCheckResult]) -> PreflightVerdict:
    """Deterministic verdict: any failed check blocks; otherwise passed."""
    blockers = tuple(sorted(dict.fromkeys(blocker for check in checks for blocker in check.blockers)))
    failed = any(not check.passed for check in checks)
    status = "blocked" if failed else "passed"
    return PreflightVerdict(
        run_id=run_id,
        status=status,
        checks=tuple(checks),
        blockers=blockers,
    ).bind_checksum()
