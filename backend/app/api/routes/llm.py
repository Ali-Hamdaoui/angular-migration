from fastapi import APIRouter, Depends, Request

from app.api.errors import error_response
from app.api.llm_contracts import LlmActivityResponse, LlmInvocationResponse, LlmReadinessResponse, LlmSmokeRequest, LlmUsageResponse
from app.services.llm_evidence_application_service import LlmEvidenceApplicationService, LlmEvidenceError

router = APIRouter(tags=['llm'])


def get_service() -> LlmEvidenceApplicationService:
    return LlmEvidenceApplicationService()


def _error(request: Request, error: LlmEvidenceError):
    return error_response(request, status_code=error.status_code, error_code=error.code, message=error.message)


@router.get('/llm/readiness', response_model=LlmReadinessResponse)
def readiness(service: LlmEvidenceApplicationService = Depends(get_service)):
    return service.readiness()


@router.post('/llm/smoke', response_model=LlmInvocationResponse)
def smoke(payload: LlmSmokeRequest, request: Request, service: LlmEvidenceApplicationService = Depends(get_service)):
    try:
        return service.smoke(payload)
    except LlmEvidenceError as error:
        return _error(request, error)


@router.get('/runs/{run_id}/llm/activity', response_model=LlmActivityResponse)
def activity(run_id: str, request: Request, service: LlmEvidenceApplicationService = Depends(get_service)):
    try:
        return service.activity(run_id)
    except LlmEvidenceError as error:
        return _error(request, error)


@router.get('/runs/{run_id}/usage', response_model=LlmUsageResponse)
def usage(run_id: str, request: Request, service: LlmEvidenceApplicationService = Depends(get_service)):
    try:
        return service.usage(run_id)
    except LlmEvidenceError as error:
        return _error(request, error)
