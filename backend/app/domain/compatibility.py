"""Deterministic compatibility and G05 application contracts for S2-F05.

This module contains no database, filesystem, network, or LLM behavior.  The
catalogue is the authority for family routes and support claims; adapters are
responsible for supplying its versioned data and runtime inventory.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.execution_profile import RuntimeCandidate
from app.domain.runtime_compatibility import RuntimeCompatibilityClass

SupportLevel = Literal[
    "officially_supported",
    "historical_validated",
    "historical_experimental",
    "blocked",
]

FRAMEWORK_COHORT_PACKAGES = frozenset(
    {
        "@angular/animations",
        "@angular/common",
        "@angular/compiler",
        "@angular/compiler-cli",
        "@angular/core",
        "@angular/forms",
        "@angular/platform-browser",
        "@angular/platform-browser-dynamic",
        "@angular/router",
    }
)
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


#: Catalogue evidence truth layers (V2.2 P0-0): an entry describes the official
#: support envelope, carries observed empirical proof, or is certified through
#: promoted immutable evidence. Legacy payloads without the field deserialize
#: with ``evidence_classification=None`` and are treated as uncertified.
EvidenceClassification = Literal["official_envelope", "observed", "certified"]


class RuntimeProofProfile(CompatibilityModel):
    """Exact empirical target evidence; never an official range or certification."""

    source_angular_exact: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    target_angular_exact: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    target_cli_exact: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    node_exact: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    npm_exact: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    proof_source: str = Field(min_length=1)
    proof_status: Literal["observed", "replayed", "certified"]
    proved_at: datetime | None = None
    evidence_artifact_id: str | None = None
    evidence_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_certified_requires_immutable_evidence(self) -> RuntimeProofProfile:
        if self.proof_status == "certified" and (not self.evidence_artifact_id or not self.evidence_checksum):
            raise ValueError("certified runtime proof requires an immutable evidence artifact id and checksum")
        return self


class CompatibilityCatalogueEntry(CompatibilityModel):
    stage_id: str = Field(min_length=1)
    source_family: str = Field(pattern=r"^angular-(1[1-9]|2[01])\.x$")
    target_family: str = Field(pattern=r"^angular-(1[1-9]|2[01])\.x$")
    target_angular_exact: str = Field(min_length=1)
    target_cli_exact: str = Field(min_length=1)
    typescript_exact: str | None = None
    typescript_minimum: str | None = None
    typescript_exclusive_maximum: str | None = None
    rxjs_exact: str | None = None
    rxjs_minimum: str | None = None
    rxjs_ranges: tuple[str, ...] = ()
    zone_js_exact: str | None = None
    node_major: int = Field(ge=0)
    npm_major: int = Field(ge=0)
    node_exact: str | None = None
    node_minimum: str | None = None
    npm_exact: str | None = None
    cli_exact: str | None = None
    support_level: SupportLevel
    fixture_status: Literal["passed", "incomplete", "failed"]
    validation_policy_id: str = Field(min_length=1)
    known_risks: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    validated_runtime_profiles: tuple[tuple[str, str], ...] = ()
    source_node_ranges: tuple[str, ...] = ()
    target_node_ranges: tuple[str, ...] = ()
    proven_runtime_profiles: tuple[tuple[str, str], ...] = ()
    proven_runtime_evidence: tuple[RuntimeProofProfile, ...] = ()
    proven_runtime_source: str | None = None
    certification_status: str | None = None
    certification_source: str | None = None
    certified_at: datetime | None = None
    evidence_classification: EvidenceClassification | None = None

    def target_cohort(self) -> dict[str, str]:
        """Exact backend-owned package cohort selected inside official ranges."""
        cohort = {
            package: self.target_angular_exact for package in FRAMEWORK_COHORT_PACKAGES
        }
        cohort["@angular/cli"] = self.target_cli_exact
        cohort["@angular-devkit/build-angular"] = self.target_cli_exact
        for package, exact in (
            ("typescript", self.typescript_exact),
            ("rxjs", self.rxjs_exact),
            ("zone.js", self.zone_js_exact),
        ):
            if exact:
                cohort[package] = exact
        return cohort

    def target_requirements(self, package_names: Iterable[str]) -> dict[str, str]:
        """Return cohort pins only for direct packages present in a manifest."""
        names = {name for name in package_names if isinstance(name, str)}
        return {name: exact for name, exact in self.target_cohort().items() if name in names}

    @model_validator(mode="after")
    def validate_adjacent_families(self) -> CompatibilityCatalogueEntry:
        source = int(self.source_family.removeprefix("angular-").removesuffix(".x"))
        target = int(self.target_family.removeprefix("angular-").removesuffix(".x"))
        if target != source + 1:
            raise ValueError("compatibility entries must describe adjacent Angular major families")
        if self.support_level == "historical_validated" and self.fixture_status != "passed":
            raise ValueError("historical_validated requires a passed fixture suite")
        if self.support_level == "blocked" and not self.blockers:
            raise ValueError("blocked compatibility entries require a blocker")
        for proof in self.proven_runtime_evidence:
            source_major = self.source_family.removeprefix("angular-").removesuffix(".x") + "."
            target_major = self.target_family.removeprefix("angular-").removesuffix(".x") + "."
            if not proof.source_angular_exact.startswith(source_major):
                raise ValueError("runtime proof source exact does not match the catalogue source family")
            if not proof.target_angular_exact.startswith(target_major) or not proof.target_cli_exact.startswith(target_major):
                raise ValueError("runtime proof target exact does not match the catalogue target family")
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
            if not entry.source_node_ranges:
                serialized.pop("source_node_ranges", None)
            if not entry.target_node_ranges:
                serialized.pop("target_node_ranges", None)
            if not entry.rxjs_ranges:
                serialized.pop("rxjs_ranges", None)
            if not entry.proven_runtime_profiles:
                serialized.pop("proven_runtime_profiles", None)
            # Drop None-valued fields so the checksum is stable across schema
            # evolution and legacy versions checksum identically to their
            # original contracts.
            serialized = {key: value for key, value in serialized.items() if value is not None}
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
    target_family: str = Field(default="angular-21.x", pattern=r"^angular-(1[1-9]|2[01])\.x$")
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
    run_mode: Literal["PRODUCTION", "QUALIFICATION"] = "PRODUCTION"
    qualification_authorization_checksum: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    resolved_at: datetime

    @model_validator(mode="before")
    @classmethod
    def canonicalize_target_family(cls, values):
        if isinstance(values, dict) and isinstance(values.get("target_family"), str):
            target = values["target_family"].strip()
            if target.startswith("angular-"):
                values = {**values, "target_family": target}
            elif re.fullmatch(r"(?:1[1-9]|2[01])\.x", target):
                values = {**values, "target_family": f"angular-{target}"}
        return values


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
    classification: RuntimeCompatibilityClass = "EXACT_CERTIFIED"


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
    typescript_exact: str | None = None
    rxjs_exact: str | None = None
    zone_js_exact: str | None = None
    target_cohort: dict[str, str] = Field(default_factory=dict)
    node_exact: str | None = None
    npm_exact: str | None = None
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_classification: RuntimeCompatibilityClass | None = None


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
