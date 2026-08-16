"""Stage rollback and resume API (V2 F25)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.stage_rollback_contracts import (
    StageResumeDto,
    StageRollbackDecisionDto,
    StageRollbackListDto,
    StageRollbackRecordDto,
)
from app.services.stage_rollback_service import StageRollbackError, StageRollbackService

router = APIRouter(tags=["stage-rollback"])


def get_rollback_service() -> StageRollbackService:
    return StageRollbackService()


def _raise(error: StageRollbackError) -> None:
    raise HTTPException(status_code=404 if error.code in {"RUN_NOT_FOUND", "NO_ROLLBACK_POINT"} else 422,
                        detail={"error_code": error.code, "message": error.message})


def _decision_dto(d) -> StageRollbackDecisionDto:
    return StageRollbackDecisionDto(run_id=d.run_id, rollback_point_stage_order=d.rollback_point_stage_order,
                                    sealed_stage_count=d.sealed_stage_count, evidence_preserved=d.evidence_preserved,
                                    status=d.status, checksum=d.checksum)


def _record_dto(row) -> StageRollbackRecordDto:
    return StageRollbackRecordDto(id=row.id, run_id=row.run_id, rollback_point_stage_order=row.rollback_point_stage_order,
                                  sealed_stage_count=row.sealed_stage_count, evidence_preserved=row.evidence_preserved,
                                  status=row.status, created_at=row.created_at)


@router.post("/runs/{run_id}/rollback", response_model=StageRollbackDecisionDto)
def rollback_run(
    run_id: str,
    service: StageRollbackService = Depends(get_rollback_service),
) -> StageRollbackDecisionDto:
    try:
        decision = service.rollback(run_id)
    except StageRollbackError as error:
        _raise(error)
    return _decision_dto(decision)


@router.post("/runs/{run_id}/resume-from-sealed", response_model=StageResumeDto)
def resume_from_sealed(
    run_id: str,
    service: StageRollbackService = Depends(get_rollback_service),
) -> StageResumeDto:
    try:
        resume = service.resume_from_sealed(run_id)
    except StageRollbackError as error:
        _raise(error)
    return StageResumeDto(**resume)


@router.get("/runs/{run_id}/rollbacks", response_model=StageRollbackListDto)
def list_rollbacks(
    run_id: str,
    service: StageRollbackService = Depends(get_rollback_service),
) -> StageRollbackListDto:
    return StageRollbackListDto(rollbacks=[_record_dto(row) for row in service.list_rollbacks(run_id)])
