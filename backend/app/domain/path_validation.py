"""Typed contracts for external source and generated-output path validation."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class PathValidationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_path: str = Field(min_length=1)
    target_parent_path: str | None = None
    target_output_path: str | None = None  # legacy adapter
    target_angular_family: str = "21.x"
    idempotency_key: str = Field(min_length=1)
    actor: str | None = None
    @field_validator("source_path", "idempotency_key")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip(): raise ValueError("path and idempotency values must not be blank")
        return value
    @model_validator(mode="after")
    def require_target_parent(self):
        if not (self.target_parent_path or self.target_output_path or "").strip(): raise ValueError("target_parent_path must not be blank")
        return self

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
    target_parent_path: str = ""
    generated_output_name: str = ""
    resolved_output_root: str = ""
    reservation_id: str | None = None
    reservation_expires_at: datetime | None = None
    platform_repository_root: str = ""
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