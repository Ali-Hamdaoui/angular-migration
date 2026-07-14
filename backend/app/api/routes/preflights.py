"""Production preflight and G01 approval API."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.domain.preflight import G01Decision, G01DecisionRequest, PreflightRequest, PreflightResult
from app.services.production_preflight_service import PreflightError, ProductionPreflightService
from app.repositories.session import session_scope
from app.services.preflight_events import format_preflight_sse, replay_preflight_events

router = APIRouter(prefix="/preflights", tags=["preflights"])
draft_approval_router = APIRouter(tags=["preflights"])


def get_preflight_service() -> ProductionPreflightService:
    return ProductionPreflightService(get_settings())


def _handle(error: PreflightError) -> None:
    raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message}) from error


@router.post("", response_model=PreflightResult)
def create_preflight(request: PreflightRequest, service: ProductionPreflightService = Depends(get_preflight_service)) -> PreflightResult:
    try:
        return service.create(request)
    except PreflightError as error:
        _handle(error)


@router.get("/{preflight_id}", response_model=PreflightResult)
def read_preflight(preflight_id: str, service: ProductionPreflightService = Depends(get_preflight_service)) -> PreflightResult:
    result = service.get(preflight_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Preflight not found")
    return result


@router.post("/{preflight_id}/g01/decisions", response_model=G01Decision)
def decide_g01(preflight_id: str, request: G01DecisionRequest, service: ProductionPreflightService = Depends(get_preflight_service)) -> G01Decision:
    try:
        return service.decide(preflight_id, request)
    except PreflightError as error:
        _handle(error)

@draft_approval_router.post("/runs/drafts/{draft_id}/approvals/{gate_id}/decisions", response_model=G01Decision)
def decide_g01_draft(draft_id: str, gate_id: str, request: G01DecisionRequest, service: ProductionPreflightService = Depends(get_preflight_service)) -> G01Decision:
    try:
        return service.decide(draft_id, request.model_copy(update={"gate_id": gate_id}))
    except PreflightError as error:
        _handle(error)

@router.get("/{preflight_id}/events")
def stream_preflight_events(preflight_id: str, request: Request) -> StreamingResponse:
    raw_last_event_id = request.headers.get("last-event-id") or request.query_params.get("last_event_id")
    last_event_id = int(raw_last_event_id) if raw_last_event_id and raw_last_event_id.isdigit() else None
    with session_scope() as session:
        events = replay_preflight_events(session, preflight_id, last_event_id=last_event_id)
    async def event_stream():
        for event in events:
            yield format_preflight_sse(event)
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})
