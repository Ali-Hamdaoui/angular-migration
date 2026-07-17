from fastapi import APIRouter,Depends,HTTPException
from app.api.discovery_contracts import DiscoveryCaptureRequest,DiscoveryEvidenceResponse
from app.services.discovery_evidence_application_service import DiscoveryEvidenceApplicationService,DiscoveryEvidenceError
router=APIRouter(prefix='/runs',tags=['discovery'])
def service(): return DiscoveryEvidenceApplicationService()
@router.post('/{run_id}/discovery',response_model=DiscoveryEvidenceResponse)
def capture(run_id:str,request:DiscoveryCaptureRequest,s=Depends(service)):
 try:return s.capture(run_id,request)
 except DiscoveryEvidenceError as e: raise HTTPException(e.status_code,detail={'error_code':e.code,'message':e.message})
@router.get('/{run_id}/discovery',response_model=DiscoveryEvidenceResponse)
def get(run_id:str,s=Depends(service)):
 r=s.get(run_id)
 if not r: raise HTTPException(404,detail={'error_code':'DISCOVERY_NOT_FOUND','message':'Discovery evidence was not found.'})
 return r
