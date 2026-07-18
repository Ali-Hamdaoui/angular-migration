"""ExecutionProfile resolution and explicit selection endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from app.api.execution_profile_contracts import ExecutionProfileResolveRequest, ExecutionProfileResponse, ExecutionProfileSelectRequest
from app.services.execution_profile_application_service import ExecutionProfileApplicationError, ExecutionProfileApplicationService
router=APIRouter(prefix="/runs",tags=["execution-profiles"])
def get_execution_profile_service(): return ExecutionProfileApplicationService()
def _raise(error): raise HTTPException(status_code=error.status_code,detail={"error_code":error.code,"message":error.message})
@router.post("/{run_id}/execution-profiles/resolve",response_model=ExecutionProfileResponse)
def resolve_execution_profile(run_id:str,request:ExecutionProfileResolveRequest,service:ExecutionProfileApplicationService=Depends(get_execution_profile_service)):
    try: return service.resolve(run_id,request)
    except ExecutionProfileApplicationError as error: _raise(error)
@router.get("/{run_id}/execution-profiles",response_model=ExecutionProfileResponse)
def list_execution_profiles(run_id:str,service:ExecutionProfileApplicationService=Depends(get_execution_profile_service)):
    result=service.list(run_id)
    if result is None: raise HTTPException(status_code=404,detail={"error_code":"PROFILE_RESOLUTION_NOT_FOUND","message":"Execution profile resolution not found."})
    return result
@router.post("/{run_id}/execution-profiles/{profile_id}/select",response_model=ExecutionProfileResponse)
def select_execution_profile(run_id:str,profile_id:str,request:ExecutionProfileSelectRequest,service:ExecutionProfileApplicationService=Depends(get_execution_profile_service)):
    if request.profile_id != profile_id: raise HTTPException(status_code=400,detail={"error_code":"PROFILE_ID_MISMATCH","message":"profile_id in body does not match path."})
    try: return service.select(run_id,request)
    except ExecutionProfileApplicationError as error: _raise(error)
