"""Deterministic compatibility and G05 application contracts for S2-F05.

This module contains no database, filesystem, network, or LLM behavior.  The
catalogue is the authority for family routes and support claims; adapters are
responsible for supplying its versioned data and runtime inventory.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.execution_profile import RuntimeCandidate


SupportLevel = Literal[
    "officially_supported",
    "historical_validated",
    "historical_experimental",
    "blocked",
]
FeasibilityStatus = Literal[
    "feasible",
    "feasible_with_warnings",
    "requires_manual_preparation",
    "blocked",
]


class CompatibilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CompatibilityArtifact(CompatibilityModel):
    artifact_id: str = Field(min_length=1)
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class CompatibilityCatalogueEntry(CompatibilityModel):
    stage_id: str = Field(min_length=1)
    source_family: str = Field(pattern=r"^angular-(18|19|20|21)\.x$")
    target_family: str = Field(pattern=r"^angular-(18|19|20|21)\.x$")
    target_angular_exact: str = Field(min_length=1)
    target_cli_exact: str = Field(min_length=1)
    typescript_exact: str | None = None
    rxjs_exact: str | None = None
    zone_js_exact: str | None = None
    node_major: int = Field(ge=0)
    npm_major: int = Field(ge=0)
    node_exact: str | None = None
    npm_exact: str | None = None
    cli_exact: str | None = None
    support_level: SupportLevel
    fixture_status: Literal["passed", "incomplete", "failed"]
    validation_policy_id: str = Field(min_length=1)
    known_risks: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    validated_runtime_profiles: tuple[tuple[str, str], ...] = ()

    @model_validator(mode="after")
    def validate_adjacent_families(self) -> "CompatibilityCatalogueEntry":
        source = int(self.source_family.removeprefix("angular-").removesuffix(".x"))
        target = int(self.target_family.removeprefix("angular-").removesuffix(".x"))
        if target != source + 1:
            raise ValueError("compatibility entries must describe adjacent Angular major families")
        if self.support_level == "historical_validated" and self.fixture_status != "passed":
            raise ValueError("historical_validated requires a passed fixture suite")
        if self.support_level == "blocked" and not self.blockers:
            raise ValueError("blocked compatibility entries require a blocker")
        return self


class CompatibilityCatalogue(CompatibilityModel):
    version: str = Field(min_length=1)
    entries: tuple[CompatibilityCatalogueEntry, ...] = Field(min_length=1)
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def build(cls, version: str, entries: tuple[CompatibilityCatalogueEntry, ...]) -> "CompatibilityCatalogue":
        serialized_entries = []
        for entry in entries:
            serialized = entry.model_dump(mode="json")
            if not entry.validated_runtime_profiles:
                serialized.pop("validated_runtime_profiles", None)
            serialized_entries.append(serialized)
        payload = {"version": version, "entries": serialized_entries}
        checksum = "sha256:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(version=version, entries=entries, checksum=checksum)

    def entry_for(self, source_family: str, target_family: str) -> CompatibilityCatalogueEntry | None:
        return next(
            (
                entry
                for entry in self.entries
                if entry.source_family == source_family and entry.target_family == target_family
            ),
            None,
        )


class CompatibilityResolutionRequest(CompatibilityModel):
    run_id: str = Field(min_length=1)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1)
    source_angular_exact: str = Field(min_length=1)
    target_family: str = Field(default="angular-21.x", pattern=r"^angular-\d+\.x$")
    catalogue_version: str = Field(min_length=1)
    registry_snapshot_id: str = Field(default="registry-snapshot-v1", min_length=1, max_length=128)
    registry_snapshot_checksum: str = Field(default="sha256:" + "0" * 64, pattern=r"^sha256:[0-9a-f]{64}$")
    prerequisite_artifacts: tuple[CompatibilityArtifact, ...] = ()
    runtime_candidates: tuple[RuntimeCandidate, ...] = ()
    workspace_topology: str = Field(default="single_application_cli_workspace", min_length=1)
    dependency_findings: tuple[str, ...] = ()
    source_execution_profile_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    plan_version: str | None = Field(default=None, max_length=128)
    resolved_at: datetime


class Stage1ExecutionProfile(CompatibilityModel):
    profile_id: str
    angular_exact: str
    angular_cli_exact: str
    node_exact: str
    npm_exact: str
    npx_exact: str
    node_executable: str
    npm_executable: str
    npx_executable: str
    operating_system: str
    architecture: str
    catalogue_version: str
    source_angular_exact: str
    source_execution_profile_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    stage1_profile_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def calculate_stage1_profile_checksum(profile: Stage1ExecutionProfile | dict) -> str:
    payload = profile.model_dump(mode="json") if hasattr(profile, "model_dump") else dict(profile)
    payload.pop("source_execution_profile_checksum", None)
    payload.pop("stage1_profile_checksum", None)
    payload.pop("checksum", None)
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class CompatibilityStage(CompatibilityModel):
    stage_id: str
    source_family: str
    target_family: str
    support_level: SupportLevel
    target_angular_exact: str
    target_cli_exact: str
    node_exact: str | None = None
    npm_exact: str | None = None
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class FeasibilityPackage(CompatibilityModel):
    catalogue_version: str
    catalogue_checksum: str
    source_exact: str
    source_family: str
    target_family: str
    support_level: SupportLevel
    route: tuple[CompatibilityStage, ...]
    selected_profile: Stage1ExecutionProfile | None
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    artifact_set_checksum: str
    workspace_fingerprint: str | None = None
    plan_version: str | None = None
    package_checksum: str


class G05Package(CompatibilityModel):
    gate_id: Literal["G05"] = "G05"
    gate_version: str = "g05-v1"
    status: Literal["pending", "blocked"]
    package_checksum: str
    artifact_set_checksum: str
    state_version: int
    workspace_fingerprint: str | None = None
    plan_version: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    feasibility: FeasibilityPackage


class CompatibilityResolutionResult(CompatibilityModel):
    run_id: str
    status: FeasibilityStatus
    source_exact: str
    source_family: str
    target_family: str
    support_level: SupportLevel
    route: tuple[CompatibilityStage, ...]
    selected_profile: Stage1ExecutionProfile | None
    package: FeasibilityPackage
    gate: G05Package
    state_version: int
    idempotent_replay: bool = False
