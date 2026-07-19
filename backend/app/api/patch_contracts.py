"""G07 API contracts — patch apply, repair validation, repair chain."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PatchApplyRequest(BaseModel):
    proposal_id: str = Field(min_length=1)
    diff_content: str = Field(min_length=1)
    expected_checksum: str = Field(min_length=1)
    expected_fingerprint: str = Field(min_length=1, description="Expected workspace fingerprint")
    expected_state_version: int = Field(ge=0)
    expected_plan_version: str = ""
    idempotency_key: str = ""
    actor: str = "system"
    workspace_root: str | None = None


class PatchApplyResultResponse(BaseModel):
    patch_apply_id: str
    status: str
    state_version: int
    idempotent_replay: bool = False
    artifact_refs: dict[str, str] = {}
    failure_evidence: dict[str, Any] | None = None


class RepairApplyRequest(BaseModel):
    idempotency_key: str = ""
    actor: str = "system"


class RepairApplyResponse(BaseModel):
    patch_apply_id: str
    status: str
    state_version: int
    idempotent_replay: bool = False
    artifact_refs: dict[str, str] = {}
    failure_evidence: dict[str, Any] | None = None


class ValidateRepairRequest(BaseModel):
    attempt_id: str = Field(min_length=1)
    preflight_id: str = Field(min_length=1)
    diff_content: str = Field(min_length=1)
    expected_profile_id: str = Field(min_length=1)
    actual_profile_id: str = Field(min_length=1)
    expected_plan_version: str = ""
    actual_plan_version: str = ""
    previous_errors: list[str] = []
    current_errors: list[str] = []
    artifact_set_checksum: str = ""
    plan_version: str = ""
    workspace_fingerprint: str = ""
    idempotency_key: str = ""
    actor: str = "system"


class ValidateRepairResponse(BaseModel):
    attempt_id: str
    preflight_status: str
    validation_status: str
    g11_gate_id: str
    g11_status: str
    state_version: int
    artifact_refs: dict[str, str] = {}
    idempotent_replay: bool = False


class G11DecisionRequest(BaseModel):
    gate_id: str = Field(min_length=1)
    decision: str = Field(description="APPROVED, REJECTED, or MODIFICATION_REQUESTED")
    actor: str = "system"
    rationale: str = ""
    current_state_version: int = 0
    current_artifact_checksum: str = ""
    current_workspace_fingerprint: str = ""
    idempotency_key: str = ""


class G11DecisionResponse(BaseModel):
    gate_id: str
    decision: str
    status: str
    stale_replay: bool = False


class RepairChainResponse(BaseModel):
    chain_id: str
    run_id: str
    status: str
    total_attempts: int = 0
    applied_attempts: int = 0
    duplicate_count: int = 0
    no_progress_reason: str | None = None
    recovery_action: str | None = None
    diagnostic_hold: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = []
    state_version: int = 0
    artifact_refs: dict[str, str] = {}


class RecoverRepairRequest(BaseModel):
    chain_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    stage_id: str = ""
    workspace_fingerprint_before: str = ""
    source_input_fingerprint: str = ""
    idempotency_key: str = ""
    actor: str = "system"


class RecoverRepairResponse(BaseModel):
    chain_id: str
    action: str
    status: str
    state_version: int
    artifact_refs: dict[str, str] = {}
    idempotent_replay: bool = False
