"""Third-party compatibility scanner contracts (V2 F15).

The scanner extracts a project's third-party dependency inventory, resolves each
dependency against the compatibility catalogue, and classifies per-dependency
compatibility for a stage's target Angular major.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


#: Angular platform packages managed by ng update (never third-party inventory).
ANGULAR_SCOPED_PACKAGES = frozenset(
    {
        "@angular/core", "@angular/common", "@angular/compiler", "@angular/forms",
        "@angular/platform-browser", "@angular/platform-browser-dynamic",
        "@angular/router", "@angular/animations", "@angular/cli", "@angular/compiler-cli",
        "@angular/language-service", "@angular/localize", "@angular/service-worker",
        "@angular/upgrade", "@angular/elements", "@angular/cdk", "@angular/material",
    }
)
#: Core toolchain packages tracked separately from third-party inventory.
TOOLCHAIN_PACKAGES = frozenset({"typescript", "rxjs", "zone.js", "jasmine-core", "karma", "ts-node"})


class DependencyInventoryItem(_ImmutableModel):
    """One third-party dependency with its declared and resolved versions."""

    name: str = Field(min_length=1)
    declared: str = Field(min_length=1)
    resolved: str | None = None
    scope: Literal["dependency", "devDependency", "peerDependency"] = "dependency"


class DependencyCompatibilityFinding(_ImmutableModel):
    """Classification of one dependency against a stage target."""

    name: str
    declared: str
    resolved: str | None = None
    target_major: int
    status: Literal["compatible", "incompatible", "unknown", "peer_conflict"]
    detail: str = ""


class DependencyCompatibilityReport(_ImmutableModel):
    """Per-stage third-party compatibility report."""

    run_id: str
    stage_id: str
    source_major: int
    target_major: int
    inventory: tuple[DependencyInventoryItem, ...] = Field(default_factory=tuple)
    findings: tuple[DependencyCompatibilityFinding, ...] = Field(default_factory=tuple)
    status: str  # "compatible" | "warnings" | "blocked"
    blockers: tuple[str, ...] = Field(default_factory=tuple)
