from typing import Any

from pydantic import Field

from app.domain.analysis import AnalysisArtifactInput, G04Decision
from app.domain.contracts import ContractModel


class AnalysisCreateRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    # Kept for safe backward compatibility; the backend derives the authority.
    prerequisite_artifacts: list[AnalysisArtifactInput] = Field(default_factory=list, max_length=32)
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    plan_version: str | None = Field(default=None, max_length=128)
    correlation_id: str | None = Field(default=None, max_length=128)


class G04DecisionApiRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    gate_version: str = Field(min_length=1, max_length=128)
    package_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    plan_version: str | None = Field(default=None, max_length=128)
    decision: G04Decision
    comment: str | None = Field(default=None, max_length=4000)


class AnalysisResponse(ContractModel):
    run_id: str
    analysis_id: str
    status: str
    package: dict[str, Any] | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    artifact_links: dict[str, str] = Field(default_factory=dict)
    package_checksum: str | None = None
    gate_id: str = "G04"
    gate_version: str = "g04-v1"
    gate_status: str
    gate_decision: str | None = None
    error_code: str | None = None
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False


class G04DecisionResponse(ContractModel):
    run_id: str
    gate_id: str = "G04"
    gate_version: str
    decision: G04Decision
    status: str
    accepted: bool
    package_checksum: str
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
