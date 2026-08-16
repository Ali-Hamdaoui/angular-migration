"""Immutable execution audit trail API (V2 F27-03)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.execution_audit_contracts import (
    ExecutionAuditEntryDto,
    ExecutionAuditListDto,
    ExecutionAuditVerificationDto,
)
from app.services.execution_audit_service import ExecutionAuditError, ExecutionAuditTrailService

router = APIRouter(tags=["execution-audit"])


def get_audit_service() -> ExecutionAuditTrailService:
    return ExecutionAuditTrailService()


def _entry_dto(row) -> ExecutionAuditEntryDto:
    return ExecutionAuditEntryDto(
        id=row.id, run_id=row.run_id, stage_id=row.stage_id, execution_id=row.execution_id,
        command_id=row.command_id, command_class=row.command_class, event=row.event, actor=row.actor,
        executable=row.executable, arguments=row.arguments, policy_version=row.policy_version,
        state_version=row.state_version, network_profile=row.network_profile, reason=row.reason,
        prev_checksum=row.prev_checksum, checksum=row.checksum, occurred_at=row.occurred_at,
    )


def _raise(error: ExecutionAuditError) -> None:
    raise HTTPException(
        status_code=404 if error.code in {"RUN_NOT_FOUND", "COMMAND_CLASS_UNGOVERNED"} else 422,
        detail={"error_code": error.code, "message": error.message},
    )


@router.get("/runs/{run_id}/execution-audit-trail", response_model=ExecutionAuditListDto)
def list_audit_trail(
    run_id: str,
    service: ExecutionAuditTrailService = Depends(get_audit_service),
) -> ExecutionAuditListDto:
    try:
        entries = service.list_entries(run_id)
    except ExecutionAuditError as error:
        _raise(error)
    return ExecutionAuditListDto(entries=[_entry_dto(row) for row in entries])


@router.get("/runs/{run_id}/execution-audit-trail/verify", response_model=ExecutionAuditVerificationDto)
def verify_audit_trail(
    run_id: str,
    service: ExecutionAuditTrailService = Depends(get_audit_service),
) -> ExecutionAuditVerificationDto:
    try:
        verification = service.verify_trail(run_id)
    except ExecutionAuditError as error:
        _raise(error)
    return ExecutionAuditVerificationDto(**verification)
