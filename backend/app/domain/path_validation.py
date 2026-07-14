"""Typed contracts for real source/target path safety validation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PathValidationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_path: str = Field(min_length=1)
    target_output_path: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    actor: str | None = None

    @field_validator("source_path", "target_output_path", "idempotency_key")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("path and idempotency values must not be blank")
        return value


class PathRuleResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    status: Literal["passed", "warning", "blocked"]
    message: str


class PathValidationSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    validation_id: str
    captured_at: datetime
    policy_version: str
    status: Literal["passed", "passed_with_warnings", "blocked"]
    source_path: str
    target_output_path: str
    source_fingerprint: str | None
    rules: list[PathRuleResult]
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    target_reservation_eligible: bool
    checksum: str


class PathValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    snapshot: PathValidationSnapshot