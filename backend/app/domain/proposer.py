"""Domain contracts for the Repair Proposer application service."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from app.domain.contracts import ContractModel


class ProposerStatus(str, Enum):
    CANDIDATE = "candidate"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    NOT_REPAIRABLE = "not_repairable"


class ProposerArtifactInput(ContractModel):
    """A registered deterministic artifact allowed into a proposer request."""

    artifact_id: str = Field(min_length=1, max_length=128)
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ProposerRequest(ContractModel):
    """Application input for invoking the Repair Proposer."""

    run_id: str = Field(min_length=1, max_length=64)
    repair_attempt_id: str = Field(min_length=1, max_length=64)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    failure_artifact: ProposerArtifactInput
    context_pack_artifact: ProposerArtifactInput
    workspace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    correlation_id: str | None = Field(default=None, max_length=128)

    @property
    def artifact_set_checksum(self) -> str:
        values = [self.failure_artifact.model_dump(mode="json"), self.context_pack_artifact.model_dump(mode="json")]
        encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


class ProposerDiagnosis(ContractModel):
    """AI interpretation of the failure evidence."""

    root_cause: str = Field(min_length=1, max_length=12000)
    fix_strategy: str = Field(min_length=1, max_length=12000)
    evidence_references: list[str] = Field(default_factory=list, max_length=32)
    confidence: str = Field(min_length=1, max_length=64)
    deterministic_input_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ProposerCandidate(ContractModel):
    """The candidate diff produced by the Proposer LLM."""

    diff_content: str = Field(min_length=1)
    diff_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    changed_files: list[str] = Field(min_length=1, max_length=64)
    risk_notes: list[str] = Field(default_factory=list, max_length=32)
    validation_notes: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_diff_format(self) -> "ProposerCandidate":
        if not self.diff_content.strip().startswith("---"):
            raise ValueError("diff_content must be a valid unified diff starting with '---'")
        return self


class ProposerResult(ContractModel):
    """The unpersisted application result consumed by I02 persistence."""

    run_id: str
    repair_attempt_id: str
    status: ProposerStatus
    proposer_invocation_id: str
    diagnosis: ProposerDiagnosis
    candidate: ProposerCandidate | None = None
    artifact_set_checksum: str
    proposer_output_checksum: str
    model_provenance: dict[str, str]
    usage: dict[str, Any]
    prompt_version: str
    schema_version: str
    revision_of: str | None = None
    revision_count: int = 0
    workspace_fingerprint: str

    @model_validator(mode="after")
    def require_candidate_when_candidate_status(self) -> "ProposerResult":
        if self.status is ProposerStatus.CANDIDATE and self.candidate is None:
            raise ValueError("candidate is required when status is 'candidate'")
        if self.status is not ProposerStatus.CANDIDATE and self.candidate is not None:
            raise ValueError("candidate must be None when status is not 'candidate'")
        return self
