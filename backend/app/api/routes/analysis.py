from fastapi import APIRouter, Depends, Request

from app.api.analysis_contracts import AnalysisCreateRequest, AnalysisResponse, G04DecisionApiRequest, G04DecisionResponse
from app.api.authentication import authenticated_actor
from app.api.errors import error_response
from app.services.analysis_evidence_application_service import AnalysisEvidenceApplicationService, AnalysisEvidenceError

router = APIRouter(tags=["analysis"])


def get_service() -> AnalysisEvidenceApplicationService:
    return AnalysisEvidenceApplicationService()


def _error(request: Request, error: AnalysisEvidenceError):
    return error_response(request, status_code=error.status_code, error_code=error.code, message=error.message)


@router.post("/runs/{run_id}/analysis", response_model=AnalysisResponse)
def generate(run_id: str, payload: AnalysisCreateRequest, request: Request, actor: str = Depends(authenticated_actor), service: AnalysisEvidenceApplicationService = Depends(get_service)):
    try:
        return service.generate(run_id, payload, actor)
    except AnalysisEvidenceError as error:
        return _error(request, error)


@router.get("/runs/{run_id}/analysis", response_model=AnalysisResponse)
def get_analysis(run_id: str, request: Request, actor: str = Depends(authenticated_actor), service: AnalysisEvidenceApplicationService = Depends(get_service)):
    try:
        result = service.get(run_id, actor)
        if result is None:
            return error_response(request, status_code=404, error_code="ANALYSIS_NOT_FOUND", message="Analysis evidence was not found.")
        return result
    except AnalysisEvidenceError as error:
        return _error(request, error)


@router.post("/runs/{run_id}/approvals/G04/decisions", response_model=G04DecisionResponse)
def decide_g04(run_id: str, payload: G04DecisionApiRequest, request: Request, actor: str = Depends(authenticated_actor), service: AnalysisEvidenceApplicationService = Depends(get_service)):
    try:
        return service.decide_g04(run_id, payload, actor)
    except AnalysisEvidenceError as error:
        return _error(request, error)
