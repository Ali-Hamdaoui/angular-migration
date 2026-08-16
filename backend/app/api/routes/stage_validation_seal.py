"""Stage validation and sealing API (V2 F24)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.stage_validation_contracts import (
    StageSealDto,
    StageSealListDto,
    StageSealRecordDto,
    StageValidationResultDto,
    ValidateStageRequest,
)
from app.services.stage_validation_seal_service import StageValidationError, StageValidationSealService

router = APIRouter(tags=["stage-validation-sealing"])


def get_seal_service() -> StageValidationSealService:
    return StageValidationSealService()


def _raise(error: StageValidationError) -> None:
    raise HTTPException(status_code=404 if error.code == "STAGE_NOT_FOUND" else 409 if error.code in {"STAGE_ALREADY_SEALED", "STAGE_NOT_VALIDATED"} else 422,
                        detail={"error_code": error.code, "message": error.message})


def _validation_dto(result) -> StageValidationResultDto:
    return StageValidationResultDto(stage_id=result.stage_id, checks=list(result.checks), passed=result.passed,
                                    blockers=list(result.blockers), workspace_fingerprint=result.workspace_fingerprint,
                                    checksum=result.checksum)


def _seal_dto(seal) -> StageSealDto:
    return StageSealDto(stage_id=seal.stage_id, source_major=seal.source_major, target_major=seal.target_major,
                        validation_checksum=seal.validation_checksum, workspace_fingerprint=seal.workspace_fingerprint,
                        sealed_at=seal.sealed_at, checksum=seal.checksum)


def _seal_record_dto(row) -> StageSealRecordDto:
    return StageSealRecordDto(id=row.id, stage_id=row.stage_id, run_id=row.run_id,
                              source_major=row.source_major, target_major=row.target_major,
                              validation_checksum=row.validation_checksum, workspace_fingerprint=row.workspace_fingerprint,
                              sealed_at=row.sealed_at, checksum=row.checksum, created_at=row.created_at)


@router.post("/runs/{run_id}/stages/{stage_id}/validate", response_model=StageValidationResultDto)
def validate_stage(
    run_id: str,
    stage_id: str,
    request: ValidateStageRequest,
    service: StageValidationSealService = Depends(get_seal_service),
) -> StageValidationResultDto:
    try:
        result = service.validate_stage(stage_id, Path(request.workspace_path))
    except StageValidationError as error:
        _raise(error)
    return _validation_dto(result)


@router.post("/runs/{run_id}/stages/{stage_id}/seal", response_model=StageSealDto)
def seal_stage(
    run_id: str,
    stage_id: str,
    request: ValidateStageRequest,
    service: StageValidationSealService = Depends(get_seal_service),
) -> StageSealDto:
    try:
        seal = service.seal_stage(stage_id, Path(request.workspace_path), run_id=run_id)
    except StageValidationError as error:
        _raise(error)
    return _seal_dto(seal)


@router.get("/runs/{run_id}/stages/{stage_id}/seal", response_model=StageSealRecordDto)
def get_stage_seal(
    run_id: str,
    stage_id: str,
    service: StageValidationSealService = Depends(get_seal_service),
) -> StageSealRecordDto:
    seal = service.is_sealed(stage_id)
    if seal is None:
        raise HTTPException(status_code=404, detail={"error_code": "STAGE_NOT_SEALED", "message": "Stage is not sealed."})
    return _seal_record_dto(seal)


@router.get("/runs/{run_id}/seals", response_model=StageSealListDto)
def list_run_seals(
    run_id: str,
    service: StageValidationSealService = Depends(get_seal_service),
) -> StageSealListDto:
    return StageSealListDto(seals=[_seal_record_dto(row) for row in service.list_stage_seals(run_id)])
