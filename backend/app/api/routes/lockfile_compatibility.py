"""Lockfile compatibility API (V2 F08)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.lockfile_contracts import (
    LockfileCompatibilityVerdictDto,
    LockfileEvidenceDto,
    LockfileEvidenceListDto,
    LockfileFindingDto,
    LockfileValidationRequest,
)
from app.services.lockfile_compatibility_service import LockfileCompatibilityError, LockfileCompatibilityService

router = APIRouter(tags=["lockfile-compatibility"])


def get_lockfile_service() -> LockfileCompatibilityService:
    return LockfileCompatibilityService()


def _raise(error: LockfileCompatibilityError) -> None:
    raise HTTPException(status_code=404 if error.code in {"RUN_NOT_FOUND", "STAGE_NOT_FOUND", "CATALOGUE_ENTRY_MISSING"} else 422,
                        detail={"error_code": error.code, "message": error.message})


def _verdict_dto(verdict) -> LockfileCompatibilityVerdictDto:
    return LockfileCompatibilityVerdictDto(
        source_family=verdict.source_family,
        target_family=verdict.target_family,
        status=verdict.status,
        findings=[LockfileFindingDto(package=f.package, expected=f.expected, resolved=f.resolved, status=f.status, detail=f.detail) for f in verdict.findings],
        blockers=list(verdict.blockers),
    )


def _evidence_dto(row) -> LockfileEvidenceDto:
    return LockfileEvidenceDto(
        id=row.id, run_id=row.run_id, stage_id=row.stage_id, execution_id=row.execution_id,
        lockfile_checksum=row.lockfile_checksum, lockfile_version=row.lockfile_version,
        source_family=row.source_family, target_family=row.target_family,
        node_version=row.node_version, npm_version=row.npm_version,
        node_sha256=row.node_sha256, npm_sha256=row.npm_sha256,
        validation_status=row.validation_status, blockers=row.blockers,
        findings=row.findings, deterministic=row.deterministic, created_at=row.created_at,
    )


@router.post("/lockfile/validate", response_model=LockfileCompatibilityVerdictDto)
def validate_lockfile(
    request: LockfileValidationRequest,
    service: LockfileCompatibilityService = Depends(get_lockfile_service),
) -> LockfileCompatibilityVerdictDto:
    try:
        verdict = service.validate_stage_lockfile(
            Path(request.workspace_path), request.source_family, request.target_family, request.catalogue_version
        )
    except LockfileCompatibilityError as error:
        _raise(error)
    return _verdict_dto(verdict)


@router.post("/runs/{run_id}/stages/{stage_id}/lockfile/evidence", response_model=LockfileEvidenceDto)
def record_lockfile_evidence(
    run_id: str,
    stage_id: str,
    request: LockfileValidationRequest,
    service: LockfileCompatibilityService = Depends(get_lockfile_service),
) -> LockfileEvidenceDto:
    try:
        verdict = service.validate_stage_lockfile(
            Path(request.workspace_path), request.source_family, request.target_family, request.catalogue_version
        )
        row = service.record_evidence(
            run_id=run_id, stage_id=stage_id, workspace=Path(request.workspace_path), verdict=verdict,
        )
    except LockfileCompatibilityError as error:
        _raise(error)
    return _evidence_dto(row)


@router.get("/runs/{run_id}/stages/{stage_id}/lockfile/evidence", response_model=LockfileEvidenceListDto)
def list_lockfile_evidence(
    run_id: str,
    stage_id: str,
    service: LockfileCompatibilityService = Depends(get_lockfile_service),
) -> LockfileEvidenceListDto:
    return LockfileEvidenceListDto(evidence=[_evidence_dto(row) for row in service.list_stage_evidence(run_id, stage_id)])
