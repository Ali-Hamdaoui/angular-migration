"""Deterministic domain rules for the G14 Delivery gate.

This module deliberately has no persistence or filesystem side effects.  The
delivery application service supplies the already-computed candidate; later
application/database work can persist the resulting package unchanged.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import Field

from app.domain.contracts import ArtifactRefDto, ContractModel


class G14Decision(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_COMMENT = "approved_with_comment"
    MODIFICATION_REQUESTED = "modification_requested"
    REJECTED = "rejected"


class DeliveryCandidate(ContractModel):
    """The immutable delivery candidate that G14 is asked to approve."""

    delivery_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    candidate_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    destination: str = Field(min_length=1)
    publication_status: str = Field(min_length=1)
    artifact_refs: tuple[ArtifactRefDto, ...] = ()


class G14ApprovalPackage(ContractModel):
    """Checksum-bound delivery package and its immutable input boundary."""

    run_id: str = Field(min_length=1)
    gate_id: str = "G14"
    gate_version: str = Field(min_length=1)
    state_version: int = Field(ge=1)
    actor: str = Field(min_length=1)
    candidate: DeliveryCandidate
    artifact_set_checksum: str = Field(min_length=1)
    artifacts: tuple[ArtifactRefDto, ...] = ()
    package_checksum: str = Field(min_length=1)


class G14ApprovalResult(ContractModel):
    package_checksum: str
    decision: G14Decision
    stale: bool = False
    reason: str | None = None


class G14ApprovalPackageBuilder:
    """Build a canonical, checksum-bound G14 package from delivery evidence."""

    def build(
        self,
        *,
        run_id: str,
        state_version: int,
        actor: str,
        gate_version: str,
        candidate: DeliveryCandidate,
        artifacts: tuple[ArtifactRefDto, ...] = (),
    ) -> G14ApprovalPackage:
        unsigned = {
            "run_id": run_id,
            "gate_id": "G14",
            "gate_version": gate_version,
            "state_version": state_version,
            "actor": actor,
            "candidate": candidate.model_dump(mode="json"),
            "artifact_set_checksum": _artifact_set_checksum(artifacts),
            "artifact_payload": [a.model_dump(mode="json") for a in artifacts],
        }
        payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), default=str)
        package_checksum = "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return G14ApprovalPackage(
            **{k: v for k, v in unsigned.items() if k != "artifact_payload"},
            package_checksum=package_checksum,
            artifacts=tuple(artifacts),
        )


class G14ApprovalService:
    """Apply the fail-closed G14 decision rules."""

    def decide(
        self,
        package: G14ApprovalPackage,
        decision: G14Decision,
        *,
        comment: str | None = None,
    ) -> G14ApprovalResult:
        if decision in {G14Decision.APPROVED, G14Decision.APPROVED_WITH_COMMENT}:
            if decision is G14Decision.APPROVED_WITH_COMMENT and not comment:
                raise ValueError("approved_with_comment requires a non-empty comment")
            return G14ApprovalResult(
                package_checksum=package.package_checksum,
                decision=decision,
                reason=comment,
            )
        return G14ApprovalResult(
            package_checksum=package.package_checksum,
            decision=decision,
            reason=comment,
        )


def _artifact_set_checksum(artifacts: tuple[ArtifactRefDto, ...]) -> str:
    items = [
        {"artifact_id": a.artifact_id, "checksum": a.checksum}
        for a in sorted(artifacts, key=lambda x: x.artifact_id)
    ]
    payload = json.dumps(items, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
