"""Versioned S2-F07-I02 API contracts for plan review evidence."""

from typing import Any

from pydantic import Field

from app.domain.contracts import ContractModel
from app.domain.planning import PlanArtifactInput
from app.domain.planning_review import G06Decision, PlanRevisionChanges


class PlanRevisionApiRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    plan: dict[str, Any]
    stage_plan: dict[str, Any]
    changes: PlanRevisionChanges
    artifact_set_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    prerequisite_artifacts: list[PlanArtifactInput] = Field(default_factory=list, max_length=32)
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    correlation_id: str | None = Field(default=None, max_length=128)


class PlanningExplanationApiRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    plan: dict[str, Any]
    stage_plan: dict[str, Any]
    artifact_set_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    prerequisite_artifacts: list[PlanArtifactInput] = Field(default_factory=list, max_length=32)
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    plan_version: int = Field(ge=1)
    correlation_id: str | None = Field(default=None, max_length=128)


class G06DecisionApiRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    gate_version: str = Field(min_length=1, max_length=128)
    package_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    artifact_set_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    stage_plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    decision: G06Decision
    comment: str | None = Field(default=None, max_length=4000)
    correlation_id: str | None = Field(default=None, max_length=128)


class PlanReviewResponse(ContractModel):
    run_id: str
    status: str
    plan: dict[str, Any] | None = None
    stage_plan: dict[str, Any] | None = None
    plan_checksum: str | None = None
    stage_plan_checksum: str | None = None
    artifact_set_checksum: str | None = None
    computed_artifact_set_checksum: str | None = None
    diff: dict[str, Any] | None = None
    package: dict[str, Any] | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    artifact_links: dict[str, str] = Field(default_factory=dict)
    gate_id: str = "G06"
    gate_version: str = "g06-v1"
    gate_status: str = "blocked"
    gate_decision: str | None = None
    package_checksum: str | None = None
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False


class G06DecisionResponse(ContractModel):
    run_id: str
    gate_id: str = "G06"
    gate_version: str
    decision: G06Decision
    status: str
    accepted: bool
    package_checksum: str
    artifact_set_checksum: str
    plan_checksum: str
    stage_plan_checksum: str
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
