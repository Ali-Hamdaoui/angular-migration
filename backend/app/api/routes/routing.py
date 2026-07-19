"""API routes for C-Lite failure routing — classify, retrieve, and retry."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.errors import error_response
from app.domain.contracts import WorkflowEventType
from app.domain.failure import FailureDiagnostic
from app.domain.route import FailureRouteDecision
from app.repositories.models.workflow import MigrationRunModel
from app.repositories.route_repository import RouteRepository
from app.repositories.session import session_scope
from app.services.clite_router import CLiteRouter
from app.state.transition_service import StateTransitionService, TransitionError

router = APIRouter(prefix="/runs", tags=["routing"])
_repo = RouteRepository()
_router = CLiteRouter()


# ---------------------------------------------------------------------------
# Request / response DTOs
# ---------------------------------------------------------------------------


class ClassifyRequest(BaseModel):
    """Request body for classifying failure diagnostics."""

    diagnostics: list[dict[str, Any]] = Field(min_length=1)
    policy_version: str = Field(default="c-lite-v1", min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_state_version: int = Field(default=1, ge=1)
    actor: str = "system"


class FailureDiagnosticDto(BaseModel):
    """Serialised diagnostic entry for requests."""

    message: str
    code: str | None = None
    file_path: str | None = None
    line_number: int | None = None
    column: int | None = None
    severity: str = "error"
    parser_type: str = "generic"
    parser_confidence: float = 1.0


class RouteDecisionResponse(BaseModel):
    """Response model for a single route decision."""

    failure_id: str
    route: str
    policy_version: str
    decision_checksum: str
    actions: list[str] = Field(default_factory=list)
    risk: str
    state_version: int
    idempotency_key: str
    created_at: str


class RetryRequest(BaseModel):
    """Request body for triggering a retry attempt."""

    idempotency_key: str = Field(min_length=1, max_length=128)
    actor: str = "system"


class RetryResponse(BaseModel):
    """Response model for a retry attempt record."""

    attempt_id: str
    failure_id: str
    run_id: str
    attempt_number: int
    route: str
    status: str
    max_retries: int
    created_at: str
    event_sequence: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_diagnostics(raw: list[dict[str, Any]]) -> list[FailureDiagnostic]:
    """Parse raw diagnostic dicts into FailureDiagnostic domain objects."""
    return [FailureDiagnostic(**d) for d in raw]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{run_id}/failures/{failure_id}/classify", status_code=201, response_model=None)
def classify_failure(
    run_id: str,
    failure_id: str,
    body: ClassifyRequest,
    http_request: Request,
) -> JSONResponse | RouteDecisionResponse:
    """Classify failure diagnostics via C-Lite router, persist decision, emit event.

    Accepts parsed diagnostics, runs the CLiteRouter.classify() pipeline,
    stores the resulting FailureRouteDecision, and emits a FAILURE_CLASSIFIED
    workflow event.
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

        # 2. Parse diagnostics
        try:
            diagnostics = _parse_diagnostics(body.diagnostics)
        except Exception as exc:
            return error_response(
                http_request,
                status_code=422,
                error_code="INVALID_DIAGNOSTICS",
                message=f"Failed to parse diagnostics: {exc}",
            )

        # 3. Classify via CLiteRouter
        decision: FailureRouteDecision = _router.classify(
            failure_diagnostics=diagnostics,
            failure_id=failure_id,
            policy_version=body.policy_version,
        )

        # 4. Persist route decision
        try:
            persisted = _repo.save_route_decision(
                session,
                run_id,
                failure_id,
                decision,
                body.idempotency_key,
                body.expected_state_version,
            )
        except Exception as exc:
            return error_response(
                http_request,
                status_code=409,
                error_code="PERSISTENCE_FAILED",
                message=f"Failed to persist route decision: {exc}",
            )

        # 5. Emit FAILURE_CLASSIFIED event
        transition_svc = StateTransitionService(session)
        event_sequence = 0
        try:
            result = transition_svc.append_audit_event(
                run_id=run_id,
                idempotency_key=f"{body.idempotency_key}:FAILURE_CLASSIFIED",
                event_type=WorkflowEventType.FAILURE_CLASSIFIED,
                actor=body.actor,
                reason=f"Failure {failure_id} classified as {decision.route.value}",
                occurred_at=datetime.now(UTC),
                payload={
                    "failure_id": failure_id,
                    "route": decision.route.value,
                    "policy_version": decision.policy_version,
                    "decision_checksum": decision.decision_checksum,
                    "risk": decision.risk,
                    "action_count": len(decision.actions),
                },
            )
            event_sequence = result.event_sequence
        except TransitionError as exc:
            return error_response(
                http_request,
                status_code=409,
                error_code="EVENT_FAILED",
                message=f"Event emission failed: {exc}",
            )

    return RouteDecisionResponse(
        failure_id=persisted.failure_id,
        route=persisted.route,
        policy_version=persisted.policy_version,
        decision_checksum=persisted.decision_checksum,
        actions=persisted.actions,
        risk=persisted.risk,
        state_version=persisted.state_version,
        idempotency_key=persisted.idempotency_key,
        created_at=persisted.created_at.isoformat(),
    )


