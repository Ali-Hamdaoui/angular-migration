"""API routes for command execution (G01 S3-F02).

Provides run-scoped command queuing and retrieval.
All execution goes through the CommandExecutor service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.errors import error_response
from app.core.config import get_settings
from app.domain.contracts import (
    CommandExecutionResponseDto,
    CommandExecuteRequestDto,
)
from app.repositories.session import session_scope
from app.services.command_executor_service import (
    CommandExecutorError,
    CommandExecutorService,
    CommandExecutionResponse,
)

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
