"""Preflight check API (V2 F16)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.preflight_check_contracts import (
    PreflightCheckResultDto,
    PreflightVerdictDto,
    PreflightVerdictRecordDto,
    RunPreflightRequest,
)
from app.services.preflight_check_service import PreflightCheckError, PreflightCheckService

router = APIRouter(tags=["preflight-checks"])


def get_preflight_service() -> PreflightCheckService:
    return PreflightCheckService()


def _raise(error: PreflightCheckError) -> None:
    raise HTTPException(status_code=404 if error.code in {"RUN_NOT_FOUND", "PREFLIGHT_REQUIRED"} else 409 if error.code == "PREFLIGHT_BLOCKED" else 422,
                        detail={"error_code": error.code, "message": error.message})


def _check_dto(check) -> PreflightCheckResultDto:
    return PreflightCheckResultDto(check_id=check["check_id"] if isinstance(check, dict) else check.check_id,
                                   name=check["name"] if isinstance(check, dict) else check.name,
                                   passed=check["passed"] if isinstance(check, dict) else check.passed,
                                   blockers=check["blockers"] if isinstance(check, dict) else list(check.blockers),
                                   detail=check.get("detail", "") if isinstance(check, dict) else check.detail)


def _verdict_dto(verdict) -> PreflightVerdictDto:
    return PreflightVerdictDto(run_id=verdict.run_id, status=verdict.status,
                               checks=[_check_dto(c) for c in verdict.checks],
                               blockers=list(verdict.blockers), checksum=verdict.checksum)


def _record_dto(row) -> PreflightVerdictRecordDto:
    return PreflightVerdictRecordDto(id=row.id, run_id=row.run_id, status=row.status,
                                     blockers=row.blockers, checks=row.checks,
                                     checksum=row.checksum, created_at=row.created_at)


@router.post("/runs/{run_id}/preflight/run", response_model=PreflightVerdictDto)
def run_preflight_checks(
    run_id: str,
    request: RunPreflightRequest,
    service: PreflightCheckService = Depends(get_preflight_service),
) -> PreflightVerdictDto:
    try:
        verdict = service.run_checks(run_id, Path(request.source_root))
    except PreflightCheckError as error:
        _raise(error)
    return _verdict_dto(verdict)


@router.post("/runs/{run_id}/preflight/persist", response_model=PreflightVerdictRecordDto)
def persist_preflight_verdict(
    run_id: str,
    request: RunPreflightRequest,
    service: PreflightCheckService = Depends(get_preflight_service),
) -> PreflightVerdictRecordDto:
    try:
        verdict = service.run_checks(run_id, Path(request.source_root))
        row = service.persist(run_id, verdict)
    except PreflightCheckError as error:
        _raise(error)
    return _record_dto(row)


@router.get("/runs/{run_id}/preflight", response_model=PreflightVerdictRecordDto)
def get_run_preflight_verdict(
    run_id: str,
    service: PreflightCheckService = Depends(get_preflight_service),
) -> PreflightVerdictRecordDto:
    row = service.get_run_verdict(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error_code": "PREFLIGHT_REQUIRED", "message": "No preflight verdict for run."})
    return _record_dto(row)


@router.post("/runs/{run_id}/preflight/gate", response_model=PreflightVerdictRecordDto)
def gate_run_start(
    run_id: str,
    service: PreflightCheckService = Depends(get_preflight_service),
) -> PreflightVerdictRecordDto:
    try:
        row = service.gate_run_start(run_id)
    except PreflightCheckError as error:
        _raise(error)
    return _record_dto(row)
