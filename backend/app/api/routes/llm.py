import inspect

from fastapi import APIRouter, Depends, Request

from app.api.errors import error_response
from app.api.authentication import authenticated_actor
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
def smoke(payload: LlmSmokeRequest, request: Request, actor: str = Depends(authenticated_actor), service: LlmEvidenceApplicationService = Depends(get_service)):
    try:
        if request.headers.get('x-correlation-id') and not payload.correlation_id:
            payload = payload.model_copy(update={'correlation_id': request.headers['x-correlation-id']})
        if 'actor' in inspect.signature(service.smoke).parameters:
            return service.smoke(payload, actor=actor)
        return service.smoke(payload)
    except LlmEvidenceError as error:
        return _error(request, error)


@router.get('/runs/{run_id}/llm/activity', response_model=LlmActivityResponse)
def activity(run_id: str, request: Request, actor: str = Depends(authenticated_actor), service: LlmEvidenceApplicationService = Depends(get_service)):
    try:
        if 'actor' in inspect.signature(service.activity).parameters:
            return service.activity(run_id, actor=actor)
        return service.activity(run_id)
    except LlmEvidenceError as error:
        return _error(request, error)


@router.get('/runs/{run_id}/usage', response_model=LlmUsageResponse)
def usage(run_id: str, request: Request, actor: str = Depends(authenticated_actor), service: LlmEvidenceApplicationService = Depends(get_service)):
    try:
        if 'actor' in inspect.signature(service.usage).parameters:
            return service.usage(run_id, actor=actor)
        return service.usage(run_id)
    except LlmEvidenceError as error:
        return _error(request, error)
