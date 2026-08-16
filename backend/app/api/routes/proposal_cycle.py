"""Governed repair proposal-cycle API (V2 F21)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.proposal_cycle_contracts import (
    CreateCycleRequest,
    DecideCycleRequest,
    ProposalCycleDto,
    ProposalCycleListDto,
    ProposalCycleRecordDto,
)
from app.services.proposal_cycle_service import ProposalCycleError, ProposalCycleService

router = APIRouter(tags=["proposal-cycle"])


def get_cycle_service() -> ProposalCycleService:
    return ProposalCycleService()


def _raise(error: ProposalCycleError) -> None:
    raise HTTPException(status_code=404 if error.code in {"RUN_NOT_FOUND", "ATTEMPT_NOT_FOUND", "CYCLE_NOT_FOUND"} else 409 if error.code == "CYCLE_ALREADY_DECIDED" else 422,
                        detail={"error_code": error.code, "message": error.message})


def _cycle_dto(cycle) -> ProposalCycleDto:
    return ProposalCycleDto(cycle_id=cycle.cycle_id, run_id=cycle.run_id, attempt_id=cycle.attempt_id,
                            cycle_number=cycle.cycle_number, proposal_checksum=cycle.proposal_checksum,
                            decision=cycle.decision, reviewer=cycle.reviewer, hints=list(cycle.hints),
                            parent_cycle_id=cycle.parent_cycle_id, checksum=cycle.checksum)


def _record_dto(row) -> ProposalCycleRecordDto:
    return ProposalCycleRecordDto(id=row.id, run_id=row.run_id, attempt_id=row.attempt_id,
                                  cycle_number=row.cycle_number, proposal_checksum=row.proposal_checksum,
                                  decision=row.decision, reviewer=row.reviewer, hints=row.hints,
                                  parent_cycle_id=row.parent_cycle_id, checksum=row.checksum,
                                  created_at=row.created_at)


@router.post("/runs/{run_id}/attempts/{attempt_id}/cycles", response_model=ProposalCycleDto)
def create_proposal_cycle(
    run_id: str,
    attempt_id: str,
    request: CreateCycleRequest,
    service: ProposalCycleService = Depends(get_cycle_service),
) -> ProposalCycleDto:
    try:
        cycle = service.create_cycle(run_id, attempt_id, request.proposal_checksum)
    except ProposalCycleError as error:
        _raise(error)
    return _cycle_dto(cycle)


@router.post("/cycles/{cycle_id}/decide", response_model=ProposalCycleDto)
def decide_proposal_cycle(
    cycle_id: str,
    request: DecideCycleRequest,
    service: ProposalCycleService = Depends(get_cycle_service),
) -> ProposalCycleDto:
    try:
        cycle = service.decide(cycle_id, request.decision, reviewer=request.reviewer, hints=request.hints)
    except ProposalCycleError as error:
        _raise(error)
    return _cycle_dto(cycle)


@router.get("/attempts/{attempt_id}/cycles", response_model=ProposalCycleListDto)
def list_cycle_lineage(
    attempt_id: str,
    service: ProposalCycleService = Depends(get_cycle_service),
) -> ProposalCycleListDto:
    cycles = service.list_lineage(attempt_id)
    return ProposalCycleListDto(cycles=[_record_dto_from_cycle(cycle) for cycle in cycles])


def _record_dto_from_cycle(cycle) -> ProposalCycleRecordDto:
    return ProposalCycleRecordDto(id=cycle.cycle_id, run_id=cycle.run_id, attempt_id=cycle.attempt_id,
                                  cycle_number=cycle.cycle_number, proposal_checksum=cycle.proposal_checksum,
                                  decision=cycle.decision, reviewer=cycle.reviewer, hints=list(cycle.hints),
                                  parent_cycle_id=cycle.parent_cycle_id, checksum=cycle.checksum,
                                  created_at=cycle.created_at if hasattr(cycle, "created_at") else None)
