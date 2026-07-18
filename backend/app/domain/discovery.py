"""Typed, deterministic discovery contracts for Sprint 2 Feature 1."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DiscoveryRequest(BaseModel):
    """A run-scoped request; callers never supply a workspace path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1)
    prerequisite_artifact_ids: tuple[str, ...] = Field(min_length=1)
    actor: str = Field(min_length=1)


class DiscoveryFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    value: Any
    confidence: Literal["high", "medium", "low", "unknown"] = "high"
    source_references: tuple[str, ...] = ()


class ScannerFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scanner: str
    status: Literal["completed", "unknown", "blocked"]
    findings: tuple[DiscoveryFinding, ...] = ()
    unknowns: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class DiscoveryEvidenceDraft(BaseModel):
    """Canonical serialized evidence to be finalized by I02's ArtifactService adapter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    content: str
    checksum: str


class DiscoveryApplicationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    status: Literal["completed", "blocked"]
    state_version: int
    scanner_results: tuple[ScannerFinding, ...]
    evidence_drafts: tuple[DiscoveryEvidenceDraft, ...]
    artifact_ids: tuple[str, ...] = ()
    error_code: str | None = None
    idempotent_replay: bool = False
