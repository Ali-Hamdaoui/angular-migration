from fastapi import APIRouter
from app.domain.system import HealthResponse
from app.services.system_service import get_health_status
router = APIRouter(tags=["system"])

@router.get("/health", response_model=HealthResponse, summary="Read service health")
def read_health() -> HealthResponse:
    return get_health_status()
