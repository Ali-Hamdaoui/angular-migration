"""Persisted MigrationPlan and StageExecutionPlan API surface for S2-F06-I02."""

from fastapi import APIRouter, Depends, Request

from app.api.authentication import authenticated_actor
from app.api.errors import error_response
from app.api.planning_contracts import PlanCreateRequest, PlanResponse
from app.services.planning_evidence_application_service import PlanningEvidenceApplicationService, PlanningEvidenceError

router = APIRouter(tags=["plans"])


def get_service() -> PlanningEvidenceApplicationService:
    return PlanningEvidenceApplicationService()


def _error(request: Request, error: PlanningEvidenceError):
    return error_response(request, status_code=error.status_code, error_code=error.code, message=error.message)


@router.post("/runs/{run_id}/plans", response_model=PlanResponse)
def create_plan(run_id: str, payload: PlanCreateRequest, request: Request, actor: str = Depends(authenticated_actor), service: PlanningEvidenceApplicationService = Depends(get_service)):
    try:
        correlation_id = payload.correlation_id or request.headers.get("x-correlation-id")
        return service.create(run_id, payload.model_copy(update={"correlation_id": correlation_id}), actor)
    except PlanningEvidenceError as error:
        return _error(request, error)


@router.get("/runs/{run_id}/plan", response_model=PlanResponse)
def get_plan(run_id: str, request: Request, actor: str = Depends(authenticated_actor), service: PlanningEvidenceApplicationService = Depends(get_service)):
    try:
        result = service.get_plan(run_id, actor)
        if result is None:
            return error_response(request, status_code=404, error_code="PLAN_NOT_FOUND", message="Migration plan evidence was not found.")
        return result
    except PlanningEvidenceError as error:
        return _error(request, error)


@router.get("/runs/{run_id}/stages/{stage_id}/plan", response_model=PlanResponse)
def get_stage_plan(run_id: str, stage_id: str, request: Request, actor: str = Depends(authenticated_actor), service: PlanningEvidenceApplicationService = Depends(get_service)):
    try:
        result = service.get_stage_plan(run_id, stage_id, actor)
        if result is None:
            return error_response(request, status_code=404, error_code="STAGE_PLAN_NOT_FOUND", message="Stage execution plan evidence was not found.")
        return result
    except PlanningEvidenceError as error:
        return _error(request, error)
