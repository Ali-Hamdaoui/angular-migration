"""Versioned authoritative migration-run API."""

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.errors import error_response
from app.core.config import get_settings
from app.domain.contracts import (
    AuthoritativeRunMutationResultDto,
    AuthoritativeRunStateDto,
    CreateAuthoritativeRunRequestDto,
    StartAuthoritativeRunRequestDto,
)
from app.services.migration_run_service import CreateRunRequest, MigrationRunError, MigrationRunService
from app.repositories.models import WorkflowEventModel
from app.repositories.session import session_scope


class ContractModel(BaseModel):
    """Base for inline route-level DTOs matching domain contract pattern."""
    model_config = {"extra": "forbid", "frozen": True}


class ReconciliationStatusDto(ContractModel):
    """Startup reconciliation result and current status."""
    reconciliation_id: str
    backend_instance_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    stale_leases_found: int = 0
    interrupted_commands_found: int = 0
    artifact_mismatches_found: int = 0
    recovered_runs: int = 0
    quarantined_runs: int = 0
    graph_reconstructed: bool = False
    artifacts: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ResumeRunRequestDto(ContractModel):
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    checkpoint_valid: bool = True
    workspace_valid: bool = True
    policy_compatible: bool = True


class ReconciliationRequestDto(ContractModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)


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


@router.get("/{run_id}/events")
def stream_run_events(run_id: str, request: Request):
    raw_last_event_id = request.headers.get("last-event-id") or request.query_params.get("last_event_id")
    last_sequence = int(raw_last_event_id) if raw_last_event_id and raw_last_event_id.isdigit() else 0

    async def event_stream():
        nonlocal last_sequence
        while not await request.is_disconnected():
            with session_scope() as session:
                events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id).where(WorkflowEventModel.sequence > last_sequence).order_by(WorkflowEventModel.sequence)))
            for event in events:
                last_sequence = event.sequence
                payload = {"event_id": event.id, "run_id": event.run_id, "stage_id": event.stage_id, "event_type": event.event_type, "occurred_at": event.occurred_at.isoformat(), "sequence": event.sequence, "payload": event.payload}
                yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {json.dumps(payload, sort_keys=True)}\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


@router.post("/{run_id}/resume", response_model=AuthoritativeRunMutationResultDto)
def resume_run(
    run_id: str,
    request: ResumeRunRequestDto,
    http_request: Request,
    service: MigrationRunService = Depends(get_run_service),
):
    try:
        result = service.resume(
            run_id=run_id,
            expected_state_version=request.expected_state_version,
            idempotency_key=request.idempotency_key,
            actor=request.actor,
            checkpoint_valid=request.checkpoint_valid,
            workspace_valid=request.workspace_valid,
            policy_compatible=request.policy_compatible,
        )
    except MigrationRunError as error:
        status = 404 if error.code == "RUN_NOT_FOUND" else 409
        return error_response(http_request, status_code=status, error_code=error.code, message=error.message)
    return AuthoritativeRunMutationResultDto(
        run_id=result.run_id, status=result.status, state_version=result.state_version,
        event_sequence=result.event_sequence, graph_thread_id=result.graph_thread_id,
        idempotent_replay=result.idempotent_replay, artifacts=list(result.artifacts),
    )
