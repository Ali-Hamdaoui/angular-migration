"""G14 delivery-candidate endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from app.api.delivery_contracts import DeliveryRequest, DeliveryResponse, G14DecisionRequest
from app.services.delivery_application_service import DeliveryApplicationService, DeliveryApplicationError

router = APIRouter(prefix="/runs", tags=["delivery"])


def get_service() -> DeliveryApplicationService:
    return DeliveryApplicationService()


@router.get("/{run_id}/approvals/G14", response_model=DeliveryResponse)
def inspect_delivery(run_id: str, service: DeliveryApplicationService = Depends(get_service)):
    result = service.get(run_id, "G14")
    if result is None:
        raise HTTPException(status_code=404, detail="Delivery record not found")
    return result


@router.post("/{run_id}/delivery-candidate", status_code=201, response_model=None)
def create_delivery(run_id: str, request: DeliveryRequest, service: DeliveryApplicationService = Depends(get_service)):
    try:
        return service.initialize(run_id, request)
    except DeliveryApplicationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"error_code": e.code, "message": e.message},
        ) from e


@router.post("/{run_id}/approvals/G14/decisions", response_model=None)
def decide_g14(run_id: str, request: G14DecisionRequest, service: DeliveryApplicationService = Depends(get_service)):
    if request.gate_id != "G14":
        raise HTTPException(status_code=400, detail="gate_id mismatch")
    try:
        return service.decide(run_id, request)
    except DeliveryApplicationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"error_code": e.code, "message": e.message},
        ) from e
