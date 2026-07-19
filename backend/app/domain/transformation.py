"""Deterministic domain rules for G03 Angular transformation, evidence, and G08 acceptance.

This module deliberately has no persistence or filesystem side effects.  The
application service supplies already-computed evidence; later persistence work
can persist the resulting packages unchanged.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import Field

from app.domain.contracts import ArtifactRefDto, ContractModel, RiskLevel


# ── S3-F07 — Angular Update and Target Version Verification ──────────────


class AngularUpdateStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERACTIVE_BLOCKED = "interactive_blocked"


class TargetVersionStatus(str, Enum):
    VERIFIED = "verified"
    MISMATCH = "mismatch"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class PromptDetectionResult(str, Enum):
    NO_PROMPT = "no_prompt"
    PROMPT_DETECTED = "prompt_detected"
    UNCERTAIN = "uncertain"


class AngularUpdateCommand(ContractModel):
    """Resolved exact argv for the Angular update command."""

    executable: str = Field(default="npx")
    arguments: list[str] = Field(min_length=1)
    working_directory_alias: str = Field(default="sandbox")
    timeout_seconds: int = Field(default=600, gt=0)
    network_profile: str = Field(default="none")
    shell: bool = False

    @property
    def argv(self) -> list[str]:
        return [self.executable, *self.arguments]


class TargetVersionEvidence(ContractModel):
    """Multiple evidence sources compared for target version verification."""

    package_json_version: str | None = None
    lockfile_version: str | None = None
    ng_version_output: str | None = None
    dependency_tree_version: str | None = None
    resolved_target: str = Field(min_length=1)
    all_sources_agree: bool = False
    disagreements: list[str] = Field(default_factory=list)


class AngularUpdateResult(ContractModel):
    """Bounded result of executing and verifying the Angular update."""

    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    update_status: AngularUpdateStatus
    target_version_status: TargetVersionStatus
    resolved_target_version: str | None = None
    command_execution_id: str | None = None
    evidence: TargetVersionEvidence | None = None
    prompt_detected: PromptDetectionResult = PromptDetectionResult.NO_PROMPT
    error_message: str | None = None


class VersionEvidenceSource(str, Enum):
    PACKAGE_JSON = "package.json"
    PACKAGE_LOCK = "package-lock.json"
    NG_VERSION = "ng version"
    DEPENDENCY_TREE = "dependency_tree"


class AngularUpdateRequest(ContractModel):
    """Input to start an Angular update for a stage."""

    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    source_version: str = Field(min_length=1)
    target_version: str = Field(min_length=1)
    toolchain_profile_id: str | None = None
    prerequisite_artifact_ids: list[str] = Field(default_factory=list)


class AngularUpdateVerificationRequest(ContractModel):
    """Input to check the target version after update."""

    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    command_execution_id: str = Field(min_length=1)


# ── S3-F08 — Transformation Evidence and Risk Classification ─────────────


class ChangedFileClassification(str, Enum):
    LOW_RISK = "low_risk"
    MEDIUM_RISK = "medium_risk"
    HIGH_RISK = "high_risk"
    SENSITIVE = "sensitive"
    GENERATED = "generated"
    BINARY = "binary"
    FORBIDDEN = "forbidden"


class SensitiveChangeReason(str, Enum):
    AUTH_OR_API = "auth_or_api"
    BEHAVIOR_CHANGE = "behavior_change"
    SECURITY_RELEVANT = "security_relevant"
    CONFIGURATION_CHANGE = "configuration_change"
    BUILD_SYSTEM_CHANGE = "build_system_change"
    HIDDEN_MODERNIZATION = "hidden_modernization"
    BINARY_FILE = "binary_file"
    GENERATED_FILE = "generated_file"
    PACKAGE_LOCK_CHANGE = "package_lock_change"
    UNKNOWN = "unknown"


class ChangedFileEntry(ContractModel):
    """A single changed file with its risk classification and metadata."""

    file_path: str = Field(min_length=1)
    change_type: str = Field(pattern="^(added|modified|deleted|renamed)$")
    classification: ChangedFileClassification
    reason: SensitiveChangeReason | None = None
    lines_added: int = Field(default=0, ge=0)
    lines_removed: int = Field(default=0, ge=0)
    is_generated: bool = False
    is_binary: bool = False
    size_bytes: int = Field(default=0, ge=0)


class DiffSummary(ContractModel):
    """Summary of the full transformation unified diff."""

    total_files_changed: int = Field(ge=0)
    total_lines_added: int = Field(ge=0)
    total_lines_removed: int = Field(ge=0)
    files_by_classification: dict[str, int] = Field(default_factory=dict)
    changed_files: list[ChangedFileEntry] = Field(default_factory=list)
    diff_checksum: str = Field(min_length=1)


class PackageChangeSummary(ContractModel):
    """Summary of package.json and lockfile changes."""

    dependencies_added: list[str] = Field(default_factory=list)
    dependencies_removed: list[str] = Field(default_factory=list)
    dependencies_updated: list[dict[str, str]] = Field(default_factory=list)
    dev_dependencies_added: list[str] = Field(default_factory=list)
    dev_dependencies_removed: list[str] = Field(default_factory=list)
    dev_dependencies_updated: list[dict[str, str]] = Field(default_factory=list)
    angular_version_before: str | None = None
    angular_version_after: str | None = None
    other_major_changes: list[str] = Field(default_factory=list)


class ForbiddenChangeEntry(ContractModel):
    """A change flagged as forbidden or high-risk modernization."""

    file_path: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    risk_level: RiskLevel
    suggestion: str | None = None


class TransformationEvidenceResult(ContractModel):
    """Complete evidence output for the transformation."""

    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    diff: DiffSummary
    package_change: PackageChangeSummary | None = None
    migration_list: list[str] = Field(default_factory=list)
    forbidden_changes: list[ForbiddenChangeEntry] = Field(default_factory=list)
    overall_risk_level: RiskLevel = RiskLevel.LOW
    evidence_complete: bool = False
    block_reason: str | None = None


class TransformationEvidenceRequest(ContractModel):
    """Input to generate transformation evidence for a stage."""

    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    prerequisite_artifact_ids: list[str] = Field(default_factory=list)
    source_sandbox_path: str = Field(min_length=1)
    target_sandbox_path: str = Field(min_length=1)


# ── S3-F09 — G08 Transformation Acceptance Gate ──────────────────────────


class G08Decision(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_COMMENT = "approved_with_comment"
    MODIFICATION_REQUESTED = "modification_requested"
    REJECTED = "rejected"


class G08EvidencePackage(ContractModel):
    """Checksum-bound G08 evidence package referencing all transformation artifacts."""

    run_id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    gate_id: str = "G08"
    gate_version: str = Field(min_length=1)
    state_version: int = Field(ge=1)
    actor: str = Field(min_length=1)
    transformation_result: AngularUpdateResult
    evidence_result: TransformationEvidenceResult
    artifact_refs: tuple[ArtifactRefDto, ...] = ()
    artifact_set_checksum: str = Field(min_length=1)
    workspace_fingerprint: str = Field(min_length=1)
    package_checksum: str = Field(min_length=1)


class G08DecisionResult(ContractModel):
    """Result of applying a G08 decision."""

    package_checksum: str
    decision: G08Decision
    stale: bool = False
    reason: str | None = None


class G08EvidencePackageBuilder:
    """Build a canonical, checksum-bound G08 package from S3-F07 and S3-F08 evidence."""

    def build(
        self,
        *,
        run_id: str,
        stage_id: str,
        state_version: int,
        actor: str,
        gate_version: str,
        transformation_result: AngularUpdateResult,
        evidence_result: TransformationEvidenceResult,
        artifacts: list[ArtifactRefDto] | tuple[ArtifactRefDto, ...] = (),
        workspace_fingerprint: str,
    ) -> G08EvidencePackage:
        artifact_set_checksum = _artifact_set_checksum(artifacts)
        unsigned: dict[str, Any] = {
            "run_id": run_id,
            "stage_id": stage_id,
            "gate_id": "G08",
            "gate_version": gate_version,
            "state_version": state_version,
            "actor": actor,
            "transformation_result": transformation_result.model_dump(mode="json"),
            "evidence_result": evidence_result.model_dump(mode="json"),
            "artifact_set_checksum": artifact_set_checksum,
            "artifact_payload": [item.model_dump(mode="json") for item in artifacts],
            "workspace_fingerprint": workspace_fingerprint,
        }
        package_checksum = _checksum(unsigned)
        return G08EvidencePackage(
            run_id=run_id,
            stage_id=stage_id,
            gate_version=gate_version,
            state_version=state_version,
            actor=actor,
            transformation_result=transformation_result,
            evidence_result=evidence_result,
            artifact_refs=tuple(artifacts),
            artifact_set_checksum=artifact_set_checksum,
            workspace_fingerprint=workspace_fingerprint,
            package_checksum=package_checksum,
        )


class G08ApprovalService:
    """Apply the fail-closed G08 decision rules."""

    def decide(
        self,
        package: G08EvidencePackage,
        decision: G08Decision,
        *,
        comment: str | None = None,
    ) -> G08DecisionResult:
        if decision in {G08Decision.APPROVED, G08Decision.APPROVED_WITH_COMMENT}:
            if not package.evidence_result.evidence_complete:
                return G08DecisionResult(
                    package_checksum=package.package_checksum,
                    decision=G08Decision.REJECTED,
                    stale=True,
                    reason="transformation evidence is incomplete",
                )
            if package.evidence_result.overall_risk_level == RiskLevel.CRITICAL:
                return G08DecisionResult(
                    package_checksum=package.package_checksum,
                    decision=G08Decision.REJECTED,
                    stale=False,
                    reason="critical risk in transformation evidence requires remediation before approval",
                )
            if decision is G08Decision.APPROVED_WITH_COMMENT and not comment:
                raise ValueError("approved_with_comment requires a non-empty comment")
            return G08DecisionResult(
                package_checksum=package.package_checksum,
                decision=decision,
                reason=comment,
            )
        return G08DecisionResult(
            package_checksum=package.package_checksum,
            decision=decision,
            reason=comment,
        )


# ── Shared helpers ────────────────────────────────────────────────────────


def _artifact_set_checksum(artifacts: list[ArtifactRefDto] | tuple[ArtifactRefDto, ...]) -> str:
    return _checksum(
        [
            {"artifact_id": item.artifact_id, "checksum": item.checksum}
            for item in sorted(artifacts, key=lambda v: v.artifact_id)
        ]
    )


def _checksum(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
