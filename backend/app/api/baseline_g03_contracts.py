from typing import Any
from pydantic import Field
from app.domain.contracts import ContractModel
class BaselineQualifyRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    policy: str = Field(default="strict_clean", pattern="^(strict_clean|qualified_known_failures)$")
    company_policy_allows_known_failures: bool = False
    prerequisite_artifact_ids: list[str] = Field(default_factory=list)
    prerequisite_artifact_checksums: dict[str, str] = Field(default_factory=dict)
class G03DecisionRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    decision: str = Field(pattern="^(approved|modification_requested|rejected)$")
    comment: str | None = Field(default=None, max_length=4000)
class BaselineAssessmentResponse(ContractModel):
    run_id: str
    assessment_id: str
    status: str
    policy: str
    policy_version: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    known_failures: list[dict[str, Any]] = Field(default_factory=list)
    evidence_confidence: dict[str, str] = Field(default_factory=dict)
    evidence_set_checksum: str
    sandbox_fingerprint: str
    execution_profile_checksum: str
    package_checksum: str
    artifact_ids: list[str] = Field(default_factory=list)
    state_version: int
    event_sequence: int
    g03_decision: str | None = None
    stale_reason: str | None = None
    idempotent_replay: bool = False
