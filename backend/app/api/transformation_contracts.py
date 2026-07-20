"""Typed HTTP contracts for G03 transformation, evidence, and G08 approval surfaces."""

from typing import Any

from pydantic import Field

from app.domain.contracts import ContractModel
from app.domain.transformation import AngularUpdateStatus, G08Decision, TargetVersionStatus


# ── S3-F07 — Angular Update ──────────────────────────────────────────────


class AngularUpdateRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    source_version: str = Field(min_length=1)
    target_version: str = Field(min_length=1)
    toolchain_profile_id: str | None = None
    prerequisite_artifact_ids: list[str] = Field(default_factory=list)


class AngularUpdateResponse(ContractModel):
    run_id: str
    stage_id: str
    status: AngularUpdateStatus
    target_version_status: TargetVersionStatus | None = None
    resolved_target_version: str | None = None
    command_execution_id: str | None = None
    prompt_detected: str = "no_prompt"
    artifact_ids: list[str] = Field(default_factory=list)
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    error_message: str | None = None
    idempotent_replay: bool = False


class TargetVersionResponse(ContractModel):
    run_id: str
    stage_id: str
    target_version_status: TargetVersionStatus
    resolved_target_version: str | None = None
    evidence_sources: dict[str, str] = Field(default_factory=dict)
    all_sources_agree: bool = False
    disagreements: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)


# ── S3-F08 — Transformation Evidence ─────────────────────────────────────


class TransformationEvidenceRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    prerequisite_artifact_ids: list[str] = Field(default_factory=list)
    source_sandbox_path: str = Field(min_length=1)
    target_sandbox_path: str = Field(min_length=1)
    correlation_id: str | None = None


class TransformationEvidenceResponse(ContractModel):
    run_id: str
    stage_id: str
    status: str
    overall_risk_level: str = "low"
    total_files_changed: int = 0
    diff_checksum: str
    diff_summary: dict[str, Any] = Field(default_factory=dict)
    package_change: dict[str, Any] | None = None
    migration_list: list[str] = Field(default_factory=list)
    forbidden_changes: list[dict[str, Any]] = Field(default_factory=list)
    changed_file_classifications: dict[str, str] = Field(default_factory=dict)
    evidence_complete: bool = False
    artifact_ids: list[str] = Field(default_factory=list)
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    block_reason: str | None = None
    idempotent_replay: bool = False
    correlation_id: str | None = None
    source_sandbox_path: str | None = None
    target_sandbox_path: str | None = None


# ── S3-F09 — G08 Approval ────────────────────────────────────────────────


class G08DecisionRequest(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    decision: G08Decision
    comment: str | None = Field(default=None, max_length=4000)
    gate_id: str = Field(default="G08", min_length=1, max_length=16)


class G08ReviewResponse(ContractModel):
    run_id: str
    stage_id: str
    gate_id: str
    gate_version: str
    status: str
    decision: str | None = None
    package: dict[str, Any]
    package_checksum: str
    artifact_set_checksum: str
    workspace_fingerprint: str
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    idempotent_replay: bool = False
    stale_reason: str | None = None
    comment: str | None = None
