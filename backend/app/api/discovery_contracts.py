from typing import Any, Literal
from pydantic import Field
from app.domain.contracts import ContractModel
class DiscoveryCaptureRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    prerequisite_artifact_ids: list[str] = Field(min_length=1)
    prerequisite_artifact_checksums: dict[str, str] = Field(default_factory=dict)
class DiscoveryEvidenceResponse(ContractModel):
    run_id: str
    discovery_id: str
    status: Literal["completed", "blocked"]
    scanner_results: list[dict[str, Any]] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    prerequisite_artifact_ids: list[str] = Field(default_factory=list)
    error_code: str | None = None
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
