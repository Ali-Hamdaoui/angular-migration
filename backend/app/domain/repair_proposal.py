"""Deterministic domain rules for repair proposals and the G10 human-apply gate.

This module has no persistence or filesystem side effects.  The application
service supplies the already-computed proposal evidence; later
application/database work can persist the resulting models unchanged.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import Field

from app.domain.contracts import ArtifactRefDto, ContractModel


_CHECKSUM = r"^sha256:[0-9a-f]{64}$"


class G10Decision(str, Enum):
    """Human decision for the G10 gate (apply/reject)."""

    APPROVE = "approve"
    APPROVE_WITH_COMMENT = "approve_with_comment"
    REJECT = "reject"
    MODIFICATION_REQUESTED = "modification_requested"


class G10Status(str, Enum):
    """Lifecycle status of a G10 gate bound to a repair proposal."""

    PENDING = "pending"
    APPROVED = "approved"
    APPROVED_WITH_COMMENT = "approved_with_comment"
    MODIFICATION_REQUESTED = "modification_requested"
    REJECTED = "rejected"
    STALE = "stale"


class ProposalStatus(str, Enum):
    """Status of a repair proposal per repair_proposal.schema.json."""

    CANDIDATE = "candidate"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    NOT_REPAIRABLE = "not_repairable"


class RepairProposal(ContractModel):
    """Immutable repair proposal authored by the Repair Proposer.

    Matches repair_proposal.schema.json.  Once persisted the content is
    never mutated — a revision produces a new proposal_id.
    """

    proposal_id: str = Field(min_length=1)
    failure_id: str = Field(min_length=1)
    context_pack_id: str = Field(min_length=1)
    proposer_invocation_id: str = Field(min_length=1)
    status: ProposalStatus
    summary: str | None = Field(default=None, min_length=1)
    root_cause: str | None = Field(default=None, min_length=1)
    fix_strategy: str | None = Field(default=None, min_length=1)
    diff_checksum: str = Field(pattern=_CHECKSUM)
    diff_artifact: ArtifactRefDto | None = None
    changed_files: tuple[str, ...] = Field(min_length=1)
    workspace_fingerprint: str = Field(pattern=_CHECKSUM)
    risk_notes: tuple[str, ...] = ()


class G10ApprovalPackage(ContractModel):
    """Checksum-bound G10 gate package matching repair_g10_package.schema.json.

    Created when a reviewed proposal is ready for human apply/reject.
    """

    proposal_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    lineage_checksum: str = Field(pattern=_CHECKSUM)
    diff_checksum: str = Field(pattern=_CHECKSUM)
    workspace_fingerprint: str = Field(pattern=_CHECKSUM)
    g10_status: G10Status = G10Status.PENDING
    approval_id: str | None = None
    artifact_refs: tuple[ArtifactRefDto, ...] = ()


class G10DecisionRequest(ContractModel):
    """Input contract for submitting a G10 human decision."""

    proposal_id: str = Field(min_length=1)
    expected_state_version: int = Field(ge=1)
    gate_version: str = Field(min_length=1)
    decision: G10Decision
    actor: str = Field(min_length=1, max_length=128)
    rationale: str | None = Field(default=None, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=128)
    workspace_fingerprint: str = Field(pattern=_CHECKSUM)
    diff_checksum: str = Field(pattern=_CHECKSUM)
    lineage_checksum: str = Field(pattern=_CHECKSUM)


class G10DecisionResult(ContractModel):
    """Output contract produced by the G10 decision service."""

    run_id: str = ""
    proposal_id: str = Field(min_length=1)
    decision: G10Decision
    accepted: bool
    state_version: int = Field(ge=1)
    gate_version: str = Field(min_length=1)
    stale: bool = False
    reason: str | None = None


class G10ApprovalService:
    """Apply the fail-closed G10 decision rules (pure domain logic)."""

    def decide(
        self,
        package: G10ApprovalPackage,
        request: G10DecisionRequest,
        *,
        state_version: int,
    ) -> G10DecisionResult:
        """Evaluate whether the G10 gate can accept the given decision.

        Returns a result that the application service uses to persist
        the decision outcome.
        """
        if request.decision is G10Decision.APPROVE or request.decision is G10Decision.APPROVE_WITH_COMMENT:
            # Validate the decision is bound to the exact package diff/fingerprint.
            if request.diff_checksum != package.diff_checksum:
                return G10DecisionResult(
                    proposal_id=request.proposal_id,
                    decision=G10Decision.REJECT,
                    accepted=False,
                    state_version=state_version,
                    gate_version=request.gate_version,
                    stale=True,
                    reason="diff_checksum does not match the persisted proposal",
                )
            if request.workspace_fingerprint != package.workspace_fingerprint:
                return G10DecisionResult(
                    proposal_id=request.proposal_id,
                    decision=G10Decision.REJECT,
                    accepted=False,
                    state_version=state_version,
                    gate_version=request.gate_version,
                    stale=True,
                    reason="workspace_fingerprint does not match the persisted package",
                )
            if request.lineage_checksum != package.lineage_checksum:
                return G10DecisionResult(
                    proposal_id=request.proposal_id,
                    decision=G10Decision.REJECT,
                    accepted=False,
                    state_version=state_version,
                    gate_version=request.gate_version,
                    stale=True,
                    reason="lineage_checksum does not match the persisted package",
                )
            if request.decision is G10Decision.APPROVE_WITH_COMMENT and not request.rationale:
                raise ValueError("approve_with_comment requires a non-empty rationale")
            return G10DecisionResult(
                proposal_id=request.proposal_id,
                decision=request.decision,
                accepted=True,
                state_version=state_version,
                gate_version=request.gate_version,
                reason=request.rationale,
            )
        return G10DecisionResult(
            proposal_id=request.proposal_id,
            decision=request.decision,
            accepted=False,
            state_version=state_version,
            gate_version=request.gate_version,
            reason=request.rationale,
        )


class G10ApprovalPackageBuilder:
    """Build a canonical, checksum-bound G10 package from accepted proposal evidence."""

    def build(
        self,
        *,
        proposal_id: str,
        review_id: str,
        lineage_checksum: str,
        diff_checksum: str,
        workspace_fingerprint: str,
        artifact_refs: list[ArtifactRefDto] | tuple[ArtifactRefDto, ...] = (),
    ) -> G10ApprovalPackage:
        unsigned = {
            "proposal_id": proposal_id,
            "review_id": review_id,
            "lineage_checksum": lineage_checksum,
            "diff_checksum": diff_checksum,
            "workspace_fingerprint": workspace_fingerprint,
            "g10_status": G10Status.PENDING.value,
            "artifact_refs": [item.model_dump(mode="json") for item in artifact_refs],
        }
        package_checksum = _checksum(unsigned)
        return G10ApprovalPackage(
            proposal_id=proposal_id,
            review_id=review_id,
            lineage_checksum=lineage_checksum,
            diff_checksum=diff_checksum,
            workspace_fingerprint=workspace_fingerprint,
            g10_status=G10Status.PENDING,
            approval_id=package_checksum,
            artifact_refs=tuple(artifact_refs),
        )


def _checksum(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
