"""Bridge runtime certification API (V2 F11)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.runtime_certification_contracts import (
    RuntimeCertificationDto,
    RuntimeCertificationListDto,
    RuntimeCertificationRecordDto,
)
from app.services.runtime_certification_service import RuntimeCertificationError, RuntimeCertificationService

router = APIRouter(tags=["runtime-certification"])


def get_certification_service() -> RuntimeCertificationService:
    return RuntimeCertificationService()


def _raise(error: RuntimeCertificationError) -> None:
    raise HTTPException(status_code=404 if error.code == "CATALOGUE_ENTRY_MISSING" else 409 if error.code == "RUNTIME_NOT_CERTIFIED" else 422,
                        detail={"error_code": error.code, "message": error.message})


def _decision_dto(decision) -> RuntimeCertificationDto:
    return RuntimeCertificationDto(
        run_id=decision.run_id, stage_id=decision.stage_id,
        source_family=decision.source_family, target_family=decision.target_family,
        runtime_id=decision.runtime_id, node_exact=decision.node_exact, npm_exact=decision.npm_exact,
        certified=decision.certified, allowed=decision.allowed, classification=decision.classification, reason=decision.reason,
        certified_against=decision.certified_against, resolved_at=decision.resolved_at,
    )


def _record_dto(row) -> RuntimeCertificationRecordDto:
    return RuntimeCertificationRecordDto(
        id=row.id, run_id=row.run_id, stage_id=row.stage_id,
        source_family=row.source_family, target_family=row.target_family,
        runtime_id=row.runtime_id, node_version=row.node_version, npm_version=row.npm_version,
        node_sha256=row.node_sha256, npm_sha256=row.npm_sha256,
        certified=row.certified, allowed=row.allowed, classification=row.classification, reason=row.reason, certified_against=row.certified_against,
        created_at=row.created_at,
    )


@router.post("/runs/{run_id}/stages/{stage_id}/runtime/certify", response_model=RuntimeCertificationDto)
def certify_stage_runtime(
    run_id: str,
    stage_id: str,
    service: RuntimeCertificationService = Depends(get_certification_service),
) -> RuntimeCertificationDto:
    try:
        decision = service.certify_stage(stage_id)
    except RuntimeCertificationError as error:
        _raise(error)
    return _decision_dto(decision)


@router.post("/runs/{run_id}/stages/{stage_id}/runtime/gate", response_model=RuntimeCertificationDto)
def enforce_stage_certification_gate(
    run_id: str,
    stage_id: str,
    service: RuntimeCertificationService = Depends(get_certification_service),
) -> RuntimeCertificationDto:
    try:
        decision = service.enforce_stage_certification(stage_id)
    except RuntimeCertificationError as error:
        _raise(error)
    return _decision_dto(decision)


@router.get("/runs/{run_id}/stages/{stage_id}/runtime/certifications", response_model=RuntimeCertificationListDto)
def list_stage_certifications(
    run_id: str,
    stage_id: str,
    service: RuntimeCertificationService = Depends(get_certification_service),
) -> RuntimeCertificationListDto:
    return RuntimeCertificationListDto(certifications=[_record_dto(row) for row in service.list_stage_certifications(stage_id)])
