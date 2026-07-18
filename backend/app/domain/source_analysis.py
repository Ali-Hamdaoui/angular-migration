"""Typed deterministic source-analysis contracts."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class SourceAnalysisRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_path: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    actor: str | None = None


class DetectedVersion(BaseModel):
    model_config = ConfigDict(frozen=True)
    package: str
    declared: str | None = None
    resolved: str | None = None
    family: str | None = None
    confidence: Literal["high", "medium", "low", "unknown"] = "unknown"


class WorkspaceTopology(BaseModel):
    model_config = ConfigDict(frozen=True)
    projects: list[str] = Field(default_factory=list)
    libraries: list[str] = Field(default_factory=list)
    is_nx: bool = False
    has_custom_builder: bool = False
    classification: str = "unknown"


class SourceAnalysisSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    analysis_id: str
    policy_version: str
    status: Literal["accepted", "review_required", "blocked"]
    source_path: str
    package_manager: str
    lockfile: str | None
    versions: list[DetectedVersion]
    topology: WorkspaceTopology
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checksum: str


class SourceAnalysisResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    snapshot: SourceAnalysisSnapshot