"""Repair proposal and G10 gate decision endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.repair_proposal_contracts import (
    G10DecisionRequestDto,
    G10DecisionResponseDto,
    RepairProposalDto,
)
from app.domain.repair_proposal import (
    G10Decision,
    G10DecisionRequest,
    G10Status,
    ProposalStatus,
)
from app.services.repair_proposal_application_service import (
    G10DecisionService,
    RepairProposalApplicationError,
    RepairProposalService,
)

router = APIRouter(prefix="/runs", tags=["repair-proposals"])


def get_repair_proposal_service() -> RepairProposalService:
    return RepairProposalService()


def get_g10_service() -> G10DecisionService:
    return G10DecisionService()


@router.get("/{run_id}/repair-proposals/{proposal_id}", response_model=RepairProposalDto)
def read_repair_proposal(
    run_id: str,
    proposal_id: str,
    service: RepairProposalService = Depends(get_repair_proposal_service),
) -> RepairProposalDto:
    """Retrieve a repair proposal by run and proposal ID."""
    record = service.get(run_id, proposal_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Repair proposal not found")
    return RepairProposalDto(
        proposal_id=record.proposal_id,
        failure_id="",
        context_pack_id="",
        proposer_invocation_id="",
        status=ProposalStatus(record.status),
        diff_checksum=record.diff_checksum,
        changed_files=[],
        workspace_fingerprint=record.workspace_fingerprint,
        g10_status=G10Status(record.g10_status),
        g10_decision=record.g10_decision,
        g10_approval_id=record.g10_approval_id,
        state_version=record.state_version,
        event_sequence=record.event_sequence,
    )


@router.post("/{run_id}/approvals/G10/decisions", response_model=G10DecisionResponseDto)
def decide_g10(
    run_id: str,
    request: G10DecisionRequestDto,
    service: G10DecisionService = Depends(get_g10_service),
) -> G10DecisionResponseDto:
    """Submit a human decision on the G10 gate for a repair proposal."""
    try:
        domain_request = G10DecisionRequest(
            proposal_id=request.proposal_id,
            expected_state_version=request.expected_state_version,
            gate_version="g10-v1",
            decision=request.decision,
            actor=request.actor,
            rationale=request.rationale,
            idempotency_key=request.idempotency_key,
            workspace_fingerprint=request.workspace_fingerprint,
            diff_checksum=request.diff_checksum,
            lineage_checksum=request.lineage_checksum,
        )
        result = service.decide(run_id, domain_request)
        return G10DecisionResponseDto(
            run_id=run_id,
            proposal_id=result.proposal_id,
            decision=result.decision,
            accepted=result.accepted,
            state_version=result.state_version,
            event_sequence=result.state_version,
            stale=result.stale,
            reason=result.reason,
        )
    except RepairProposalApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error
