from fastapi import APIRouter, Depends, Request
from app.api.discovery_contracts import DiscoveryCaptureRequest,DiscoveryEvidenceResponse
from app.api.errors import error_response
from app.services.discovery_evidence_application_service import DiscoveryEvidenceApplicationService,DiscoveryEvidenceError
router=APIRouter(prefix='/runs',tags=['discovery'])
def service(): return DiscoveryEvidenceApplicationService()
@router.post('/{run_id}/discovery',response_model=DiscoveryEvidenceResponse)
def capture(run_id: str, request: DiscoveryCaptureRequest, http_request: Request, s=Depends(service)):
 try:
  return s.capture(run_id, request)
 except DiscoveryEvidenceError as error:
  return error_response(http_request, status_code=error.status_code, error_code=error.code, message=error.message)
@router.get('/{run_id}/discovery',response_model=DiscoveryEvidenceResponse)
def get(run_id: str, http_request: Request, s=Depends(service)):
 r=s.get(run_id)
 if not r:
  return error_response(http_request, status_code=404, error_code='DISCOVERY_NOT_FOUND', message='Discovery evidence was not found.')
 return r
