"""Domain contracts for the bounded Analysis Agent application service."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from app.domain.contracts import ContractModel


class G04Decision(str, Enum):
    APPROVE = "approve"
    APPROVE_WITH_COMMENT = "approve_with_comment"
    REQUEST_MODIFICATION = "request_modification"
    REJECT = "reject"


class AnalysisReviewDecision(str, Enum):
    ACCEPT = "accept"
    REQUEST_REVISION = "request_revision"
    REJECT = "reject"
    INSUFFICIENT_CONTEXT = "insufficient_context"


class AnalysisArtifactInput(ContractModel):
    """A registered deterministic artifact allowed into an analysis request."""

    artifact_id: str = Field(min_length=1, max_length=128)
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class AnalysisRequest(ContractModel):
    """Application input; repository content is supplied only by artifact ID."""

    run_id: str = Field(min_length=1, max_length=64)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    prerequisite_artifacts: list[AnalysisArtifactInput] = Field(min_length=1, max_length=32)
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    plan_version: str | None = Field(default=None, max_length=128)
    correlation_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def unique_artifacts(self) -> "AnalysisRequest":
        ids = [item.artifact_id for item in self.prerequisite_artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("prerequisite_artifacts must contain unique artifact IDs")
        return self

    @property
    def artifact_set_checksum(self) -> str:
        value = [item.model_dump(mode="json") for item in self.prerequisite_artifacts]
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


class AnalysisNarrative(ContractModel):
    """AI interpretation kept separate from deterministic machine facts."""

    summary: str = Field(min_length=1, max_length=12000)
    risk_groups: list[dict[str, Any]] = Field(default_factory=list, max_length=64)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=64)
    evidence_confidence: str = Field(min_length=1, max_length=64)
    recommended_next_action: str = Field(min_length=1, max_length=256)
    deterministic_input_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class AnalysisReview(ContractModel):
    """Non-authoring phase-review result bound to one proposer output."""

    decision: AnalysisReviewDecision
    notes: list[str] = Field(default_factory=list, max_length=64)
    risks: list[str] = Field(default_factory=list, max_length=64)
    policy_concerns: list[str] = Field(default_factory=list, max_length=64)
    confidence: str = Field(min_length=1, max_length=64)
    deterministic_input_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    proposer_output_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class AnalysisPackage(ContractModel):
    """The reviewable, unpersisted application result consumed by I02."""

    run_id: str
    artifact_set_checksum: str
    deterministic_input_artifacts: list[AnalysisArtifactInput]
    narrative: AnalysisNarrative
    proposer_output_checksum: str
    model_provenance: dict[str, str]
    usage: dict[str, Any]
    prompt_version: str
    schema_version: str
    reviewer: AnalysisReview
    reviewer_output_checksum: str
    reviewer_provenance: dict[str, str]
    reviewer_usage: dict[str, Any]
    reviewer_prompt_version: str
    reviewer_schema_version: str
    revision_count: int = Field(default=0, ge=0, le=2)
    workspace_fingerprint: str | None = None
    plan_version: str | None = None
    review_status: str = "accepted"


class G04DecisionRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    gate_version: str = Field(min_length=1, max_length=128)
    package_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    plan_version: str | None = Field(default=None, max_length=128)
    decision: G04Decision
    comment: str | None = Field(default=None, max_length=4000)


class G04DecisionResult(ContractModel):
    run_id: str
    decision: G04Decision
    accepted: bool
    state_version: int
    gate_version: str
    artifact_set_checksum: str
    review_status: str