@router.get("/{run_id}/failures/{failure_id}/route", response_model=None)
def get_route_decision(
    run_id: str,
    failure_id: str,
    http_request: Request,
) -> JSONResponse | RouteDecisionResponse:
    """Return the stored C-Lite route decision for a failure."""
    with session_scope() as session:
        persisted = _repo.get_route_decision(session, run_id, failure_id)
        if persisted is None:
            return error_response(
                http_request,
                status_code=404,
                error_code="ROUTE_NOT_FOUND",
                message=f"No route decision found for failure {failure_id} in run {run_id}.",
            )

    return RouteDecisionResponse(
        failure_id=persisted.failure_id,
        route=persisted.route,
        policy_version=persisted.policy_version,
        decision_checksum=persisted.decision_checksum,
        actions=persisted.actions,
        risk=persisted.risk,
        state_version=persisted.state_version,
        idempotency_key=persisted.idempotency_key,
        created_at=persisted.created_at.isoformat(),
    )


@router.post("/{run_id}/failures/{failure_id}/retry", status_code=201, response_model=None)
def retry_failure(
    run_id: str,
    failure_id: str,
    body: RetryRequest,
    http_request: Request,
) -> JSONResponse | RetryResponse:
    """Check retry policy, record retry attempt, emit EXTERNAL_RETRY_SCHEDULED event.

    Validates the run exists, checks the retry policy (max retries),
    records a new attempt, and emits the EXTERNAL_RETRY_SCHEDULED event.
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

        # 2. Get existing attempts and check retry policy
        existing_attempts = _repo.get_attempts(session, failure_id)
        attempt_number = len(existing_attempts) + 1
        max_retries = _router.max_retries

        if attempt_number > max_retries:
            return error_response(
                http_request,
                status_code=409,
                error_code="MAX_RETRIES_EXCEEDED",
                message=f"Failure {failure_id} has reached max retries ({max_retries}).",
            )

        # 3. Get the route decision for context
        existing_route = _repo.get_route_decision(session, run_id, failure_id)
        route_value = existing_route.route if existing_route else "UNKNOWN_DIAGNOSIS"

        # 4. Persist retry attempt
        try:
            attempt = _repo.save_retry_attempt(
                session,
                run_id,
                failure_id,
                attempt_number,
                route_value,
            )
        except Exception as exc:
            return error_response(
                http_request,
                status_code=409,
                error_code="PERSISTENCE_FAILED",
                message=f"Failed to persist retry attempt: {exc}",
            )

        # 5. Emit EXTERNAL_RETRY_SCHEDULED event
        transition_svc = StateTransitionService(session)
        event_sequence = 0
        try:
            result = transition_svc.append_audit_event(
                run_id=run_id,
                idempotency_key=f"{body.idempotency_key}:EXTERNAL_RETRY_SCHEDULED",
                event_type=WorkflowEventType.EXTERNAL_RETRY_SCHEDULED,
                actor=body.actor,
                reason=f"Retry attempt {attempt_number}/{max_retries} scheduled for failure {failure_id}",
                occurred_at=datetime.now(UTC),
                payload={
                    "failure_id": failure_id,
                    "attempt_number": attempt_number,
                    "max_retries": max_retries,
                    "route": route_value,
                },
            )
            event_sequence = result.event_sequence
        except TransitionError as exc:
            return error_response(
                http_request,
                status_code=409,
                error_code="EVENT_FAILED",
                message=f"Event emission failed: {exc}",
            )

    return RetryResponse(
        attempt_id=attempt.id,
        failure_id=attempt.failure_id,
        run_id=attempt.run_id,
        attempt_number=attempt.attempt_number,
        route=attempt.route,
        status=attempt.status,
        max_retries=attempt.max_retries,
        created_at=attempt.created_at.isoformat(),
        event_sequence=event_sequence,
    )
