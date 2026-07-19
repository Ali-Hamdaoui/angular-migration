"""Typed HTTP contracts for the repair-attempt proposer and reviewer surface."""

from typing import Any

from pydantic import Field

from app.domain.contracts import ContractModel
from app.domain.proposer import ProposerStatus


# ── Proposer ──────────────────────────────────────────────────────────────────


class ProposerRequestDto(ContractModel):
    """API input for invoking the Repair Proposer."""

    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str | None = Field(default=None, min_length=1, max_length=128)
    failure_artifact_id: str = Field(min_length=1, max_length=128)
    failure_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    context_pack_artifact_id: str = Field(min_length=1, max_length=128)
    context_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    workspace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    correlation_id: str | None = Field(default=None, max_length=128)


class ProposerDiagnosisDto(ContractModel):
    """AI diagnosis that accompanies a proposer result."""

    root_cause: str
    fix_strategy: str
    evidence_references: list[str] = Field(default_factory=list)
    confidence: str
    deterministic_input_checksum: str


class ProposerCandidateDto(ContractModel):
    """Candidate diff produced by the Proposer LLM."""

    diff_content: str
    diff_checksum: str
    changed_files: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)


class ProposerResponseDto(ContractModel):
    """API response for a proposer generate or retrieval."""

    run_id: str
    repair_attempt_id: str
    status: ProposerStatus
    proposer_invocation_id: str
    diagnosis: ProposerDiagnosisDto
    candidate: ProposerCandidateDto | None = None
    model_provenance: dict[str, str] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    prompt_version: str = ""
    schema_version: str = ""
    revision_count: int = 0
    artifact_set_checksum: str = ""
    proposer_output_checksum: str = ""
    workspace_fingerprint: str = ""


# ── Reviewer ──────────────────────────────────────────────────────────────────


class ReviewerRequestDto(ContractModel):
    """API input for invoking the Repair Reviewer."""

    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str | None = Field(default=None, min_length=1, max_length=128)
    proposal_id: str = Field(min_length=1, max_length=128)
    proposer_candidate_diff: str = Field(min_length=1)
    proposer_candidate_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    proposer_candidate_files: list[str] = Field(default_factory=list, max_length=64)
    proposer_candidate_risks: list[str] = Field(default_factory=list, max_length=32)
    proposer_candidate_validations: list[str] = Field(
        default_factory=list, max_length=32
    )
    artifact_set_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    context_artifact_ids: list[str] = Field(default_factory=list, max_length=8)
    context_artifact_checksums: dict[str, str] = Field(default_factory=dict)
    workspace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    correlation_id: str | None = Field(default=None, max_length=128)


class ReviewDecisionDto(ContractModel):
    """Non-authoring reviewer decision."""

    review_id: str
    proposal_id: str
    reviewer_invocation_id: str
    decision: str
    proposal_diff_checksum: str
    review_checksum: str
    critique: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    requested_context: list[str] = Field(default_factory=list)


class ReviewResponseDto(ContractModel):
    """API response for a reviewer invocation."""

    run_id: str
    repair_attempt_id: str
    proposal_id: str
    decision: str
    review_decision: ReviewDecisionDto
    review_output_checksum: str
    model_provenance: dict[str, str] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    prompt_version: str = ""
    schema_version: str = ""
    revision_count: int = 0
    workspace_fingerprint: str = ""


# ── Revisions ─────────────────────────────────────────────────────────────────


class RevisionRequestDto(ContractModel):
    """API input for requesting a revision cycle."""

    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str | None = Field(default=None, min_length=1, max_length=128)
    proposal_id: str = Field(min_length=1, max_length=128)
    revision_instructions: list[str] = Field(min_length=1, max_length=64)
    context_artifact_ids: list[str] = Field(default_factory=list, max_length=8)
    context_artifact_checksums: dict[str, str] = Field(default_factory=dict)
    workspace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    correlation_id: str | None = Field(default=None, max_length=128)


class RevisionResponseDto(ContractModel):
    """API response for a revision cycle."""

    run_id: str
    repair_attempt_id: str
    proposal_id: str
    decision: str
    review_decision: ReviewDecisionDto
    review_output_checksum: str
    model_provenance: dict[str, str] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    prompt_version: str = ""
    schema_version: str = ""
    revision_count: int = 0
    workspace_fingerprint: str = ""
    revision_cycle_complete: bool = False
