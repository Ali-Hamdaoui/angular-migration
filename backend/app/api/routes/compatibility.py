"""Versioned feasibility and G05 API surface for S2-F05."""

from fastapi import APIRouter, Depends, Request

from app.api.authentication import authenticated_actor
from app.api.compatibility_contracts import FeasibilityCreateRequest, FeasibilityResolveActionRequest, FeasibilityResponse, G05DecisionRequest, G05DecisionResponse, PlanningCommandResponse
from app.api.errors import error_response
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.compatibility_application_service import CompatibilityResolver
from app.services.compatibility_evidence_application_service import CompatibilityEvidenceApplicationService, CompatibilityEvidenceError
from app.services.planning_job_service import enqueue_planning_job
from app.repositories.session import session_scope
from app.orchestration.planning import dispatch_planning_job

router = APIRouter(tags=["feasibility"])


def get_service() -> CompatibilityEvidenceApplicationService:
    return CompatibilityEvidenceApplicationService(resolver=CompatibilityResolver(CompatibilityCatalogueProvider().load()))


@router.post("/runs/{run_id}/feasibility/actions/resolve", response_model=PlanningCommandResponse, status_code=202)
def queue_feasibility_resolution(run_id: str, payload: FeasibilityResolveActionRequest, request: Request, actor: str = Depends(authenticated_actor)):
    try:
        result = enqueue_planning_job(run_id, actor=actor, expected_state_version=payload.expected_state_version, idempotency_key=payload.idempotency_key)
        dispatch_planning_job(run_id, worker_id="feasibility-command")
        return result
    except ValueError as error:
        code = str(error)
        status = 404 if code == "RUN_NOT_FOUND" else 403 if code == "RUN_NOT_AUTHORIZED" else 409
        return error_response(request, status_code=status, error_code=code, message="The feasibility planning command could not be queued.")


def _error(request: Request, error: CompatibilityEvidenceError):
    return error_response(request, status_code=error.status_code, error_code=error.code, message=error.message)


@router.post("/runs/{run_id}/feasibility", response_model=FeasibilityResponse)
def resolve_feasibility(run_id: str, payload: FeasibilityCreateRequest, request: Request, actor: str = Depends(authenticated_actor), service: CompatibilityEvidenceApplicationService = Depends(get_service)):
    try:
        return service.resolve(run_id, payload, actor)
    except CompatibilityEvidenceError as error:
        return _error(request, error)


@router.get("/runs/{run_id}/feasibility", response_model=FeasibilityResponse)
def get_feasibility(run_id: str, request: Request, actor: str = Depends(authenticated_actor), service: CompatibilityEvidenceApplicationService = Depends(get_service)):
    try:
        result = service.get(run_id, actor)
        if result is None:
            return error_response(request, status_code=404, error_code="FEASIBILITY_NOT_FOUND", message="Feasibility evidence was not found.")
        return result
    except CompatibilityEvidenceError as error:
        return _error(request, error)


@router.post("/runs/{run_id}/feasibility/reconcile-artifacts")
def reconcile_feasibility_artifacts(run_id: str, request: Request, actor: str = Depends(authenticated_actor), service: CompatibilityEvidenceApplicationService = Depends(get_service)):
    try:
        return service.reconcile_orphans(run_id, actor)
    except CompatibilityEvidenceError as error:
        return _error(request, error)


@router.post("/runs/{run_id}/approvals/G05/decisions", response_model=G05DecisionResponse)
def decide_g05(run_id: str, payload: G05DecisionRequest, request: Request, actor: str = Depends(authenticated_actor), service: CompatibilityEvidenceApplicationService = Depends(get_service)):
    try:
        result = service.decide_g05(run_id, payload, actor)
        if getattr(result, "accepted", result.get("accepted", False) if isinstance(result, dict) else False):
            from app.orchestration.planning import dispatch_after_g05
            dispatch_after_g05(run_id, scope=getattr(service, "_scope", None) or session_scope)
        return result
    except CompatibilityEvidenceError as error:
        return _error(request, error)
