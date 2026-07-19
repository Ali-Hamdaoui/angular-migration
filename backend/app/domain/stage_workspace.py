"""Deterministic domain rules for stage workspace preparation and G07 gate.

This module has no persistence or filesystem side effects.  Application
services supply the already-computed evidence; persistence layers store
the resulting package unchanged.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import Field

from app.domain.contracts import ArtifactRefDto, ContractModel


class G07Decision(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_COMMENT = "approved_with_comment"
    MODIFICATION_REQUESTED = "modification_requested"
    REJECTED = "rejected"


class StageStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    PLAN_LOCKED = "plan_locked"
    WAITING_APPROVAL = "waiting_approval"
    SANDBOX_READY = "sandbox_ready"
    BOOTSTRAP_INSTALLING = "bootstrap_installing"
    BOOTSTRAP_COMPLETED = "bootstrap_completed"
    BOOTSTRAP_FAILED = "bootstrap_failed"
    FAILED = "failed"


class WorkspaceCopyReport(ContractModel):
    """Report of the stage workspace copy operation."""

    source_path: str = Field(min_length=1)
    destination_path: str = Field(min_length=1)
    file_count: int = Field(ge=0)
    total_size_bytes: int = Field(ge=0)
    destination_fingerprint: str = Field(min_length=1)
    symlinks_preserved: bool = True
    completed_at: str = Field(min_length=1)


class StageExecutionPlan(ContractModel):
    """The locked execution plan for a stage."""

    stage_key: str = Field(min_length=1)
    source_version_family: str = Field(min_length=1)
    target_version_family: str = Field(min_length=1)
    source_angular_version: str | None = None
    target_angular_version: str | None = None
    toolchain_profile: str = Field(default="npm-ci")
    approved_commands: tuple[str, ...] = ("npm ci",)
    plan_version: str = Field(min_length=1)
    plan_checksum: str = Field(default="", min_length=0)


class StageInputManifest(ContractModel):
    """Input manifest for the stage sandbox preparation."""

    stage_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    source_fingerprint: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    plan: StageExecutionPlan
    manifest_checksum: str = Field(min_length=1)


class StageFingerprint(ContractModel):
    """Workspace fingerprint for a stage sandbox."""

    workspace_path: str = Field(min_length=1)
    fingerprint: str = Field(default="", min_length=0)
    policy_version: str = Field(min_length=1)
    file_count: int = Field(ge=0)
    total_size_bytes: int = Field(ge=0)

    @property
    def is_valid(self) -> bool:
        return len(self.fingerprint) > 0


class G07ApprovalPackage(ContractModel):
    """Checksum-bound evidence package for G07 gate decision."""

    run_id: str = Field(min_length=1)
    gate_id: str = "G07"
    gate_version: str = Field(min_length=1)
    state_version: int = Field(ge=1)
    actor: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    stage_key: str = Field(min_length=1)
    plan_version: str = Field(min_length=1)
    source_fingerprint: str = Field(min_length=1)
    workspace_fingerprint: str = Field(min_length=1)
    artifact_set_checksum: str = Field(min_length=1)
    input_manifest: StageInputManifest
    copy_report: WorkspaceCopyReport
    artifacts: tuple[ArtifactRefDto, ...] = ()
    package_checksum: str = Field(min_length=1)


class G07ApprovalResult(ContractModel):
    package_checksum: str
    decision: G07Decision
    stage_boundary: str | None = None
    stale: bool = False
    reason: str | None = None


class StageSandboxVerification(ContractModel):
    """Verification result for the created stage sandbox."""

    stage_id: str = Field(min_length=1)
    sandbox_path: str = Field(min_length=1)
    pre_fingerprint: StageFingerprint
    post_fingerprint: StageFingerprint
    verification_checksum: str = Field(min_length=1)
    verified: bool


class BootstrapInstallResult(ContractModel):
    """Result of a stage bootstrap install command."""

    stage_id: str = Field(min_length=1)
    command: str = Field(min_length=1)
    exit_code: int | None = None
    stdout_checksum: str = Field(min_length=1)
    stderr_checksum: str = Field(min_length=1)
    duration_ms: int | None = None
    pre_fingerprint: StageFingerprint
    post_fingerprint: StageFingerprint
    succeeded: bool


class G07ApprovalPackageBuilder:
    """Build a canonical, checksum-bound G07 package from stage evidence."""

    def build(
        self,
        *,
        run_id: str,
        state_version: int,
        actor: str,
        stage_id: str,
        stage_key: str,
        gate_version: str,
        plan_version: str,
        source_fingerprint: str,
        workspace_fingerprint: str,
        input_manifest: StageInputManifest,
        copy_report: WorkspaceCopyReport,
        artifacts: list[ArtifactRefDto] | tuple[ArtifactRefDto, ...] = (),
    ) -> G07ApprovalPackage:
        unsigned = {
            "run_id": run_id,
            "gate_id": "G07",
            "gate_version": gate_version,
            "state_version": state_version,
            "actor": actor,
            "stage_id": stage_id,
            "stage_key": stage_key,
            "plan_version": plan_version,
            "source_fingerprint": source_fingerprint,
            "workspace_fingerprint": workspace_fingerprint,
            "artifact_set_checksum": _artifact_set_checksum(artifacts),
            "artifact_payload": [item.model_dump(mode="json") for item in artifacts],
            "input_manifest": input_manifest.model_dump(mode="json"),
            "copy_report": copy_report.model_dump(mode="json"),
        }
        package_checksum = _checksum(unsigned)
        return G07ApprovalPackage(
            **{key: value for key, value in unsigned.items() if key != "artifact_payload"},
            package_checksum=package_checksum,
            artifacts=tuple(artifacts),
        )


class G07ApprovalService:
    """Apply the fail-closed G07 decision rules."""

    def decide(
        self,
        package: G07ApprovalPackage,
        decision: G07Decision,
        *,
        comment: str | None = None,
    ) -> G07ApprovalResult:
        if decision in {G07Decision.APPROVED, G07Decision.APPROVED_WITH_COMMENT}:
            if not package.package_checksum:
                return G07ApprovalResult(
                    package_checksum=package.package_checksum,
                    decision=G07Decision.REJECTED,
                    stale=True,
                    reason="package checksum is invalid",
                )
            if decision is G07Decision.APPROVED_WITH_COMMENT and not comment:
                raise ValueError("approved_with_comment requires a non-empty comment")
            return G07ApprovalResult(
                package_checksum=package.package_checksum,
                decision=decision,
                stage_boundary=package.stage_id,
                reason=comment,
            )
        return G07ApprovalResult(
            package_checksum=package.package_checksum,
            decision=decision,
            reason=comment,
        )


class StageWorkspaceService:
    """Deterministic logic for stage workspace operations."""

    def verify_fingerprint(
        self, expected: StageFingerprint, actual: StageFingerprint
    ) -> bool:
        return (
            expected.fingerprint == actual.fingerprint
            and expected.policy_version == actual.policy_version
        )

    def build_sandbox_verification(
        self,
        stage_id: str,
        sandbox_path: str,
        pre_fingerprint: StageFingerprint,
        post_fingerprint: StageFingerprint,
    ) -> StageSandboxVerification:
        verified = self.verify_fingerprint(pre_fingerprint, post_fingerprint)
        payload = {
            "stage_id": stage_id,
            "sandbox_path": sandbox_path,
            "pre_fingerprint": pre_fingerprint.model_dump(mode="json"),
            "post_fingerprint": post_fingerprint.model_dump(mode="json"),
            "verified": verified,
        }
        verification_checksum = _checksum(payload)
        return StageSandboxVerification(
            stage_id=stage_id,
            sandbox_path=sandbox_path,
            pre_fingerprint=pre_fingerprint,
            post_fingerprint=post_fingerprint,
            verification_checksum=verification_checksum,
            verified=verified,
        )


def _artifact_set_checksum(artifacts: list[ArtifactRefDto] | tuple[ArtifactRefDto, ...]) -> str:
    return _checksum(
        [
            {"artifact_id": item.artifact_id, "checksum": item.checksum}
            for item in sorted(artifacts, key=lambda value: value.artifact_id)
        ]
    )


def _checksum(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
