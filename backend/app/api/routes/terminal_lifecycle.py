"""Full terminal lifecycle API (V2 F23)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.terminal_lifecycle_contracts import (
    TerminalLifecycleDriveDto,
    TerminalLifecycleEvidenceDto,
    TerminalLifecycleSequenceDto,
)
from app.services.terminal_lifecycle_service import TerminalLifecycleError, TerminalLifecycleService

router = APIRouter(tags=["terminal-lifecycle"])


def get_lifecycle_service() -> TerminalLifecycleService:
    return TerminalLifecycleService()


def _raise(error: TerminalLifecycleError) -> None:
    raise HTTPException(status_code=404 if error.code == "RUN_NOT_FOUND" else 422,
                        detail={"error_code": error.code, "message": error.message})


@router.get("/terminal/runs/{run_id}/lifecycle", response_model=TerminalLifecycleSequenceDto)
def terminal_lifecycle_sequence(
    run_id: str,
    service: TerminalLifecycleService = Depends(get_lifecycle_service),
) -> TerminalLifecycleSequenceDto:
    try:
        sequence = service.lifecycle_sequence(run_id)
    except TerminalLifecycleError as error:
        _raise(error)
    return TerminalLifecycleSequenceDto(**sequence)


@router.get("/terminal/runs/{run_id}/lifecycle/evidence", response_model=TerminalLifecycleEvidenceDto)
def terminal_lifecycle_evidence(
    run_id: str,
    service: TerminalLifecycleService = Depends(get_lifecycle_service),
) -> TerminalLifecycleEvidenceDto:
    try:
        evidence = service.lifecycle_evidence(run_id)
    except TerminalLifecycleError as error:
        _raise(error)
    return TerminalLifecycleEvidenceDto(**evidence)


@router.post("/terminal/runs/{run_id}/lifecycle/drive", response_model=TerminalLifecycleDriveDto)
def terminal_lifecycle_drive(
    run_id: str,
    service: TerminalLifecycleService = Depends(get_lifecycle_service),
) -> TerminalLifecycleDriveDto:
    try:
        sequence = service.drive_next(run_id)
    except TerminalLifecycleError as error:
        _raise(error)
    return TerminalLifecycleDriveDto(**sequence)
