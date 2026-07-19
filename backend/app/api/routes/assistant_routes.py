"""API routes for migration assistant (S4-F11).

POST /api/v1/runs/{run_id}/assistant/messages — send a message to the assistant
GET  /api/v1/runs/{run_id}/assistant/messages — get conversation metadata
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.errors import error_response
from app.core.config import get_settings
from app.services.assistant_context_service import (
    AssistantContextService,
    AssistantError,
    AssistantMessageRequest,
)

router = APIRouter(prefix="/runs/{run_id}/assistant", tags=["assistant"])


class ContractModel(BaseModel):
    """Base for inline route-level DTOs."""
    model_config = {"extra": "forbid", "frozen": True}


class SendMessageRequestDto(ContractModel):
    message: str = Field(min_length=1, max_length=10000)
    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    expected_state_version: int = Field(default=1, ge=1)
    suggested_questions: list[str] = Field(default_factory=list)


class SendMessageResponseDto(ContractModel):
    response: str
    status: str
    conversation_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    deterministic_fallback: bool = False
    artifact_ids: list[str] = Field(default_factory=list)


class ConversationInfoDto(ContractModel):
    conversation_id: str
    run_id: str
    actor: str
    message_count: int = 0
    total_tokens_used: int = 0
    total_cost_usd: float = 0.0
    created_at: str
    updated_at: str


def get_assistant_service() -> AssistantContextService:
    settings = get_settings()
    return AssistantContextService(settings)


@router.post("/messages", response_model=SendMessageResponseDto, status_code=201)
def send_message(
    run_id: str,
    request: SendMessageRequestDto,
    http_request: Request,
    service: AssistantContextService = Depends(get_assistant_service),
):
    try:
        result = service.send_message(AssistantMessageRequest(
            run_id=run_id,
            actor=request.actor,
            message=request.message,
            idempotency_key=request.idempotency_key,
            expected_state_version=request.expected_state_version,
            suggested_questions=list(request.suggested_questions),
        ))
    except AssistantError as error:
        status = 404 if error.code == "RUN_NOT_FOUND" else 422
        return error_response(http_request, status_code=status, error_code=error.code, message=error.message)

    return SendMessageResponseDto(
        response=result.response,
        status=result.status,
        conversation_id=result.conversation_id,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        deterministic_fallback=result.deterministic_fallback,
        artifact_ids=[r.artifact_id for r in result.artifact_refs],
    )


@router.get("/messages", response_model=ConversationInfoDto | None)
def get_conversation(
    run_id: str,
    actor: str,
    http_request: Request,
    service: AssistantContextService = Depends(get_assistant_service),
):
    conv = service.get_conversation(run_id, actor)
    if conv is None:
        return None
    return ConversationInfoDto(
        conversation_id=conv.conversation_id,
        run_id=conv.run_id,
        actor=conv.actor,
        message_count=conv.message_count,
        total_tokens_used=conv.total_tokens_used,
        total_cost_usd=conv.total_cost_usd,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
    )
