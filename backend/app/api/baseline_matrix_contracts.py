"""Typed HTTP contracts for the S1-F12 validation matrix."""
from typing import Any, Literal
from pydantic import Field
from app.domain.contracts import ContractModel
BaselineMatrixKind = Literal["build", "test", "lint"]
class BaselineValidationRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    prerequisite_artifact_ids: list[str] = Field(default_factory=list)
class BaselineTargetInventoryResponse(ContractModel):
    run_id: str
    targets: list[dict[str, Any]]
    package_json_checksum: str
    angular_json_present: bool
    state_version: int
    event_sequence: int
class BaselineValidationResponse(ContractModel):
    validation_id: str
    run_id: str
    kind: BaselineMatrixKind
    status: str
    targets: list[dict[str, Any]]
    results: list[dict[str, Any]]
    parser_summary: dict[str, Any] | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    baseline_checksum: str | None = None
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
