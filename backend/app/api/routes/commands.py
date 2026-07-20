"""API routes for governed command templates and policy validation (G01 S3-F01).

Provides read-only template inspection and policy validation endpoints.
All execution must pass through these endpoints before process creation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.errors import error_response
from app.domain.contracts import (
    CommandPolicyValidateRequestDto,
    CommandPolicyValidateResponseDto,
    CommandTemplateDto,
    CommandTemplateListDto,
)
from app.repositories.session import session_scope
from app.services.command_registry_service import (
    CommandPolicyEngineService,
    CommandRegistryService,
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

    Audit record and workflow event are persisted by the policy engine's
    validate() method.
    """
    with session_scope() as session:
        result = engine.validate(session, body)
        return result
