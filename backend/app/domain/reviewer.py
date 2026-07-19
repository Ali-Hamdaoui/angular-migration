"""Domain contracts for the Repair Reviewer application service."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from app.domain.contracts import ContractModel
from app.domain.proposer import ProposerArtifactInput, ProposerCandidate


class ReviewerDecision(str, Enum):
    ACCEPT = "accept"
    REQUEST_REVISION = "request_revision"
    REJECT = "reject"
    INSUFFICIENT_CONTEXT = "insufficient_context"


class ReviewRequest(ContractModel):
    """Application input for invoking the Repair Reviewer.

    The Reviewer never authors a diff — only the Proposer may do that.
    The proposer_candidate field carries the ProposerCandidate to review.
    """

    run_id: str = Field(min_length=1, max_length=64)
    repair_attempt_id: str = Field(min_length=1, max_length=64)
    proposal_id: str = Field(min_length=1, max_length=128)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    proposer_candidate: ProposerCandidate
    context_artifacts: list[ProposerArtifactInput] = Field(
        default_factory=list, max_length=8
    )
    workspace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    correlation_id: str | None = Field(default=None, max_length=128)
    artifact_set_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @property
    def review_input_checksum(self) -> str:
        """Checksum of all deterministic reviewer inputs for binding verification."""
        values: list[dict[str, Any]] = [
            self.proposer_candidate.model_dump(mode="json"),
            {"artifact_set_checksum": self.artifact_set_checksum},
        ]
        encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


class ReviewDecision(ContractModel):
    """Non-authoring reviewer decision matching repair_review_decision.schema.json.

    This schema intentionally contains NO diff or patch field — the Reviewer
    never authors a repair diff.  The proposal_diff_checksum binds this review
    to exactly one proposer output.
    """

    review_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    reviewer_invocation_id: str = Field(min_length=1)
    decision: ReviewerDecision
    proposal_diff_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    review_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    critique: list[str] = Field(default_factory=list, max_length=64)
    revision_instructions: list[str] = Field(default_factory=list, max_length=64)
    requested_context: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def forbid_authoring_fields(self) -> "ReviewDecision":
        """Defence-in-depth: reject any field that looks like authoring content."""
        data = self.model_dump(mode="json")
        authoring_keys = {"diff_content", "diff", "patch", "commands", "changed_files"}
        if authoring_keys.intersection(data):
            raise ValueError(
                "ReviewDecision must not contain diff, patch, or authoring fields"
            )
        return self


class ReviewResult(ContractModel):
    """The unpersisted application result consumed by I02 persistence."""

    run_id: str = Field(min_length=1, max_length=64)
    repair_attempt_id: str = Field(min_length=1, max_length=64)
    proposal_id: str = Field(min_length=1, max_length=128)
    decision: ReviewerDecision
    review_decision: ReviewDecision
    review_output_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    model_provenance: dict[str, str]
    usage: dict[str, Any]
    prompt_version: str
    schema_version: str
    revision_count: int = Field(default=0, ge=0, le=10)
    workspace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
