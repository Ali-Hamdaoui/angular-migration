"""Versioned feasibility and G05 API surface for S2-F05."""

from fastapi import APIRouter, Depends, Request

from app.api.authentication import authenticated_actor
from app.api.compatibility_contracts import FeasibilityCreateRequest, FeasibilityResponse, G05DecisionRequest, G05DecisionResponse
from app.api.errors import error_response
from app.domain.compatibility import CompatibilityCatalogue, CompatibilityCatalogueEntry
from app.services.compatibility_application_service import CompatibilityResolver
from app.services.compatibility_evidence_application_service import CompatibilityEvidenceApplicationService, CompatibilityEvidenceError

router = APIRouter(tags=["feasibility"])


def default_catalogue() -> CompatibilityCatalogue:
    entries = tuple(
        CompatibilityCatalogueEntry(
            stage_id=f"angular-{major}-to-{major + 1}",
            source_family=f"angular-{major}.x",
            target_family=f"angular-{major + 1}.x",
            target_angular_exact=f"{major + 1}.0.0",
            target_cli_exact=f"{major + 1}.0.0",
            node_major=20,
            npm_major=10,
            node_exact="20.11.1",
            npm_exact="10.2.4",
            cli_exact=f"{major + 1}.0.0",
            support_level="historical_experimental",
            fixture_status="incomplete",
            validation_policy_id="angular-stage-standard-v2",
            known_risks=("historical_fixture_evidence_incomplete",),
        )
        for major in range(18, 21)
    )
    return CompatibilityCatalogue.build("catalog-v1", entries)


def get_service() -> CompatibilityEvidenceApplicationService:
    return CompatibilityEvidenceApplicationService(resolver=CompatibilityResolver(default_catalogue()))


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
            dispatch_after_g05(run_id)
        return result
    except CompatibilityEvidenceError as error:
        return _error(request, error)
