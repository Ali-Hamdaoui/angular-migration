"""Versioned authoritative migration-run API."""

from fastapi import APIRouter, Depends, Request

from app.api.errors import error_response
from app.core.config import get_settings
from app.domain.contracts import (
    AuthoritativeRunMutationResultDto,
    AuthoritativeRunStateDto,
    CreateAuthoritativeRunRequestDto,
    StartAuthoritativeRunRequestDto,
)
from app.services.migration_run_service import CreateRunRequest, MigrationRunError, MigrationRunService

router = APIRouter(prefix="/runs", tags=["runs"])


def get_run_service() -> MigrationRunService:
    return MigrationRunService(get_settings())


def _error(request: Request, error: MigrationRunError):
    status = 404 if error.code == "RUN_NOT_FOUND" else 409 if error.code in {"ACTIVE_RUN_EXISTS", "G01_NOT_APPROVED", "G01_STALE", "G01_EXPIRED", "RUN_NOT_STARTABLE", "GRAPH_HANDOFF_FAILED"} else 422
    return error_response(request, status_code=status, error_code=error.code, message=error.message)


@router.post("", response_model=AuthoritativeRunMutationResultDto, status_code=201)
def create_run(request: CreateAuthoritativeRunRequestDto, http_request: Request, service: MigrationRunService = Depends(get_run_service)):
    try:
        result = service.create(CreateRunRequest(
            preflight_id=request.preflight_id, input_checksum=request.input_checksum,
            artifact_set_checksum=request.artifact_set_checksum, idempotency_key=request.idempotency_key,
            actor=request.actor, client_constraints=request.client_constraints, pricing_snapshot=request.pricing_snapshot,
        ))
    except MigrationRunError as error:
        return _error(http_request, error)
    return AuthoritativeRunMutationResultDto(
        run_id=result.run_id, status=result.status, state_version=result.state_version,
        event_sequence=result.event_sequence, graph_thread_id=result.graph_thread_id,
        idempotent_replay=result.idempotent_replay, artifacts=list(result.artifacts),
    )


@router.post("/{run_id}/start", response_model=AuthoritativeRunMutationResultDto)
def start_run(run_id: str, request: StartAuthoritativeRunRequestDto, http_request: Request, service: MigrationRunService = Depends(get_run_service)):
    try:
        result = service.start(run_id=run_id, expected_state_version=request.expected_state_version, idempotency_key=request.idempotency_key, actor=request.actor)
    except MigrationRunError as error:
        return _error(http_request, error)
    return AuthoritativeRunMutationResultDto(
        run_id=result.run_id, status=result.status, state_version=result.state_version,
        event_sequence=result.event_sequence, graph_thread_id=result.graph_thread_id,
        idempotent_replay=result.idempotent_replay, artifacts=list(result.artifacts),
    )


@router.get("/{run_id}/state", response_model=AuthoritativeRunStateDto)
def read_run_state(run_id: str, http_request: Request, service: MigrationRunService = Depends(get_run_service)):
    try:
        return service.get_state(run_id)
    except MigrationRunError as error:
        return _error(http_request, error)
