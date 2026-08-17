"""V2 analyzer and planner contracts (F18).

The analyzer derives deterministic findings for any source/target pair in the
11-21 envelope; the planner derives a deterministic, checksum-bound migration
plan from the route, the compatibility catalogue, and stage knowledge.
"""

from __future__ import annotations

import hashlib
import json
from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class V2AnalysisFinding(_ImmutableModel):
    """One deterministic analyzer finding."""

    finding_id: str = Field(min_length=1)
    severity: str  # "info" | "warning" | "blocker"
    message: str


class V2PlannedStage(_ImmutableModel):
    """One planned stage in a V2 migration plan."""

    stage_order: int = Field(ge=1)
    source_major: int
    target_major: int
    source_family: str
    target_family: str
    target_exact: str
    node_minimum: str | None = None
    expected_transforms: tuple[str, ...] = Field(default_factory=tuple)
    validation_expectations: tuple[str, ...] = Field(default_factory=tuple)
    expected_dependency_changes: tuple[dict[str, str], ...] = Field(default_factory=tuple)


class V2MigrationPlan(_ImmutableModel):
    """Deterministic migration plan for a source/target pair."""

    run_id: str = Field(min_length=1)
    source_major: int
    target_major: int
    catalogue_version: str
    findings: tuple[V2AnalysisFinding, ...] = Field(default_factory=tuple)
    stages: tuple[V2PlannedStage, ...] = Field(min_length=1)
    checksum: str = ""

    def bind_checksum(self) -> V2MigrationPlan:
        canonical = self.model_dump(mode="json")
        canonical.pop("checksum", None)
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"checksum": f"sha256:{digest}"})
