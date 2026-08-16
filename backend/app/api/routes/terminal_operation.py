"""Terminal operation API (V2 F06)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.terminal_operation_contracts import (
    TerminalActionRequest,
    TerminalDiagnosticsDto,
    TerminalNextActionDto,
    TerminalResumeDto,
)
from app.services.terminal_operation_service import TerminalOperationError, TerminalOperationService

router = APIRouter(tags=["terminal-operation"])


def get_terminal_service() -> TerminalOperationService:
    return TerminalOperationService()


def _raise(error: TerminalOperationError) -> None:
    raise HTTPException(status_code=404 if error.code == "RUN_NOT_FOUND" else 422,
                        detail={"error_code": error.code, "message": error.message})


@router.get("/terminal/runs/{run_id}/next-action", response_model=TerminalNextActionDto)
def terminal_next_action(
    run_id: str,
    service: TerminalOperationService = Depends(get_terminal_service),
) -> TerminalNextActionDto:
    try:
        action = service.next_action(run_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail={"error_code": "RUN_NOT_FOUND", "message": str(exc)})
    return TerminalNextActionDto(**action)


@router.get("/terminal/runs/{run_id}/diagnostics", response_model=TerminalDiagnosticsDto)
def terminal_diagnostics(
    run_id: str,
    service: TerminalOperationService = Depends(get_terminal_service),
) -> TerminalDiagnosticsDto:
    return TerminalDiagnosticsDto(**service.terminal_diagnostics(run_id))


@router.post("/terminal/runs/{run_id}/resume", response_model=TerminalResumeDto)
def terminal_resume(
    run_id: str,
    request: TerminalActionRequest,
    service: TerminalOperationService = Depends(get_terminal_service),
) -> TerminalResumeDto:
    return TerminalResumeDto(**service.terminal_resume(run_id))
