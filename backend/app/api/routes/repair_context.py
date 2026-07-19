"""API routes for RepairContextPack — context assembly, persistence, and retrieval."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.errors import error_response
from app.domain.contracts import WorkflowEventType
from app.domain.failure import FailureEvidence
from app.domain.repair_context import (
    ContextBudgetTracker,
    ContextSegment,
    ContextSegmentType,
    RepairContextPack,
    RepairContextStatus,
    SecretSanitizer,
)
from app.repositories.failure_repository import FailureRepository
from app.repositories.models.workflow import MigrationRunModel
from app.repositories.repair_context_repository import RepairContextRepository
from app.repositories.session import session_scope
from app.services.repair_context_builder import RepairContextPackBuilder
from app.state.transition_service import StateTransitionService, TransitionError

router = APIRouter(prefix="/runs", tags=["repair-context"])
_repo = RepairContextRepository()
_failure_repo = FailureRepository()


# ---------------------------------------------------------------------------
# Request / response DTOs
# ---------------------------------------------------------------------------


class WorkspaceFileDto(BaseModel):
    """A single workspace file to include in the context pack."""

    file_path: str = Field(min_length=1, max_length=1024)
    content: str = Field(min_length=1, max_length=16000)


class PriorAttemptDto(BaseModel):
    """A prior repair attempt summary."""

    attempt_number: int = Field(ge=1)
    diagnosis: str = Field(default="", max_length=16000)
    summary: str = Field(default="", max_length=16000)


class BuildRepairContextRequest(BaseModel):
    """Request body for building a repair context pack."""

    failure_id: str = Field(min_length=1, max_length=128)
    stage_id: str = Field(min_length=1, max_length=64)
    repair_attempt: int = Field(default=1, ge=1)
    workspace_files: list[WorkspaceFileDto] = Field(default_factory=list, max_length=50)
    prior_attempts: list[PriorAttemptDto] = Field(default_factory=list, max_length=10)
    token_budget: int | None = Field(default=None, ge=1, le=32000)
    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_state_version: int = Field(default=1, ge=1)
    actor: str = "system"


class ContextSegmentDto(BaseModel):
    """Serialised context segment for API responses."""

    segment_type: str
    file_path: str | None = None
    content: str = ""
    reason: str = ""
    checksum: str = ""
    redacted: bool = False
    line_start: int | None = None
    line_end: int | None = None


class RepairContextResponse(BaseModel):
    """Response model for a RepairContextPack record."""

    context_pack_id: str
    run_id: str
    failure_id: str
    stage_id: str
    repair_attempt: int
    workspace_fingerprint: str
    selection_policy_version: str
    sanitization_checksum: str
    content_checksum: str
    token_budget: int | None = None
    status: str
    segments: list[ContextSegmentDto] = Field(default_factory=list)
    idempotent_replay: bool = False
    event_sequence: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_failure_evidence(session, run_id: str, failure_id: str) -> FailureEvidence | None:
    """Load a stored FailureEvidence from the database and reconstruct the domain object."""
    persisted = _failure_repo.get_failure(session, run_id, failure_id)
    if persisted is None:
        return None
    parsed: dict[str, Any] = json.loads(persisted.failure_json)
    # Reconstruct FailureEvidence from the stored JSON
    from app.domain.failure import FailureDiagnostic, FailureEvidence, FailureOrigin, FailureStatus

    diagnostics = [
        FailureDiagnostic(
            message=d.get("message", ""),
            code=d.get("code"),
            file_path=d.get("file_path"),
            line_number=d.get("line_number"),
            column=d.get("column"),
            severity=d.get("severity", "error"),
            parser_type=d.get("parser_type", "generic"),
            parser_confidence=d.get("parser_confidence", 1.0),
        )
        for d in parsed.get("diagnostics", [])
    ]
    return FailureEvidence(
        failure_id=persisted.id,
        run_id=persisted.run_id,
        stage_id=persisted.stage_id or "",
        execution_id=persisted.execution_id or "",
        failure_fingerprint=persisted.failure_fingerprint,
        origin=FailureOrigin(parsed.get("origin", "unknown_origin")),
        diagnostics=diagnostics,
        workspace_fingerprint=persisted.workspace_fingerprint,
        status=FailureStatus(persisted.status),
    )


def _build_context_pack(
    failure_evidence: FailureEvidence,
    workspace_files: list[dict],
    prior_attempts: list[dict] | None = None,
    token_budget: int | None = None,
) -> RepairContextPack:
    """Run the RepairContextPackBuilder pipeline to produce a context pack."""
    builder = RepairContextPackBuilder(
        sanitizer=SecretSanitizer(),
        budget_tracker=ContextBudgetTracker(max_tokens=token_budget or 32000),
    )
    return builder.build(
        failure_evidence=failure_evidence,
        workspace_files=workspace_files,
        prior_attempts=prior_attempts or [],
        token_budget=token_budget,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{run_id}/failures/{failure_id}/repair-context", status_code=201, response_model=None)
def build_repair_context(
    run_id: str,
    failure_id: str,
    body: BuildRepairContextRequest,
    http_request: Request,
):
    """Accept failure evidence + workspace files, build context pack, persist, emit events.

    Validates the run exists, reconstructs failure evidence from the store,
    builds a RepairContextPack through the RepairContextPackBuilder pipeline,
    persists with idempotency protection, emits REPAIR_CONTEXT_CREATED or
    REPAIR_CONTEXT_BLOCKED, and returns the stored context pack.
    """
    with session_scope() as session:
        # 1. Validate the run exists
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            return error_response(
                http_request,
                status_code=404,
                error_code="RUN_NOT_FOUND",
                message=f"Run {run_id} does not exist.",
            )

        # 2. Load failure evidence
        failure_evidence = _load_failure_evidence(session, run_id, failure_id)
        if failure_evidence is None:
            return error_response(
                http_request,
                status_code=404,
                error_code="FAILURE_NOT_FOUND",
                message=f"Failure {failure_id} not found in run {run_id}.",
            )

        # 3. Build context pack
        workspace_files = [
            {"path": wf.file_path, "content": wf.content}
            for wf in body.workspace_files
        ]
        prior_attempts = [
            {
                "attempt_number": pa.attempt_number,
                "diagnosis": pa.diagnosis,
                "summary": pa.summary,
            }
            for pa in body.prior_attempts
        ]

        try:
            context_pack = _build_context_pack(
                failure_evidence=failure_evidence,
                workspace_files=workspace_files,
                prior_attempts=prior_attempts,
                token_budget=body.token_budget,
            )
        except ValueError as exc:
            return error_response(
                http_request,
                status_code=422,
                error_code="BUILD_FAILED",
                message=f"Repair context pack builder failed: {exc}",
            )

        # 4. Persist with idempotency protection
        try:
            persisted = _repo.save_context_pack(
                session,
                context_pack,
                body.idempotency_key,
                body.expected_state_version,
            )
        except Exception as exc:
            return error_response(
                http_request,
                status_code=409,
                error_code="PERSISTENCE_FAILED",
                message=f"Failed to persist repair context pack: {exc}",
            )

        # 5. Determine event type based on status
        is_blocked = context_pack.status == RepairContextStatus.INSUFFICIENT
        event_type = (
            WorkflowEventType.REPAIR_CONTEXT_BLOCKED
            if is_blocked
            else WorkflowEventType.REPAIR_CONTEXT_CREATED
        )
        idem_suffix = "REPAIR_CONTEXT_BLOCKED" if is_blocked else "REPAIR_CONTEXT_CREATED"

        # 6. Emit event via transition service
        transition_svc = StateTransitionService(session)
        event_sequence = 0
        try:
            result = transition_svc.append_audit_event(
                run_id=run_id,
                idempotency_key=f"{body.idempotency_key}:{idem_suffix}",
                event_type=event_type,
                actor=body.actor,
                reason=f"Repair context {'blocked' if is_blocked else 'created'} for failure {failure_id}",
                occurred_at=datetime.now(UTC),
                payload={
                    "context_pack_id": context_pack.context_pack_id,
                    "failure_id": failure_id,
                    "status": context_pack.status.value,
                    "segment_count": len(context_pack.segments),
                    "token_budget": body.token_budget,
                },
            )
            event_sequence = result.event_sequence
        except TransitionError as exc:
            return error_response(
                http_request,
                status_code=409,
                error_code="TRANSITION_FAILED",
                message=f"Event emission failed: {exc}",
            )

    # 7. Build response
    return RepairContextResponse(
        context_pack_id=context_pack.context_pack_id,
        run_id=run_id,
        failure_id=context_pack.failure_id,
        stage_id=context_pack.stage_id,
        repair_attempt=context_pack.repair_attempt,
        workspace_fingerprint=context_pack.workspace_fingerprint,
        selection_policy_version=context_pack.selection_policy_version,
        sanitization_checksum=context_pack.sanitization_checksum,
        content_checksum=context_pack.content_checksum,
        token_budget=context_pack.token_budget,
        status=context_pack.status.value,
        segments=[
            ContextSegmentDto(
                segment_type=s.segment_type.value,
                file_path=s.file_path,
                content=s.content,
                reason=s.reason,
                checksum=s.checksum,
                redacted=s.redacted,
                line_start=s.line_start,
                line_end=s.line_end,
            )
            for s in context_pack.segments
        ],
        idempotent_replay=False,
        event_sequence=event_sequence,
    )


@router.get("/{run_id}/repair-contexts/{context_id}", response_model=None)
def get_repair_context(
    run_id: str,
    context_id: str,
    http_request: Request,
):
    """Retrieve a stored repair context pack by its ID."""
    with session_scope() as session:
        persisted = _repo.get_context_pack(session, run_id, context_id)
        if persisted is None:
            return error_response(
                http_request,
                status_code=404,
                error_code="CONTEXT_NOT_FOUND",
                message=f"Repair context {context_id} not found in run {run_id}.",
            )

    # Reconstruct segments from stored context_json
    parsed: dict[str, Any] = json.loads(persisted.context_json)
    segments = [
        ContextSegmentDto(
            segment_type=s.get("segment_type", ""),
            file_path=s.get("file_path"),
            content=s.get("content", ""),
            reason=s.get("reason", ""),
            checksum=s.get("checksum", ""),
            redacted=s.get("redacted", False),
            line_start=s.get("line_start"),
            line_end=s.get("line_end"),
        )
        for s in parsed.get("segments", [])
    ]

    return RepairContextResponse(
        context_pack_id=persisted.id,
        run_id=persisted.run_id,
        failure_id=persisted.failure_id,
        stage_id=persisted.stage_id,
        repair_attempt=persisted.repair_attempt,
        workspace_fingerprint=persisted.workspace_fingerprint,
        selection_policy_version=persisted.selection_policy_version,
        sanitization_checksum=persisted.sanitization_checksum,
        content_checksum=persisted.content_checksum,
        token_budget=persisted.token_budget,
        status=persisted.status,
        segments=segments,
    )
