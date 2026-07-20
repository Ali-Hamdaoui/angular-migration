"""API routes for command execution (G01 S3-F02).

Provides run-scoped command queuing and retrieval.
All execution goes through the CommandExecutor service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

import json
import time
from typing import Generator

from app.api.errors import error_response
from app.core.config import get_settings
from app.domain.contracts import (
    CommandExecutionResponseDto,
    CommandExecuteRequestDto,
    CancelCommandRequestDto,
    LogChunkResponseDto,
)
from app.repositories.session import session_scope
from app.services.command_executor_service import (
    CommandExecutorError,
    CommandExecutorService,
    CommandExecutionResponse,
)
from app.services.command_log_service import CommandLogService
from app.services.job_supervisor_service import JobSupervisorService, JobSupervisorError

router = APIRouter(prefix="/runs", tags=["run-commands"])


def get_executor() -> CommandExecutorService:
    return CommandExecutorService()


@router.post("/{run_id}/commands", status_code=201)
def queue_command(
    run_id: str,
    body: CommandExecuteRequestDto,
    request: Request,
    executor: CommandExecutorService = Depends(get_executor),
):
    """Queue and execute one approved command for a migration run.

    The command must be registered in the structured command registry and
    pass all policy checks. This endpoint blocks until the command completes.
    """
    with session_scope() as session:
        try:
            result = executor.queue_command(
                session,
                run_id=run_id,
                stage_id=body.stage_id,
                command_id=body.command_id,
                executable=body.executable,
                arguments=body.arguments,
                idempotency_key=body.idempotency_key,
                requested_by=body.requested_by,
                requester=body.requester,
                working_directory_alias=body.working_directory_alias,
                working_directory=body.working_directory,
                runtime_profile_id=body.runtime_profile_id,
                timeout_seconds=body.timeout_seconds,
                network_profile=body.network_profile,
                cancellation_policy=body.cancellation_policy,
            )
        except CommandExecutorError as error:
            status_code = 409 if error.code in {"STALE_STATE"} else 422
            return error_response(request, status_code=status_code, error_code=error.code, message=error.message)

        return CommandExecutionResponseDto(
            execution_id=result.execution_id,
            run_id=result.run_id,
            command_id=result.command_id,
            status=result.status,
            state_version=result.state_version,
            event_sequence=result.event_sequence,
            idempotent_replay=result.idempotent_replay,
        )


@router.get("/{run_id}/commands/{execution_id}")
def get_command_execution(
    run_id: str,
    execution_id: str,
    request: Request,
    executor: CommandExecutorService = Depends(get_executor),
):
    """Get the details of a specific command execution."""
    with session_scope() as session:
        model = executor.get_command_execution(session, run_id, execution_id)
        if model is None:
            return error_response(
                request,
                status_code=404,
                error_code="EXECUTION_NOT_FOUND",
                message=f"Command execution '{execution_id}' not found for run '{run_id}'",
            )
        return CommandExecutionResponseDto(
            execution_id=model.id,
            run_id=model.run_id,
            command_id=model.command_id or "",
            status=model.status,
            state_version=model.state_version or 1,
            event_sequence=model.event_sequence or 1,
        )


@router.get("/{run_id}/commands")
def list_command_executions(
    run_id: str,
    executor: CommandExecutorService = Depends(get_executor),
):
    """List all command executions for a run."""
    with session_scope() as session:
        models = executor.list_command_executions(session, run_id)
        return {
            "run_id": run_id,
            "executions": [
                CommandExecutionResponseDto(
                    execution_id=m.id,
                    run_id=m.run_id,
                    command_id=m.command_id or "",
                    status=m.status,
                    state_version=m.state_version or 1,
                    event_sequence=m.event_sequence or 1,
                )
                for m in models
            ],
            "total": len(models),
        }


@router.get("/{run_id}/commands/{execution_id}/logs")
def get_command_logs(
    run_id: str,
    execution_id: str,
    request: Request,
    offset: int = 0,
    limit: int = 1000,
    stream: str | None = None,
):
    """Get log chunks for a command execution."""
    with session_scope() as session:
        log_service = CommandLogService()
        chunks, total = log_service.get_logs(
            session, execution_id,
            offset=offset,
            limit=min(limit, 5000),
            stream_filter=stream,
        )
        return {
            "execution_id": execution_id,
            "run_id": run_id,
            "chunks": [LogChunkResponseDto(
                sequence=c.sequence,
                stream=c.stream,
                text=c.text,
                redacted=c.redacted,
                created_at=c.created_at,
            ) for c in chunks],
            "total": total,
            "offset": offset,
            "limit": limit,
        }


@router.get("/{run_id}/commands/{execution_id}/logs/summary")
def get_command_log_summary(
    run_id: str,
    execution_id: str,
):
    """Get a summary of available log streams for a command."""
    with session_scope() as session:
        log_service = CommandLogService()
        return log_service.get_stream_summary(session, execution_id)


@router.get("/{run_id}/commands/{execution_id}/logs/stream")
def stream_command_logs(
    run_id: str,
    execution_id: str,
    cursor: int = 0,
    stream: str | None = None,
    poll_interval: float = 0.5,
):
    """SSE endpoint that streams log chunks as they become available.

    Accepts ?cursor=<seq> to resume from a known sequence number and
    ?stream=stdout|stderr to filter by stream.  The connection stays
    open and emits new chunks as ``data:`` SSE lines.

    When no new data is available for 30 seconds the connection is
    closed gracefully.
    """
    log_service = CommandLogService()
    idle_seconds = 0
    max_idle = 30.0

    def generate() -> Generator[str, None, None]:
        nonlocal cursor, idle_seconds
        yield f"event: connected\ndata: {json.dumps({'execution_id': execution_id, 'cursor': cursor})}\n\n"
        while idle_seconds < max_idle:
            with session_scope() as session:
                chunks, _total = log_service.get_logs(
                    session, execution_id,
                    cursor=cursor,
                    limit=200,
                    stream_filter=stream,
                )
            if chunks:
                idle_seconds = 0
                for chunk in chunks:
                    cursor = chunk.sequence
                    yield f"event: chunk\ndata: {json.dumps({'sequence': chunk.sequence, 'stream': chunk.stream, 'text': chunk.text, 'redacted': chunk.redacted})}\n\n"
                yield f"event: cursor\ndata: {json.dumps({'cursor': cursor})}\n\n"
            else:
                idle_seconds += poll_interval
            time.sleep(poll_interval)
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/{run_id}/commands/{execution_id}/cancel")
def cancel_command(
    run_id: str,
    execution_id: str,
    body: CancelCommandRequestDto,
    request: Request,
    executor: CommandExecutorService = Depends(get_executor),
):
    """Cancel a running command execution."""
    with session_scope() as session:
        try:
            result = executor.request_cancel(
                session,
                run_id=run_id,
                execution_id=execution_id,
                actor=body.actor,
                idempotency_key=body.idempotency_key,
            )
        except CommandExecutorError as error:
            status_code = 404 if error.code == "EXECUTION_NOT_FOUND" else 409
            return error_response(request, status_code=status_code, error_code=error.code, message=error.message)
        except JobSupervisorError as error:
            status_code = 404 if error.code == "EXECUTION_NOT_FOUND" else 409
            return error_response(request, status_code=status_code, error_code=error.code, message=error.message)
        return result


@router.get("/{run_id}/active-command")
def get_active_command(
    run_id: str,
    request: Request,
):
    """Get the currently active command for a run."""
    with session_scope() as session:
        supervisor = JobSupervisorService()
        execution = supervisor.get_active_command(session, run_id)
        if execution is None:
            return {"run_id": run_id, "active_command": None}
        return {
            "run_id": run_id,
            "active_command": {
                "execution_id": execution.id,
                "command_id": execution.command_id,
                "executable": execution.executable,
                "arguments": execution.arguments,
                "status": execution.status,
                "started_at": execution.started_at.isoformat() if execution.started_at else None,
            },
        }


@router.get("/{run_id}/active-lease")
def get_active_lease(
    run_id: str,
    request: Request,
):
    """Get the active worker lease for a run."""
    with session_scope() as session:
        supervisor = JobSupervisorService()
        lease = supervisor.get_active_lease(session, run_id)
        if lease is None:
            return {"run_id": run_id, "active_lease": None}
        return {
            "run_id": run_id,
            "active_lease": {
                "lease_id": lease.id,
                "worker_id": lease.worker_id,
                "execution_id": lease.execution_id,
                "acquired_at": lease.acquired_at.isoformat() if lease.acquired_at else None,
                "expires_at": lease.expires_at.isoformat() if lease.expires_at else None,
            },
        }
