"""API routes for governed command templates and policy validation (G01 S3-F01).

Provides read-only template inspection and policy validation endpoints.
All execution must pass through these endpoints before process creation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.errors import error_response
from app.core.config import get_settings
from app.domain.contracts import (
    CommandPolicyValidateRequestDto,
    CommandPolicyValidateResponseDto,
    CommandTemplateDto,
    CommandTemplateListDto,
    WorkflowEventType,
)
from app.repositories.models import WorkflowEventModel, CommandAuthorizationAuditModel
from app.repositories.session import session_scope
from app.services.command_registry_service import (
    CommandPolicyEngineService,
    CommandRegistryError,
    CommandRegistryService,
    CommandPolicyError,
)

router = APIRouter(prefix="/operator", tags=["operator"])


def get_registry() -> CommandRegistryService:
    return CommandRegistryService()


def get_policy_engine() -> CommandPolicyEngineService:
    return CommandPolicyEngineService()


@router.get("/command-templates", response_model=CommandTemplateListDto)
def list_command_templates(
    request: Request,
    registry: CommandRegistryService = Depends(get_registry),
):
    """List all registered command templates."""
    with session_scope() as session:
        result = registry.list_templates(session)
        # Seed defaults if empty
        if result.total == 0:
            registry.seed_defaults(session)
            result = registry.list_templates(session)
        return result


@router.get("/command-templates/{template_id}", response_model=CommandTemplateDto)
def get_command_template(
    template_id: str,
    request: Request,
    registry: CommandRegistryService = Depends(get_registry),
):
    """Get a single command template by ID."""
    with session_scope() as session:
        template = registry.get_template(session, template_id)
        if template is None:
            return error_response(
                request,
                status_code=404,
                error_code="TEMPLATE_NOT_FOUND",
                message=f"Command template '{template_id}' not found",
            )
        return template


@router.post("/command-policy/validate", response_model=CommandPolicyValidateResponseDto)
def validate_command_policy(
    body: CommandPolicyValidateRequestDto,
    request: Request,
    engine: CommandPolicyEngineService = Depends(get_policy_engine),
):
    """Validate a command against the structured registry and policy engine.

    This endpoint does NOT execute the command. It only checks whether the
    command would be authorized. Use POST /api/v1/runs/{id}/commands to
    actually queue execution.
    """
    with session_scope() as session:
        result = engine.validate(session, body)
        now = datetime.now(UTC)

        # Persist the authorization audit record
        audit = CommandAuthorizationAuditModel(
            id=result.authorization_id,
            run_id=result.run_id,
            stage_id=result.stage_id,
            command_id=result.command_id,
            executable=result.executable,
            arguments=result.arguments,
            decision=result.decision,
            reasons=result.reasons,
            policy_version=result.policy_version,
            idempotency_key=body.idempotency_key,
            actor=body.requested_by,
            artifact_ids=[],
            state_version=1,
            created_at=now,
        )
        session.add(audit)

        # Also emit a workflow event
        latest = session.scalar(
            select(WorkflowEventModel)
            .where(WorkflowEventModel.run_id == body.run_id)
            .order_by(WorkflowEventModel.sequence.desc())
            .limit(1)
        )
        event_type = (
            WorkflowEventType.COMMAND_AUTHORIZATION_ACCEPTED
            if result.decision == "accepted"
            else WorkflowEventType.COMMAND_AUTHORIZATION_REJECTED
        )
        event = WorkflowEventModel(
            id=f"event-{uuid4().hex[:12]}",
            run_id=body.run_id,
            stage_id=body.stage_id,
            event_type=event_type.value,
            idempotency_key=body.idempotency_key,
            actor=body.requested_by or "system",
            reason=f"command authorization {result.decision}",
            sequence=(latest.sequence + 1) if latest else 1,
            payload={
                "authorization_id": result.authorization_id,
                "command_id": result.command_id,
                "decision": result.decision,
                "reasons": result.reasons,
                "policy_version": result.policy_version,
            },
            occurred_at=now,
        )
        session.add(event)
        session.flush()

        return result
