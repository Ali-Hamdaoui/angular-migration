from fastapi import APIRouter, Depends, HTTPException

from app.api.baseline_repair_contracts import BaselineRepairRequest, BaselineRepairResponse
from app.services.baseline_repair_application_service import BaselineRepairApplicationError, BaselineRepairApplicationService

router = APIRouter(prefix="/runs", tags=["baseline-repair"])


def get_service():
    return BaselineRepairApplicationService()


@router.post("/{run_id}/baseline/repairs", response_model=BaselineRepairResponse)
def apply_baseline_repair(run_id: str, request: BaselineRepairRequest, service=Depends(get_service)):
    try:
        return service.apply(run_id, request)
    except BaselineRepairApplicationError as error:
        raise HTTPException(status_code=error.status_code, detail={"error_code": error.code, "message": error.message}) from error
