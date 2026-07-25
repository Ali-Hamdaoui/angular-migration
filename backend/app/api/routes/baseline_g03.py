from fastapi import APIRouter, Depends, HTTPException
from app.api.baseline_g03_contracts import BaselineQualifyRequest,G03DecisionRequest,BaselineAssessmentResponse
from app.services.baseline_g03_application_service import BaselineG03ApplicationError,BaselineG03ApplicationService
router=APIRouter(prefix="/runs",tags=["baseline-g03"])
def service(): return BaselineG03ApplicationService()
def fail(e): raise HTTPException(status_code=e.status_code,detail={"error_code":e.code,"message":e.message,"details":getattr(e,"details",{})})
@router.get("/{run_id}/baseline/summary",response_model=BaselineAssessmentResponse)
def summary(run_id:str,s:BaselineG03ApplicationService=Depends(service)):
    result=s.get(run_id)
    if result is None: raise HTTPException(404,detail={"error_code":"BASELINE_SUMMARY_NOT_FOUND","message":"Baseline qualification has not been recorded."})
    return result
@router.post("/{run_id}/baseline/qualify",response_model=BaselineAssessmentResponse)
def qualify(run_id:str,request:BaselineQualifyRequest,s:BaselineG03ApplicationService=Depends(service)):
    try:return s.qualify(run_id,request)
    except BaselineG03ApplicationError as e:fail(e)
    except Exception as e:
        # Qualification is fail-closed. Keep implementation details out of the
        # normal response while returning a stable, actionable error contract.
        error = BaselineG03ApplicationError("BASELINE_QUALIFICATION_INTERNAL_ERROR", "Baseline qualification failed internally. Retry only after reviewing backend diagnostics.", 500)
        error.details = {"failed_component": "BaselineG03ApplicationService", "failed_operation": "qualify", "exception_type": type(e).__name__, "retryable": False}
        fail(error)
@router.post("/{run_id}/approvals/G03/decisions",response_model=BaselineAssessmentResponse)
def decide(run_id:str,request:G03DecisionRequest,s:BaselineG03ApplicationService=Depends(service)):
    try:return s.decide(run_id,request)
    except BaselineG03ApplicationError as e:fail(e)
