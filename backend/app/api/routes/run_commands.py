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


@router.post("/{run_id}/commands", status_code=202)
def queue_command(
    run_id: str,
    body: CommandExecuteRequestDto,
    request: Request,
    executor: CommandExecutorService = Depends(get_executor),
):
    """Queue an accepted authorization for worker-owned execution."""
    with session_scope() as session:
        try:
            result = executor.queue_authorized_command(
                session,
                run_id=run_id,
                authorization_decision_id=body.authorization_decision_id,
                expected_state_version=body.expected_state_version,
                idempotency_key=body.idempotency_key,
                requested_by=body.requested_by,
                correlation_id=request.headers.get("x-correlation-id"),
            )
        except CommandExecutorError as error:
            status_code = 404 if error.code in {"RUN_NOT_FOUND", "AUTHORIZATION_DECISION_NOT_FOUND", "COMMAND_TEMPLATE_NOT_FOUND"} else 409 if error.code in {"STALE_STATE_VERSION", "AUTHORIZATION_STALE", "IDEMPOTENCY_KEY_CONFLICT", "IDEMPOTENCY_KEY_REUSED", "AUTHORIZATION_IDEMPOTENCY_MISMATCH"} else 422
            details = dict(error.details)
            if error.code == "STALE_STATE_VERSION":
                details["guidance"] = "Refresh the authoritative run snapshot and retry."
            return error_response(request, status_code=status_code, error_code=error.code, message=error.message, details=details)
    executor.dispatch_execution(result.execution_id)
    return CommandExecutionResponseDto(
            execution_id=result.execution_id,
            run_id=result.run_id,
            command_id=result.command_id,
            status=result.status,
            state_version=result.state_version,
            event_sequence=result.event_sequence,
            idempotent_replay=result.idempotent_replay,
            stage_id=result.stage_id,
            authorization_id=result.authorization_id,
            template_id=result.template_id,
            template_version=result.template_version,
            plan_id=result.plan_id,
            plan_version=result.plan_version,
            execution_profile_id=result.execution_profile_id,
            workspace_alias=result.workspace_alias,
            created_at=result.created_at,
            started_at=result.started_at,
            completed_at=result.completed_at,
            duration_ms=result.duration_ms,
            exit_code=result.exit_code,
            failure_code=result.failure_code,
            correlation_id=result.correlation_id,
            artifact_ids=list(result.artifact_ids),
            request_payload_hash=result.request_payload_hash,
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
        return executor._response_from_model(model)


@router.get("/{run_id}/commands")
def list_command_executions(
    run_id: str,
    executor: CommandExecutorService = Depends(get_executor),
):
    """List all command executions for a run."""
    with session_scope() as session:
        models = executor.get_list_command_executions(session, run_id)
        return {
            "run_id": run_id,
            "executions": [
                executor._response_from_model(m)
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
    cursor: int | None = None,
):
    """Get log chunks for a command execution."""
    with session_scope() as session:
        if CommandExecutorService().get_command_execution(session, run_id, execution_id) is None:
            return error_response(request, status_code=404, error_code="EXECUTION_NOT_FOUND", message="Command execution not found")
        log_service = CommandLogService()
        chunks, total = log_service.get_logs(
            session, execution_id,
            offset=offset,
            limit=min(limit, 5000),
            stream_filter=stream,
            cursor=cursor,
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
    request: Request,
):
    """Get a summary of available log streams for a command."""
    with session_scope() as session:
        if CommandExecutorService().get_command_execution(session, run_id, execution_id) is None:
            return error_response(request, status_code=404, error_code="EXECUTION_NOT_FOUND", message="Command execution not found")
        log_service = CommandLogService()
        return log_service.get_stream_summary(session, execution_id)


@router.get("/{run_id}/commands/{execution_id}/logs/stream")
def stream_command_logs(
    run_id: str,
    execution_id: str,
    request: Request,
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
    with session_scope() as session:
        if CommandExecutorService().get_command_execution(session, run_id, execution_id) is None:
            return error_response(request, status_code=404, error_code="EXECUTION_NOT_FOUND", message="Command execution not found")
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
