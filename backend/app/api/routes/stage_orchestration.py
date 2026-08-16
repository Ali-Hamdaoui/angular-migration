"""Dynamic stage orchestration API (V2 F12)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.stage_orchestration_contracts import (
    StageChainRecordDto,
    StageChainStateDto,
    StageRunRecordDto,
)
from app.services.stage_chain_orchestrator import StageChainOrchestrator, StageOrchestrationError

router = APIRouter(tags=["stage-orchestration"])


def get_orchestrator() -> StageChainOrchestrator:
    return StageChainOrchestrator()


def _raise(error: StageOrchestrationError) -> None:
    raise HTTPException(status_code=404 if error.code == "RUN_NOT_FOUND" else 409 if error.code == "CHAIN_NOT_STARTED" else 422,
                        detail={"error_code": error.code, "message": error.message})


def _stage_dto(s) -> StageRunRecordDto:
    return StageRunRecordDto(stage_order=s["stage_order"] if isinstance(s, dict) else s.stage_order,
                             stage_id=s["stage_id"] if isinstance(s, dict) else s.stage_id,
                             source_major=s["source_major"] if isinstance(s, dict) else s.source_major,
                             target_major=s["target_major"] if isinstance(s, dict) else s.target_major,
                             status=s["status"] if isinstance(s, dict) else s.status,
                             gate_passed=s["gate_passed"] if isinstance(s, dict) else s.gate_passed,
                             failure_code=s.get("failure_code") if isinstance(s, dict) else s.failure_code)


def _state_dto(state) -> StageChainStateDto:
    return StageChainStateDto(run_id=state.run_id, source_major=state.source_major, target_major=state.target_major,
                              catalogue_version=state.catalogue_version, status=state.status,
                              stages=[_stage_dto(s) for s in state.stages], checksum=state.checksum)


@router.post("/runs/{run_id}/chain/start", response_model=StageChainStateDto)
def start_chain(
    run_id: str,
    service: StageChainOrchestrator = Depends(get_orchestrator),
) -> StageChainStateDto:
    try:
        state = service.start_chain(run_id)
    except StageOrchestrationError as error:
        _raise(error)
    return _state_dto(state)


@router.post("/runs/{run_id}/chain/advance", response_model=StageChainStateDto)
def advance_chain(
    run_id: str,
    service: StageChainOrchestrator = Depends(get_orchestrator),
) -> StageChainStateDto:
    try:
        state = service.advance(run_id)
    except StageOrchestrationError as error:
        _raise(error)
    return _state_dto(state)


@router.post("/runs/{run_id}/chain/stages/{stage_order}/fail", response_model=StageChainStateDto)
def mark_stage_failed(
    run_id: str,
    stage_order: int,
    failure_code: str = "STAGE_FAILED",
    service: StageChainOrchestrator = Depends(get_orchestrator),
) -> StageChainStateDto:
    try:
        state = service.mark_stage_failed(run_id, stage_order, failure_code)
    except StageOrchestrationError as error:
        _raise(error)
    return _state_dto(state)


@router.post("/runs/{run_id}/chain/resume", response_model=StageChainStateDto)
def resume_chain(
    run_id: str,
    service: StageChainOrchestrator = Depends(get_orchestrator),
) -> StageChainStateDto:
    try:
        state = service.resume(run_id)
    except StageOrchestrationError as error:
        _raise(error)
    return _state_dto(state)


@router.get("/runs/{run_id}/chain", response_model=StageChainStateDto)
def current_chain(
    run_id: str,
    service: StageChainOrchestrator = Depends(get_orchestrator),
) -> StageChainStateDto:
    try:
        state = service.current_state(run_id)
    except StageOrchestrationError as error:
        _raise(error)
    return _state_dto(state)
