"""Deterministic domain rules for the G13 final-assurance boundary.

This module deliberately has no persistence or filesystem side effects.  The
final-assurance application service supplies the already-computed evidence; later
application/database work can persist the resulting package unchanged.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import Field

from app.domain.contracts import ArtifactRefDto, ContractModel


class G13Decision(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_COMMENT = "approved_with_comment"
    MODIFICATION_REQUESTED = "modification_requested"
    REJECTED = "rejected"


class FinalAssuranceSummary(ContractModel):
    """Immutable summary of the final assurance checks for a candidate."""

    run_id: str = Field(min_length=1)
    candidate_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    technical_status: str = Field(min_length=1)
    parity_status: str = Field(min_length=1)
    source_integrity_status: str = Field(min_length=1)
    security_status: str | None = None
    quality_status: str | None = None
    artifact_refs: tuple[ArtifactRefDto, ...] = ()


class G13ApprovalPackage(ContractModel):
    """Checksum-bound final-assurance approval package."""

    run_id: str = Field(min_length=1)
    gate_id: str = "G13"
    gate_version: str = Field(min_length=1)
    state_version: int = Field(ge=1)
    actor: str = Field(min_length=1)
    summary: FinalAssuranceSummary
    artifact_set_checksum: str = Field(min_length=1)
    artifacts: tuple[ArtifactRefDto, ...] = ()
    package_checksum: str = Field(min_length=1)


class G13ApprovalResult(ContractModel):
    package_checksum: str
    decision: G13Decision
    stale: bool = False
    reason: str | None = None


class G13ApprovalPackageBuilder:
    """Build a canonical, checksum-bound G13 package."""

    def build(
        self,
        *,
        run_id: str,
        state_version: int,
        actor: str,
        gate_version: str,
        summary: FinalAssuranceSummary,
        artifacts: list[ArtifactRefDto] | tuple[ArtifactRefDto, ...] = (),
    ) -> G13ApprovalPackage:
        unsigned = {
            "run_id": run_id,
            "gate_id": "G13",
            "gate_version": gate_version,
            "state_version": state_version,
            "actor": actor,
            "summary": summary.model_dump(mode="json"),
            "artifact_set_checksum": _artifact_set_checksum(artifacts),
            "artifact_payload": [item.model_dump(mode="json") for item in artifacts],
        }
        payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), default=str)
        package_checksum = "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return G13ApprovalPackage(
            **{k: v for k, v in unsigned.items() if k != "artifact_payload"},
            package_checksum=package_checksum,
            artifacts=tuple(artifacts),
        )


class G13ApprovalService:
    """Fail-closed G13 decision rules."""

    def decide(
        self,
        package: G13ApprovalPackage,
        decision: G13Decision,
        *,
        comment: str | None = None,
    ) -> G13ApprovalResult:
        if decision in {G13Decision.APPROVED, G13Decision.APPROVED_WITH_COMMENT}:
            if decision is G13Decision.APPROVED_WITH_COMMENT and not comment:
                raise ValueError("approved_with_comment requires a non-empty comment")
            return G13ApprovalResult(
                package_checksum=package.package_checksum,
                decision=decision,
                reason=comment,
            )
        return G13ApprovalResult(
            package_checksum=package.package_checksum,
            decision=decision,
            reason=comment,
        )


def _artifact_set_checksum(artifacts: list[ArtifactRefDto] | tuple[ArtifactRefDto, ...]) -> str:
    items = [
        {"artifact_id": a.artifact_id, "checksum": a.checksum}
        for a in sorted(artifacts, key=lambda x: x.artifact_id)
    ]
    payload = json.dumps(items, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
