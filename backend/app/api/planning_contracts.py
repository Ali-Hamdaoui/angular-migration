"""Versioned API contracts for persisted S2-F06 plan evidence."""

from typing import Any

from pydantic import Field

from app.domain.planning import PlanArtifactInput
from app.domain.contracts import ContractModel


class PlanCreateRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    source_exact: str = Field(min_length=1, max_length=64)
    source_family: str = Field(pattern=r"^angular-(1[1-9]|2[01])\.x$")
    target_family: str = Field(default="angular-21.x", pattern=r"^angular-(1[2-9]|2[01])\.x$")
    catalogue_version: str = Field(min_length=1, max_length=128)
    input_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence_set_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    input_workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    execution_profile_id: str = Field(min_length=1, max_length=128)
    package_manager: str = Field(default="npm", min_length=1, max_length=32)
    resolved_scripts: dict[str, str] = Field(default_factory=dict)
    project_targets: dict[str, str] = Field(default_factory=dict)
    stage_route: list[tuple[str, ...]] = Field(min_length=1, max_length=10)
    target_cli_exact: str | None = Field(default=None, max_length=64)
    builder: str = Field(min_length=1, max_length=256)
    prerequisite_artifacts: list[PlanArtifactInput] = Field(min_length=1, max_length=32)
    validation_policy_id: str = Field(default="angular-stage-standard-v2", min_length=1, max_length=128)
    recovery_policy_id: str = Field(default="safe-boundary-v1", min_length=1, max_length=128)
    repair_policy_id: str = Field(default="proposer-reviewer-human-v1", min_length=1, max_length=128)
    correlation_id: str | None = Field(default=None, max_length=128)
    capability_facts: list[dict[str, str]] = Field(default_factory=list, max_length=256)


class PlanResponse(ContractModel):
    run_id: str
    status: str
    plan: dict[str, Any]
    stage_plan: dict[str, Any]
    plan_checksum: str
    stage_plan_checksum: str
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str] = Field(default_factory=dict)
    artifact_links: dict[str, str] = Field(default_factory=dict)
    builder_decision: dict[str, Any]
    state_version: int
    event_sequence: int
    idempotent_replay: bool = False
