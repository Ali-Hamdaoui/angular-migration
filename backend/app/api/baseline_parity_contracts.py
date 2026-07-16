from typing import Any
from pydantic import Field
from app.domain.contracts import ContractModel


class BaselineParityCaptureRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    prerequisite_artifact_ids: list[str] = Field(default_factory=list)


class BaselineParityResponse(ContractModel):
    run_id: str
    evidence_id: str
    status: str
    schema_version: str
    parser_version: str
    baseline_checksum: str | None
    runtime_profile_id: str | None
    runtime_checksum: str | None
    failures: list[dict[str, Any]] = Field(default_factory=list)
    routes: list[dict[str, Any]] = Field(default_factory=list)
    backend_integration: dict[str, Any] = Field(default_factory=dict)
    anchors: list[dict[str, Any]] = Field(default_factory=list)
    confidence: dict[str, str] = Field(default_factory=dict)
    source_artifact_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
