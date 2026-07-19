"""S2-F07-I02 plan revision, explanation, and G06 API routes."""

from fastapi import APIRouter, Depends, Request

from app.api.authentication import authenticated_actor
from app.api.errors import error_response
from app.api.planning_review_contracts import (
    G06DecisionApiRequest,
    G06DecisionResponse,
    PlanReviewResponse,
    PlanRevisionApiRequest,
    PlanningExplanationApiRequest,
)
from app.services.planning_review_evidence_application_service import (
    PlanningReviewEvidenceApplicationService,
    PlanningReviewEvidenceError,
)

router = APIRouter(tags=["planning-review"])


def get_service() -> PlanningReviewEvidenceApplicationService:
    return PlanningReviewEvidenceApplicationService()


def _error(request: Request, error: PlanningReviewEvidenceError):
    return error_response(request, status_code=error.status_code, error_code=error.code, message=error.message)


@router.post("/runs/{run_id}/plan/revisions", response_model=PlanReviewResponse)
def revise(
    run_id: str,
    payload: PlanRevisionApiRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
    service: PlanningReviewEvidenceApplicationService = Depends(get_service),
):
    try:
        correlation_id = payload.correlation_id or request.headers.get("x-correlation-id")
        return service.revise(run_id, payload.model_copy(update={"correlation_id": correlation_id}), actor)
    except PlanningReviewEvidenceError as error:
        return _error(request, error)


@router.post("/runs/{run_id}/plan/explanation", response_model=PlanReviewResponse)
def explain(
    run_id: str,
    payload: PlanningExplanationApiRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
    service: PlanningReviewEvidenceApplicationService = Depends(get_service),
):
    try:
        correlation_id = payload.correlation_id or request.headers.get("x-correlation-id")
        return service.explain(run_id, payload.model_copy(update={"correlation_id": correlation_id}), actor)
    except PlanningReviewEvidenceError as error:
        return _error(request, error)


@router.post("/runs/{run_id}/approvals/G06/decisions", response_model=G06DecisionResponse)
def decide_g06(
    run_id: str,
    payload: G06DecisionApiRequest,
    request: Request,
    actor: str = Depends(authenticated_actor),
    service: PlanningReviewEvidenceApplicationService = Depends(get_service),
):
    try:
        correlation_id = payload.correlation_id or request.headers.get("x-correlation-id")
        return service.decide_g06(run_id, payload.model_copy(update={"correlation_id": correlation_id}), actor)
    except PlanningReviewEvidenceError as error:
        return _error(request, error)


@router.get("/runs/{run_id}/plan/review", response_model=PlanReviewResponse)
def get_review(
    run_id: str,
    request: Request,
    actor: str = Depends(authenticated_actor),
    service: PlanningReviewEvidenceApplicationService = Depends(get_service),
):
    try:
        result = service.get(run_id, actor)
        if result is None:
            return error_response(
                request,
                status_code=404,
                error_code="PLANNING_REVIEW_NOT_FOUND",
                message="Planning review evidence was not found.",
            )
        return result
    except PlanningReviewEvidenceError as error:
        return _error(request, error)
