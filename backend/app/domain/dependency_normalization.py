"""Dependency normalization domain contracts — one complete manifest proposal (P3 V2.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEPENDENCY_NORMALIZATION_REPAIR_KIND = "dependency_manifest_normalization"
DEPENDENCY_NORMALIZATION_SCHEMA_VERSION = "dependency-normalization-v1"

# Frozen action literals — reviewer and service must not invent new actions.
_VALID_ACTIONS = frozenset({"KEEP", "UPGRADE", "REMOVE", "REPLACE"})


class DependencyNormalizationAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package: str = Field(min_length=1, max_length=256)
    section: Literal["dependencies", "devDependencies"]
    current_spec: str = Field(min_length=1, max_length=256)
    action: Literal["KEEP", "UPGRADE", "REMOVE", "REPLACE"]
    target_package: str | None = Field(default=None, min_length=1, max_length=256)
    target_version: str | None = Field(default=None, min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _check_replacement(self) -> "DependencyNormalizationAction":
        if self.action == "REPLACE":
            if not self.target_package or not self.target_version:
                raise ValueError("REPLACE requires target_package and target_version")
        elif self.action == "UPGRADE":
            if not self.target_version:
                raise ValueError("UPGRADE requires target_version")
            if self.target_package is not None:
                raise ValueError("UPGRADE must not set target_package")
        else:  # KEEP / REMOVE
            if self.target_package is not None or self.target_version is not None:
                raise ValueError(f"{self.action} must not set target_package/target_version")
        # forbid --force / flags in reason and version fields
        for val in (self.target_version or "", self.reason):
            if "--force" in val or "--legacy-peer-deps" in val:
                raise ValueError("forbidden flag in normalization fields")
        return self


class DependencyNormalizationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["dependency-normalization-v1"]
    analysis_summary: str = Field(min_length=1, max_length=4000)
    packages: list[DependencyNormalizationAction] = Field(min_length=1, max_length=128)

    @field_validator("packages")
    @classmethod
    def _no_duplicate_packages(cls, v: list[DependencyNormalizationAction]) -> list[DependencyNormalizationAction]:
        seen: set[str] = set()
        for item in v:
            if item.package in seen:
                raise ValueError(f"duplicate package: {item.package}")
            seen.add(item.package)
        return v

    def package_map(self) -> dict[str, DependencyNormalizationAction]:
        return {p.package: p for p in self.packages}
