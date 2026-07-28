"""Typed API contracts for the S2-F05 feasibility and G05 surface."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.domain.compatibility import CompatibilityArtifact, Stage1ExecutionProfile
from app.domain.contracts import ContractModel
from app.domain.execution_profile import RuntimeCandidate


class FeasibilityCreateRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    source_angular_exact: str = Field(min_length=1, max_length=64)
    catalogue_version: str = Field(min_length=1, max_length=128)
    registry_snapshot_id: str = Field(min_length=1, max_length=128)
    registry_snapshot_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    prerequisite_artifacts: list[CompatibilityArtifact] = Field(min_length=1, max_length=32)
    runtime_candidates: tuple[RuntimeCandidate, ...] = ()
    workspace_topology: str = Field(default="single_application_cli_workspace", min_length=1, max_length=128)
    dependency_findings: tuple[str, ...] = ()
    source_execution_profile_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    plan_version: str | None = Field(default=None, max_length=128)
    correlation_id: str | None = Field(default=None, max_length=128)
    resolved_at: datetime | None = None


class FeasibilityResolveActionRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class PlanningCommandResponse(ContractModel):
    job_id: str
    status: str
    current_step: str
    correlation_id: str | None = None


class G05DecisionRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    gate_version: str = Field(min_length=1, max_length=64)
    package_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    artifact_set_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    plan_version: str | None = Field(default=None, max_length=128)
    decision: Literal["approve", "approve_with_comment", "request_modification", "reject"]
    comment: str | None = Field(default=None, max_length=4000)


class FeasibilityResponse(ContractModel):
    run_id: str
    resolution_id: str
    status: str
    source_exact: str
    source_family: str
    target_family: str
    support_level: str
    catalogue_snapshot: dict[str, Any] = Field(default_factory=dict)
    registry_snapshot: dict[str, Any] = Field(default_factory=dict)
    runtime_candidates: list[dict[str, Any]] = Field(default_factory=list)
    route: list[dict[str, Any]]
    selected_profile: Stage1ExecutionProfile | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    package: dict[str, Any]
    package_checksum: str
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    artifact_links: dict[str, str] = Field(default_factory=dict)
    gate_id: str = "G05"
    gate_version: str = "g05-v1"
    gate_status: str
    gate_decision: str | None = None
    gate_created_at: datetime | None = None
    gate_expires_at: datetime | None = None
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False


class G05DecisionResponse(ContractModel):
    run_id: str
    gate_id: str = "G05"
    gate_version: str
    decision: str
    status: str
    accepted: bool
    package_checksum: str
    artifact_set_checksum: str
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
