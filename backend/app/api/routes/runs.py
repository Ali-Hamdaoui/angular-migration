"""Versioned authoritative migration-run API."""

import asyncio
import json
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.errors import error_response
from app.core.config import get_settings
from app.domain.contracts import (
    AuthoritativeRunMutationResultDto,
    AuthoritativeRunStateDto,
    CancelAuthoritativeRunRequestDto,
    CreateAuthoritativeRunRequestDto,
    RunTimingDto,
    StartAuthoritativeRunRequestDto,
)
from app.services.migration_run_service import CreateRunRequest, MigrationRunError, MigrationRunService
from app.services.run_timing_service import RunTimingError, RunTimingService
from app.repositories.models import WorkflowEventModel
from app.repositories.session import session_scope

router = APIRouter(prefix="/runs", tags=["runs"])


def get_run_service() -> MigrationRunService:
    return MigrationRunService(get_settings())


def get_run_timing_service() -> RunTimingService:
    return RunTimingService()


def _error(request: Request, error: MigrationRunError):
    status = 404 if error.code == "RUN_NOT_FOUND" else 409 if error.code in {"ACTIVE_RUN_EXISTS", "G01_NOT_APPROVED", "G01_STALE", "G01_EXPIRED", "RUN_NOT_STARTABLE", "SOURCE_INTAKE_ALREADY_ACTIVE", "SOURCE_INTAKE_RETRY_NOT_ALLOWED", "TARGET_RESERVATION_INVALID", "GRAPH_HANDOFF_FAILED", "STALE_STATE_VERSION", "RUN_CANCELLATION_BLOCKED", "RUN_NOT_CANCELLABLE"} else 422
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
        run_id=result.run_id, job_id=result.job_id, status=result.status, state_version=result.state_version,
        event_sequence=result.event_sequence, graph_thread_id=result.graph_thread_id,
        idempotent_replay=result.idempotent_replay, artifacts=list(result.artifacts),
    )


@router.post("/{run_id}/start", response_model=AuthoritativeRunMutationResultDto, status_code=202)
def start_run(run_id: str, request: StartAuthoritativeRunRequestDto, http_request: Request, service: MigrationRunService = Depends(get_run_service)):
    try:
        result = service.start(run_id=run_id, expected_state_version=request.expected_state_version, idempotency_key=request.idempotency_key, actor=request.actor)
    except MigrationRunError as error:
        return _error(http_request, error)
    return AuthoritativeRunMutationResultDto(
        run_id=result.run_id, job_id=result.job_id, status=result.status, state_version=result.state_version,
        event_sequence=result.event_sequence, graph_thread_id=result.graph_thread_id,
        idempotent_replay=result.idempotent_replay, artifacts=list(result.artifacts),
    )


@router.post("/{run_id}/retry-source-intake", response_model=AuthoritativeRunMutationResultDto, status_code=202)
def retry_source_intake(run_id: str, request: StartAuthoritativeRunRequestDto, http_request: Request, service: MigrationRunService = Depends(get_run_service)):
    try:
        result = service.retry_source_intake(run_id=run_id, expected_state_version=request.expected_state_version, idempotency_key=request.idempotency_key, actor=request.actor)
    except MigrationRunError as error:
        return _error(http_request, error)
    return AuthoritativeRunMutationResultDto(
        run_id=result.run_id, job_id=result.job_id, status=result.status, state_version=result.state_version,
        event_sequence=result.event_sequence, graph_thread_id=result.graph_thread_id,
        idempotent_replay=result.idempotent_replay, artifacts=list(result.artifacts),
    )


@router.post("/{run_id}/cancel", response_model=AuthoritativeRunMutationResultDto)
def cancel_run(run_id: str, request: CancelAuthoritativeRunRequestDto, http_request: Request, service: MigrationRunService = Depends(get_run_service)):
    try:
        result = service.cancel(run_id=run_id, expected_state_version=request.expected_state_version, idempotency_key=request.idempotency_key, actor=request.actor)
    except MigrationRunError as error:
        return _error(http_request, error)
    return AuthoritativeRunMutationResultDto(
        run_id=result.run_id, job_id=result.job_id, status=result.status, state_version=result.state_version,
        event_sequence=result.event_sequence, graph_thread_id=result.graph_thread_id,
        idempotent_replay=result.idempotent_replay, artifacts=list(result.artifacts),
    )


@router.get("/{run_id}/timing", response_model=RunTimingDto)
def read_run_timing(run_id: str, http_request: Request, service: RunTimingService = Depends(get_run_timing_service)):
    try:
        with session_scope() as session:
            return service.build(session, run_id)
    except RunTimingError as error:
        return _error(http_request, error)


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
        last_activity = time.monotonic()
        while not await request.is_disconnected():
            with session_scope() as session:
                events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id).where(WorkflowEventModel.sequence > last_sequence).order_by(WorkflowEventModel.sequence)))
            for event in events:
                last_sequence = event.sequence
                payload = {"event_id": event.id, "run_id": event.run_id, "stage_id": event.stage_id, "event_type": event.event_type, "occurred_at": event.occurred_at.isoformat(), "sequence": event.sequence, "payload": event.payload}
                yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {json.dumps(payload, sort_keys=True)}\n\n"
                last_activity = time.monotonic()
            if not events and time.monotonic() - last_activity >= 15:
                yield ": heartbeat\n\n"
                last_activity = time.monotonic()
            await asyncio.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})
