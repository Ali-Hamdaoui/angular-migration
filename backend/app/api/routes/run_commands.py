"""API routes for command execution (G01 S3-F02).

Provides run-scoped command queuing and retrieval.
All execution goes through the CommandExecutor service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

import json
import asyncio
from time import monotonic
from typing import AsyncGenerator, Generator

from app.api.errors import error_response
from app.api.authentication import authenticated_actor, authorize_run
from app.core.config import get_settings
from app.domain.contracts import (
    CommandExecutionResponseDto,
    CommandExecuteRequestDto,
    CancelCommandRequestDto,
    LogChunkResponseDto,
)
from app.repositories.session import session_scope
from app.repositories.models.workflow import CommandExecutionModel
from app.services.command_executor_service import (
    CommandExecutorError,
    CommandExecutorService,
    CommandExecutionResponse,
)
from app.services.command_log_service import CommandLogService
from app.services.job_supervisor_service import JobSupervisorService, JobSupervisorError

router = APIRouter(prefix="/runs", tags=["run-commands"])
VALID_LOG_STREAMS = {"stdout", "stderr", "system"}


def get_executor() -> CommandExecutorService:
    return CommandExecutorService()


@router.post("/{run_id}/commands", status_code=202)
def queue_command(
    run_id: str,
    body: CommandExecuteRequestDto,
    request: Request,
    actor: str = Depends(authenticated_actor),
    executor: CommandExecutorService = Depends(get_executor),
):
    """Queue an accepted authorization for worker-owned execution."""
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        try:
            result = executor.queue_authorized_command(
                session,
                run_id=run_id,
                authorization_decision_id=body.authorization_decision_id,
                expected_state_version=body.expected_state_version,
                idempotency_key=body.idempotency_key,
                requested_by=actor,
                correlation_id=request.headers.get("x-correlation-id"),
            )
        except CommandExecutorError as error:
            status_code = 404 if error.code in {"RUN_NOT_FOUND", "AUTHORIZATION_DECISION_NOT_FOUND", "COMMAND_TEMPLATE_NOT_FOUND"} else 409 if error.code in {"STALE_STATE_VERSION", "AUTHORIZATION_STALE", "IDEMPOTENCY_KEY_CONFLICT", "IDEMPOTENCY_KEY_REUSED", "AUTHORIZATION_IDEMPOTENCY_MISMATCH"} else 422
            details = dict(error.details)
            if error.code == "STALE_STATE_VERSION":
                details["guidance"] = "Refresh the authoritative run snapshot and retry."
            return error_response(request, status_code=status_code, error_code=error.code, message=error.message, details=details)
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
            stdout_artifact_id=result.stdout_artifact_id,
            stderr_artifact_id=result.stderr_artifact_id,
            command_log_artifact_id=result.command_log_artifact_id,
            manifest_artifact_id=result.manifest_artifact_id,
            result_artifact_id=result.result_artifact_id,
            executable=result.executable,
            arguments=result.arguments,
            safe_relative_working_directory=result.safe_relative_working_directory,
            runtime_checksum=result.runtime_checksum,
            worker_id=result.worker_id,
            failure_reason=result.failure_reason,
            request_payload_hash=result.request_payload_hash,
            cancel_requested_at=getattr(result, "cancel_requested_at", None),
            cancel_requested_by=getattr(result, "cancel_requested_by", None),
            cancelled=bool(getattr(result, "cancelled", False)),
            timed_out=bool(getattr(result, "timed_out", False)),
            claim_attempt=getattr(result, "claim_attempt", None),
        )


@router.get("/{run_id}/commands/{execution_id}")
def get_command_execution(
    run_id: str,
    execution_id: str,
    request: Request,
    actor: str = Depends(authenticated_actor),
    executor: CommandExecutorService = Depends(get_executor),
):
    """Get the details of a specific command execution."""
    with session_scope() as session:
        authorize_run(session, run_id, actor)
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
    actor: str = Depends(authenticated_actor),
    executor: CommandExecutorService = Depends(get_executor),
):
    """List all command executions for a run."""
    with session_scope() as session:
        authorize_run(session, run_id, actor)
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
    actor: str = Depends(authenticated_actor),
    offset: int = 0,
    limit: int = 1000,
    stream: str | None = None,
    cursor: int | None = None,
):
    """Get log chunks for a command execution."""
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        if CommandExecutorService().get_command_execution(session, run_id, execution_id) is None:
            return error_response(request, status_code=404, error_code="EXECUTION_NOT_FOUND", message="Command execution not found")
        log_service = CommandLogService()
        if stream is not None and stream not in VALID_LOG_STREAMS:
            return error_response(request, status_code=422, error_code="INVALID_LOG_STREAM", message="Stream must be one of stdout, stderr, or system", details={"allowed_streams": sorted(VALID_LOG_STREAMS)})
        if offset < 0 or limit < 1 or cursor is not None and cursor < 0:
            return error_response(request, status_code=422, error_code="INVALID_LOG_CURSOR", message="Cursor, offset, and limit must be non-negative and limit must be positive")
        chunks, total = log_service.get_logs(
            session, execution_id, run_id=run_id,
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
                truncated=c.truncated,
                created_at=c.created_at,
                byte_count=c.byte_count,
                character_count=c.character_count,
            ) for c in chunks],
            "total": total,
            "offset": offset,
            "limit": min(limit, 5000),
        }


@router.get("/{run_id}/commands/{execution_id}/logs/summary")
def get_command_log_summary(
    run_id: str,
    execution_id: str,
    request: Request,
    actor: str = Depends(authenticated_actor),
):
    """Get a summary of available log streams for a command."""
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        if CommandExecutorService().get_command_execution(session, run_id, execution_id) is None:
            return error_response(request, status_code=404, error_code="EXECUTION_NOT_FOUND", message="Command execution not found")
        log_service = CommandLogService()
        return log_service.get_stream_summary(session, execution_id, run_id=run_id)


@router.get("/{run_id}/commands/{execution_id}/logs/stream")
def stream_command_logs(
    run_id: str,
    execution_id: str,
    request: Request,
    actor: str = Depends(authenticated_actor),
    cursor: int | None = None,
    stream: str | None = None,
    poll_interval: float = 0.5,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    stream_actor: str | None = Query(default=None, alias="actor"),
):
    """Replay and tail durable logs using the sequence cursor.

    Explicit ``cursor`` takes precedence over ``Last-Event-ID``; absent both,
    the stream starts at zero. Only ``sequence > cursor`` is returned.
    """
    if cursor is not None and cursor < 0:
        return error_response(request, status_code=422, error_code="INVALID_LOG_CURSOR", message="Cursor must be non-negative")
    if cursor is None and last_event_id is not None:
        try:
            cursor = int(last_event_id)
        except ValueError:
            return error_response(request, status_code=422, error_code="INVALID_LAST_EVENT_ID", message="Last-Event-ID must be an integer log sequence")
        if cursor < 0:
            return error_response(request, status_code=422, error_code="INVALID_LAST_EVENT_ID", message="Last-Event-ID must be non-negative")
    cursor = cursor or 0
    if stream is not None and stream not in VALID_LOG_STREAMS:
        return error_response(request, status_code=422, error_code="INVALID_LOG_STREAM", message="Stream must be one of stdout, stderr, or system", details={"allowed_streams": sorted(VALID_LOG_STREAMS)})
    poll_interval = min(max(poll_interval, 0.1), 5.0)
    # Native EventSource cannot attach custom headers. The frontend supplies
    # the same authenticated local-control-plane actor as a query value for
    # this SSE-only endpoint; normal command and artifact routes remain
    # header-authenticated.
    effective_actor = stream_actor.strip() if isinstance(stream_actor, str) and stream_actor.strip() else actor
    with session_scope() as session:
        authorize_run(session, run_id, effective_actor)
        if CommandExecutorService().get_command_execution(session, run_id, execution_id) is None:
            return error_response(request, status_code=404, error_code="EXECUTION_NOT_FOUND", message="Command execution not found")
    log_service = CommandLogService()
    heartbeat_interval = get_settings().sse_heartbeat_seconds
    terminal_statuses = {"succeeded", "failed", "cancelled", "timed_out", "rejected"}

    async def generate() -> AsyncGenerator[str, None]:
        nonlocal cursor
        last_heartbeat = monotonic()
        model = None
        try:
            while True:
                if await request.is_disconnected():
                    return
                with session_scope() as session:
                    model = session.scalar(select(CommandExecutionModel).where(
                        CommandExecutionModel.id == execution_id,
                        CommandExecutionModel.run_id == run_id,
                    ))
                    chunks, _total = log_service.get_logs(
                        session, execution_id, run_id=run_id, cursor=cursor,
                        limit=200, stream_filter=stream,
                    )
                    summary = log_service.get_stream_summary(session, execution_id, run_id=run_id)
                if model is None:
                    yield "event: stream_error\ndata: " + json.dumps({"code": "EXECUTION_NOT_FOUND", "message": "Command execution not found", "correlation_id": None}) + "\n\n"
                    return
                if chunks:
                    for chunk in chunks:
                        cursor = chunk.sequence
                        payload = {
                            "execution_id": execution_id,
                            "sequence": chunk.sequence,
                            "stream": chunk.stream,
                            "content": chunk.text,
                            "timestamp": chunk.created_at,
                            "redacted": chunk.redacted,
                            "truncated": chunk.truncated,
                        }
                        yield f"id: {chunk.sequence}\nevent: command_log\ndata: {json.dumps(payload)}\n\n"
                    yield "event: log_checkpoint\ndata: " + json.dumps({
                        "execution_id": execution_id,
                        "earliest_sequence": summary["first_sequence"],
                        "latest_sequence": summary["last_sequence"],
                        "status": model.status,
                        "truncated": summary["truncated"],
                    }) + "\n\n"
                    continue
                if model.status in terminal_statuses:
                    completion = {
                        "execution_id": execution_id,
                        "run_id": run_id,
                        "status": model.status,
                        "last_sequence": summary["last_sequence"],
                        "stdout_artifact_id": model.stdout_artifact_id,
                        "stderr_artifact_id": model.stderr_artifact_id,
                        "completed_at": model.finished_at.isoformat() if model.finished_at else None,
                    }
                    yield "event: execution_complete\ndata: " + json.dumps(completion) + "\n\n"
                    return
                now = monotonic()
                if now - last_heartbeat >= heartbeat_interval:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
                await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            correlation_id = model.correlation_id if model is not None else None
            yield "event: stream_error\ndata: " + json.dumps({"code": "LOG_STREAM_FAILED", "message": "The log stream could not be continued.", "correlation_id": correlation_id}) + "\n\n"

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
    actor: str = Depends(authenticated_actor),
    executor: CommandExecutorService = Depends(get_executor),
):
    """Cancel a running command execution."""
    with session_scope() as session:
        authorize_run(session, run_id, actor)
        try:
            result = executor.request_cancel(
                session,
                run_id=run_id,
                execution_id=execution_id,
                actor=actor,
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
    actor: str = Depends(authenticated_actor),
):
    """Get the currently active command for a run."""
    with session_scope() as session:
        authorize_run(session, run_id, actor)
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
    actor: str = Depends(authenticated_actor),
):
    """Get the active worker lease for a run."""
    with session_scope() as session:
        authorize_run(session, run_id, actor)
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
