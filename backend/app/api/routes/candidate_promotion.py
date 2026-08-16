"""Candidate workspace promotion API (V2 F22)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.candidate_promotion_contracts import (
    CandidatePathRequest,
    CandidatePromotionDecisionDto,
    CandidatePromotionListDto,
    CandidatePromotionRecordDto,
)
from app.services.candidate_promotion_service import CandidatePromotionError, CandidatePromotionService

router = APIRouter(tags=["candidate-promotion"])


def get_promotion_service() -> CandidatePromotionService:
    return CandidatePromotionService()


def _raise(error: CandidatePromotionError) -> None:
    raise HTTPException(status_code=404 if error.code == "STAGE_NOT_FOUND" else 422,
                        detail={"error_code": error.code, "message": error.message})


def _decision_dto(d) -> CandidatePromotionDecisionDto:
    return CandidatePromotionDecisionDto(
        run_id=d.run_id, stage_id=d.stage_id, alias=d.alias, candidate_fingerprint=d.candidate_fingerprint,
        generation=d.generation, status=d.status, validated=d.validated, blockers=list(d.blockers),
        previous_generation=d.previous_generation, checksum=d.checksum,
    )


def _record_dto(row) -> CandidatePromotionRecordDto:
    return CandidatePromotionRecordDto(
        id=row.id, run_id=row.run_id, stage_id=row.stage_id, alias=row.alias,
        candidate_fingerprint=row.candidate_fingerprint, generation=row.generation, status=row.status,
        validated=row.validated, blockers=row.blockers, previous_generation=row.previous_generation,
        checksum=row.checksum, created_at=row.created_at,
    )


@router.post("/runs/{run_id}/stages/{stage_id}/candidate/validate", response_model=CandidatePromotionDecisionDto)
def validate_candidate(
    run_id: str,
    stage_id: str,
    request: CandidatePathRequest,
    service: CandidatePromotionService = Depends(get_promotion_service),
) -> CandidatePromotionDecisionDto:
    try:
        decision = service.validate_candidate(Path(request.candidate_path), run_id=run_id, stage_id=stage_id)
    except CandidatePromotionError as error:
        _raise(error)
    return _decision_dto(decision)


@router.post("/runs/{run_id}/stages/{stage_id}/candidate/promote", response_model=CandidatePromotionDecisionDto)
def promote_candidate(
    run_id: str,
    stage_id: str,
    request: CandidatePathRequest,
    service: CandidatePromotionService = Depends(get_promotion_service),
) -> CandidatePromotionDecisionDto:
    try:
        decision = service.promote_candidate(run_id=run_id, stage_id=stage_id, candidate_path=Path(request.candidate_path))
    except CandidatePromotionError as error:
        _raise(error)
    return _decision_dto(decision)


@router.post("/runs/{run_id}/stages/{stage_id}/candidate/rollback-safety", response_model=CandidatePromotionDecisionDto)
def rollback_safety(
    run_id: str,
    stage_id: str,
    service: CandidatePromotionService = Depends(get_promotion_service),
) -> CandidatePromotionDecisionDto:
    decision = service.rollback_safety(run_id=run_id, stage_id=stage_id)
    return _decision_dto(decision)


@router.get("/runs/{run_id}/stages/{stage_id}/candidate/promotions", response_model=CandidatePromotionListDto)
def list_stage_promotions(
    run_id: str,
    stage_id: str,
    service: CandidatePromotionService = Depends(get_promotion_service),
) -> CandidatePromotionListDto:
    return CandidatePromotionListDto(promotions=[_record_dto(row) for row in service.list_stage_promotions(stage_id)])
