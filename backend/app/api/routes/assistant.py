"""Typed run-scoped Migration Follow-up Assistant API."""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.errors import error_response
from app.api.authentication import assistant_authenticated_actor
from app.domain.contracts import AssistantHistoryDto, AssistantMessageRequestDto, AssistantMessageResultDto
from app.services.assistant_context_service import AssistantContextService, AssistantRequestError
from app.repositories.models import AssistantLifecycleEventModel
from app.repositories.session import session_scope

router = APIRouter(prefix="/runs/{run_id}/assistant", tags=["assistant"])

# The database remains authoritative; polling is only the SSE liveness
# mechanism. These seams also keep the stream bounded and controllable.
ASSISTANT_SSE_POLL_INTERVAL_SECONDS = 0.25
ASSISTANT_SSE_HEARTBEAT_INTERVAL_SECONDS = 15.0
ASSISTANT_SSE_BATCH_SIZE = 100


def get_service() -> AssistantContextService:
    return AssistantContextService()


def _authorize(service: AssistantContextService, run_id: str, actor: str) -> None:
    service.authorize(run_id, actor)


@router.post("/messages", response_model=AssistantMessageResultDto, status_code=201)
def send_message(run_id: str, payload: AssistantMessageRequestDto, request: Request, actor: str = Depends(assistant_authenticated_actor), service: AssistantContextService = Depends(get_service)):
    try:
        _authorize(service, run_id, actor)
        return service.answer(payload.model_copy(update={"run_id": run_id}), actor=actor)
    except AssistantRequestError as error:
        return error_response(request, status_code=error.status_code, error_code=error.code, message=error.message, details=error.details, correlation_id=error.correlation_id)


@router.get("/messages", response_model=AssistantHistoryDto)
def get_messages(run_id: str, conversation_id: str | None = None, actor: str = Depends(assistant_authenticated_actor), service: AssistantContextService = Depends(get_service)):
    _authorize(service, run_id, actor)
    return service.history(run_id, conversation_id, actor=actor)


@router.get("/events")
def stream_events(run_id: str, request: Request, actor: str = Depends(assistant_authenticated_actor), service: AssistantContextService = Depends(get_service)):
    _authorize(service, run_id, actor)
    # The header is authoritative. A present-but-invalid header must not fall
    # through to the compatibility query parameter.
    raw_last_event_id = request.headers.get("last-event-id")
    if raw_last_event_id is None:
        raw_last_event_id = request.query_params.get("last_event_id")
    if raw_last_event_id in (None, ""):
        last_sequence = 0
    elif raw_last_event_id.isdigit():
        last_sequence = int(raw_last_event_id)
    else:
        raise HTTPException(status_code=400, detail={"error_code": "assistant_invalid_event_cursor", "message": "The Assistant event cursor is invalid.", "details": {}})

    async def event_stream():
        cursor = last_sequence
        heartbeat_deadline = asyncio.get_running_loop().time() + ASSISTANT_SSE_HEARTBEAT_INTERVAL_SECONDS
        try:
            while True:
                if await request.is_disconnected():
                    return
                # Each poll has a fresh bounded session. No database session
                # remains open while the stream is idle.
                with session_scope() as session:
                    events = list(session.scalars(select(AssistantLifecycleEventModel).where(AssistantLifecycleEventModel.run_id == run_id, AssistantLifecycleEventModel.sequence > cursor).order_by(AssistantLifecycleEventModel.sequence).limit(ASSISTANT_SSE_BATCH_SIZE)))
                if events:
                    for event in events:
                        payload = {"event_id": event.id, "run_id": event.run_id, "conversation_id": event.conversation_id, "message_id": event.message_id, "event_type": event.event_type, "sequence": event.sequence, "state_version": event.state_version, "status": event.status, "correlation_id": event.correlation_id, "occurred_at": event.occurred_at.isoformat(), "payload": event.payload}
                        cursor = event.sequence
                        yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {json.dumps(payload, sort_keys=True)}\n\n"
                    heartbeat_deadline = asyncio.get_running_loop().time() + ASSISTANT_SSE_HEARTBEAT_INTERVAL_SECONDS
                    continue
                if asyncio.get_running_loop().time() >= heartbeat_deadline:
                    yield ": heartbeat\n\n"
                    heartbeat_deadline = asyncio.get_running_loop().time() + ASSISTANT_SSE_HEARTBEAT_INTERVAL_SECONDS
                await asyncio.sleep(ASSISTANT_SSE_POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            return

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
