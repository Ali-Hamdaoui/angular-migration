"""Typed run-scoped Migration Follow-up Assistant API."""

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.errors import error_response
from app.api.authentication import assistant_authenticated_actor
from app.domain.contracts import AssistantHistoryDto, AssistantMessageRequestDto, AssistantMessageResultDto
from app.services.assistant_context_service import AssistantContextService, AssistantRequestError
from app.repositories.models import AssistantLifecycleEventModel
from app.repositories.session import session_scope

router = APIRouter(prefix="/runs/{run_id}/assistant", tags=["assistant"])


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
        return error_response(request, status_code=error.status_code, error_code=error.code, message=error.message)


@router.get("/messages", response_model=AssistantHistoryDto)
def get_messages(run_id: str, conversation_id: str | None = None, actor: str = Depends(assistant_authenticated_actor), service: AssistantContextService = Depends(get_service)):
    _authorize(service, run_id, actor)
    return service.history(run_id, conversation_id, actor=actor)


@router.get("/events")
def stream_events(run_id: str, request: Request, actor: str = Depends(assistant_authenticated_actor), service: AssistantContextService = Depends(get_service)):
    _authorize(service, run_id, actor)
    raw_last_event_id = request.headers.get("last-event-id") or request.query_params.get("last_event_id")
    last_sequence = int(raw_last_event_id) if raw_last_event_id and raw_last_event_id.isdigit() else 0

    async def event_stream():
        with session_scope() as session:
            events = list(session.scalars(select(AssistantLifecycleEventModel).where(AssistantLifecycleEventModel.run_id == run_id, AssistantLifecycleEventModel.sequence > last_sequence).order_by(AssistantLifecycleEventModel.sequence)))
        for event in events:
            payload = {"event_id": event.id, "run_id": event.run_id, "conversation_id": event.conversation_id, "message_id": event.message_id, "event_type": event.event_type, "sequence": event.sequence, "state_version": event.state_version, "status": event.status, "correlation_id": event.correlation_id, "occurred_at": event.occurred_at.isoformat(), "payload": event.payload}
            yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {json.dumps(payload, sort_keys=True)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})
