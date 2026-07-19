"""Immutable contracts for the S2-F07 Planning review application boundary."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from app.domain.contracts import ContractModel
from app.domain.planning import PlanArtifactInput


class PlanRevisionField(str, Enum):
    CATALOGUE_VERSION = "catalogue_version"
    EXECUTION_PROFILE_ID = "execution_profile_id"
    TARGET_CLI_EXACT = "target_cli_exact"
    VALIDATION_POLICY_ID = "validation_policy_id"
    RECOVERY_POLICY_ID = "recovery_policy_id"
    REPAIR_POLICY_ID = "repair_policy_id"
    BUILDER = "builder"


class PlanRevisionChanges(ContractModel):
    """The only plan fields a reviewer may request to be rebuilt."""

    catalogue_version: str | None = Field(default=None, min_length=1, max_length=128)
    execution_profile_id: str | None = Field(default=None, min_length=1, max_length=128)
    target_cli_exact: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$", max_length=64)
    validation_policy_id: str | None = Field(default=None, min_length=1, max_length=128)
    recovery_policy_id: str | None = Field(default=None, min_length=1, max_length=128)
    repair_policy_id: str | None = Field(default=None, min_length=1, max_length=128)
    builder: str | None = Field(default=None, min_length=1, max_length=256)

    @property
    def changed_fields(self) -> tuple[PlanRevisionField, ...]:
        return tuple(PlanRevisionField(name) for name, value in self.model_dump().items() if value is not None)

    @model_validator(mode="after")
    def require_change(self) -> "PlanRevisionChanges":
        if not self.changed_fields:
            raise ValueError("at least one approved plan field must change")
        return self


class PlanRevisionRequest(ContractModel):
    run_id: str = Field(min_length=1, max_length=128)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    plan: dict[str, Any]
    stage_plan: dict[str, Any]
    changes: PlanRevisionChanges
    artifact_set_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    prerequisite_artifacts: tuple[PlanArtifactInput, ...] = ()
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    correlation_id: str | None = Field(default=None, max_length=128)


class PlanVersionDiff(ContractModel):
    from_version: int = Field(ge=1)
    to_version: int = Field(ge=2)
    changed_fields: tuple[PlanRevisionField, ...] = Field(min_length=1)
    changes: dict[str, Any]
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class PlanRevisionResult(ContractModel):
    run_id: str
    status: Literal["revised"] = "revised"
    plan: dict[str, Any]
    stage_plan: dict[str, Any]
    plan_checksum: str
    stage_plan_checksum: str
    diff: PlanVersionDiff
    stale_approval_ids: tuple[str, ...] = ()
    state_version: int = Field(ge=1)
    idempotent_replay: bool = False


class PlanningExplanationRequest(ContractModel):
    run_id: str = Field(min_length=1, max_length=128)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    plan: dict[str, Any]
    stage_plan: dict[str, Any]
    artifact_set_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    prerequisite_artifacts: tuple[PlanArtifactInput, ...] = ()
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    plan_version: int = Field(ge=1)
    correlation_id: str | None = Field(default=None, max_length=128)


class PlanningReviewDecision(str, Enum):
    ACCEPT = "accept"
    REQUEST_REVISION = "request_revision"
    REJECT = "reject"
    INSUFFICIENT_CONTEXT = "insufficient_context"


class PlanningNarrative(ContractModel):
    summary: str = Field(min_length=1, max_length=12000)
    rationale: list[str] = Field(default_factory=list, max_length=64)
    risks: list[str] = Field(default_factory=list, max_length=64)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=64)
    deterministic_plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class PlanningReview(ContractModel):
    decision: PlanningReviewDecision
    notes: list[str] = Field(default_factory=list, max_length=64)
    policy_concerns: list[str] = Field(default_factory=list, max_length=64)
    confidence: str = Field(min_length=1, max_length=64)
    deterministic_plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    proposer_output_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class PlanningPackage(ContractModel):
    run_id: str
    plan_version: int = Field(ge=1)
    artifact_set_checksum: str
    deterministic_plan_checksum: str
    plan_checksum: str
    stage_plan_checksum: str
    narrative: PlanningNarrative
    proposer_output_checksum: str
    reviewer: PlanningReview
    reviewer_output_checksum: str
    usage: dict[str, Any]
    reviewer_usage: dict[str, Any]
    revision_count: int = Field(default=0, ge=0, le=1)
    workspace_fingerprint: str | None = None
    review_status: Literal["accepted"] = "accepted"


class G06Decision(str, Enum):
    APPROVE = "approve"
    APPROVE_WITH_COMMENT = "approve_with_comment"
    REQUEST_MODIFICATION = "request_modification"
    REJECT = "reject"


class G06DecisionRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    gate_version: str = Field(min_length=1, max_length=128)
    artifact_set_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    stage_plan_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    workspace_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    decision: G06Decision
    comment: str | None = Field(default=None, max_length=4000)


class G06Gate(ContractModel):
    run_id: str
    gate_version: str
    status: Literal["pending", "approved", "request_modification", "rejected", "stale"]
    artifact_set_checksum: str
    plan_checksum: str
    stage_plan_checksum: str
    workspace_fingerprint: str | None = None
    state_version: int = Field(ge=1)


class G06DecisionResult(ContractModel):
    run_id: str
    decision: G06Decision
    accepted: bool
    status: str
    gate_version: str
    artifact_set_checksum: str
    plan_checksum: str
    stage_plan_checksum: str
    state_version: int = Field(ge=1)
    idempotent_replay: bool = False
