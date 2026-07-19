"""Deterministic domain rules for the G15 report approval boundary.

This module deliberately has no persistence or filesystem side effects.  The
report application service supplies the already-computed evidence; later
application/database work can persist the resulting package unchanged.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import Field

from app.domain.contracts import ArtifactRefDto, ContractModel


class G15Decision(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_COMMENT = "approved_with_comment"
    MODIFICATION_REQUESTED = "modification_requested"
    REJECTED = "rejected"


class FinalReportRecord(ContractModel):
    """Deterministic immutable report truth for the G15 gate."""

    report_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    deterministic_report_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    narrative_status: str = Field(default="not_requested")
    proof_labels: dict[str, str] = Field(default_factory=dict)
    artifact_refs: tuple[ArtifactRefDto, ...] = ()


class G15ApprovalPackage(ContractModel):
    """Checksum-bound report approval package and its immutable input boundary."""

    run_id: str = Field(min_length=1)
    gate_id: str = "G15"
    gate_version: str = Field(min_length=1)
    state_version: int = Field(ge=1)
    actor: str = Field(min_length=1)
    report: FinalReportRecord
    artifact_set_checksum: str = Field(min_length=1)
    artifacts: tuple[ArtifactRefDto, ...] = ()
    package_checksum: str = Field(min_length=1)


class G15ApprovalResult(ContractModel):
    package_checksum: str
    decision: G15Decision
    stale: bool = False
    reason: str | None = None


class G15ApprovalPackageBuilder:
    """Build a canonical, checksum-bound G15 package from report evidence."""

    def build(
        self,
        *,
        run_id: str,
        state_version: int,
        actor: str,
        gate_version: str,
        report: FinalReportRecord,
        artifacts: list[ArtifactRefDto] | tuple[ArtifactRefDto, ...] = (),
    ) -> G15ApprovalPackage:
        unsigned = {
            "run_id": run_id,
            "gate_id": "G15",
            "gate_version": gate_version,
            "state_version": state_version,
            "actor": actor,
            "report": report.model_dump(mode="json"),
            "artifact_set_checksum": _artifact_set_checksum(artifacts),
            "artifact_payload": [item.model_dump(mode="json") for item in artifacts],
        }
        payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), default=str)
        package_checksum = "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return G15ApprovalPackage(
            **{k: v for k, v in unsigned.items() if k != "artifact_payload"},
            package_checksum=package_checksum,
            artifacts=tuple(artifacts),
        )


class G15ApprovalService:
    """Apply the G15 decision rules."""

    def decide(
        self,
        package: G15ApprovalPackage,
        decision: G15Decision,
        *,
        comment: str | None = None,
    ) -> G15ApprovalResult:
        if decision in {G15Decision.APPROVED, G15Decision.APPROVED_WITH_COMMENT}:
            if decision is G15Decision.APPROVED_WITH_COMMENT and not comment:
                raise ValueError("approved_with_comment requires a non-empty comment")
            return G15ApprovalResult(
                package_checksum=package.package_checksum,
                decision=decision,
                reason=comment,
            )
        return G15ApprovalResult(
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
