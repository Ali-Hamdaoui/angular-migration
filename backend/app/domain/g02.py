"""Deterministic domain rules for the G02 source-integrity boundary.

This module deliberately has no persistence or filesystem side effects.  The
snapshot application service supplies the already-computed evidence; later
application/database work can persist the resulting package unchanged.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import Field

from app.domain.contracts import ArtifactRefDto, ContractModel


class G02Decision(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_COMMENT = "approved_with_comment"
    MODIFICATION_REQUESTED = "modification_requested"
    REJECTED = "rejected"


class SourceIntegrityStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"


class SourceIntegrityEvidence(ContractModel):
    """The immutable comparison that G02 is allowed to rely on."""

    before_fingerprint: str = Field(min_length=1)
    after_snapshot_fingerprint: str = Field(min_length=1)
    snapshot_fingerprint: str = Field(min_length=1)
    manifest_checksum: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    source_read_only_verified: bool

    @property
    def status(self) -> SourceIntegrityStatus:
        return (
            SourceIntegrityStatus.VERIFIED
            if self.is_verified
            else SourceIntegrityStatus.FAILED
        )

    @property
    def is_verified(self) -> bool:
        return (
            self.source_read_only_verified
            and self.before_fingerprint == self.after_snapshot_fingerprint
        )


class G02ApprovalPackage(ContractModel):
    """Checksum-bound evidence package and its immutable input boundary."""

    run_id: str = Field(min_length=1)
    gate_id: str = "G02"
    gate_version: str = Field(min_length=1)
    state_version: int = Field(ge=1)
    actor: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    source_fingerprint: str = Field(min_length=1)
    snapshot_fingerprint: str = Field(min_length=1)
    artifact_set_checksum: str = Field(min_length=1)
    artifacts: tuple[ArtifactRefDto, ...] = ()
    integrity: SourceIntegrityEvidence
    package_checksum: str = Field(min_length=1)

    @property
    def source_integrity_verified(self) -> bool:
        return self.integrity.is_verified


class G02ApprovalResult(ContractModel):
    package_checksum: str
    decision: G02Decision
    baseline_input_boundary: str | None = None
    stale: bool = False
    reason: str | None = None


class G02ApprovalPackageBuilder:
    """Build a canonical, checksum-bound G02 package from S1-F07 evidence."""

    def build(
        self,
        *,
        run_id: str,
        state_version: int,
        actor: str,
        snapshot_id: str,
        gate_version: str,
        source_fingerprint: str,
        after_source_fingerprint: str | None = None,
        snapshot_fingerprint: str,
        manifest_checksum: str,
        policy_version: str,
        source_read_only_verified: bool,
        artifacts: list[ArtifactRefDto] | tuple[ArtifactRefDto, ...] = (),
    ) -> G02ApprovalPackage:
        integrity = SourceIntegrityEvidence(
            before_fingerprint=source_fingerprint,
            after_snapshot_fingerprint=after_source_fingerprint or source_fingerprint,
            snapshot_fingerprint=snapshot_fingerprint,
            manifest_checksum=manifest_checksum,
            policy_version=policy_version,
            source_read_only_verified=source_read_only_verified,
        )
        unsigned = {
            "run_id": run_id,
            "gate_id": "G02",
            "gate_version": gate_version,
            "state_version": state_version,
            "actor": actor,
            "policy_version": policy_version,
            "snapshot_id": snapshot_id,
            "source_fingerprint": source_fingerprint,
            "snapshot_fingerprint": snapshot_fingerprint,
            "artifact_set_checksum": _artifact_set_checksum(artifacts),
            "artifact_payload": [item.model_dump(mode="json") for item in artifacts],
            "integrity": integrity.model_dump(mode="json"),
        }
        package_checksum = _checksum(unsigned)
        return G02ApprovalPackage(
            **{key: value for key, value in unsigned.items() if key != "artifact_payload"},
            package_checksum=package_checksum,
            artifacts=tuple(artifacts),
        )


class G02ApprovalService:
    """Apply the fail-closed G02 decision rules."""

    def decide(
        self,
        package: G02ApprovalPackage,
        decision: G02Decision,
        *,
        comment: str | None = None,
    ) -> G02ApprovalResult:
        if decision in {G02Decision.APPROVED, G02Decision.APPROVED_WITH_COMMENT}:
            if not package.source_integrity_verified:
                return G02ApprovalResult(
                    package_checksum=package.package_checksum,
                    decision=G02Decision.REJECTED,
                    stale=True,
                    reason="source integrity does not match the approved pre-snapshot boundary",
                )
            if decision is G02Decision.APPROVED_WITH_COMMENT and not comment:
                raise ValueError("approved_with_comment requires a non-empty comment")
            return G02ApprovalResult(
                package_checksum=package.package_checksum,
                decision=decision,
                baseline_input_boundary=package.snapshot_id,
                reason=comment,
            )
        return G02ApprovalResult(
            package_checksum=package.package_checksum,
            decision=decision,
            reason=comment,
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





