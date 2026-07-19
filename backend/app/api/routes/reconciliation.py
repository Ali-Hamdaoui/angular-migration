"""API routes for startup reconciliation (S4-F10).

POST /api/v1/operator/reconciliation — trigger a reconciliation run
GET  /api/v1/operator/reconciliation/latest — get latest reconciliation status
POST /api/v1/runs/{run_id}/resume — resume a run diagnostic hold
"""
from fastapi import APIRouter, Depends, Request

from app.api.errors import error_response
from app.api.routes.runs import ReconciliationRequestDto, ReconciliationStatusDto, ResumeRunRequestDto
from app.core.config import get_settings
from app.domain.contracts import AuthoritativeRunMutationResultDto
from app.services.migration_run_service import MigrationRunError, MigrationRunService
from app.services.reconciliation_service import ReconciliationError, ReconciliationRequest, StartupReconciliationService
from app.state.transition_service import ResumeRejectedError

router = APIRouter(prefix="/operator", tags=["operator"])


def get_reconciliation_service() -> StartupReconciliationService:
    settings = get_settings()
    return StartupReconciliationService(settings)


@router.post("/reconciliation", response_model=ReconciliationStatusDto, status_code=201)
def start_reconciliation(
    request: ReconciliationRequestDto,
    http_request: Request,
    service: StartupReconciliationService = Depends(get_reconciliation_service),
):
    try:
        result = service.execute(ReconciliationRequest(
            idempotency_key=request.idempotency_key,
            actor=request.actor,
        ))
    except ReconciliationError as error:
        return error_response(http_request, status_code=422, error_code=error.code, message=error.message)

    return ReconciliationStatusDto(
        reconciliation_id=result.reconciliation_id,
        backend_instance_id=result.backend_instance_id,
        status=result.status,
        started_at=result.started_at,
        completed_at=result.completed_at,
        stale_leases_found=result.stale_leases_found,
        interrupted_commands_found=result.interrupted_commands_found,
        artifact_mismatches_found=result.artifact_mismatches_found,
        recovered_runs=result.recovered_runs,
        quarantined_runs=result.quarantined_runs,
        graph_reconstructed=result.graph_reconstructed,
        artifacts=[r.artifact_id for r in result.artifact_refs],
        errors=list(result.errors),
    )


@router.get("/reconciliation/latest", response_model=ReconciliationStatusDto | None)
def get_latest_reconciliation(
    http_request: Request,
    service: StartupReconciliationService = Depends(get_reconciliation_service),
):
    result = service.get_latest()
    if result is None:
        return None
    return ReconciliationStatusDto(
        reconciliation_id=result.reconciliation_id,
        backend_instance_id=result.backend_instance_id,
        status=result.status,
        started_at=result.started_at,
        completed_at=result.completed_at,
        stale_leases_found=result.stale_leases_found,
        interrupted_commands_found=result.interrupted_commands_found,
        artifact_mismatches_found=result.artifact_mismatches_found,
        recovered_runs=result.recovered_runs,
        quarantined_runs=result.quarantined_runs,
        graph_reconstructed=result.graph_reconstructed,
        artifacts=[r.artifact_id for r in result.artifact_refs],
        errors=list(result.errors),
    )
