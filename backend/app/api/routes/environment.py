"""Environment readiness diagnostics API."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.domain.system import EnvironmentCapabilityResult, RefreshEnvironmentRequest
from app.services.environment_diagnostics_application_service import (
    EnvironmentDiagnosticsApplicationService,
)

router = APIRouter(prefix="/environment", tags=["environment"])


def get_environment_service() -> EnvironmentDiagnosticsApplicationService:
    return EnvironmentDiagnosticsApplicationService(get_settings())


@router.get("/diagnostics", response_model=EnvironmentCapabilityResult)
def read_environment_diagnostics(
    service: EnvironmentDiagnosticsApplicationService = Depends(get_environment_service),
) -> EnvironmentCapabilityResult:
    result = service.latest()
    if result is None:
        raise HTTPException(status_code=404, detail="Environment diagnostics have not been refreshed")
    return result


@router.post("/refresh", response_model=EnvironmentCapabilityResult)
def refresh_environment(
    request: RefreshEnvironmentRequest,
    service: EnvironmentDiagnosticsApplicationService = Depends(get_environment_service),
) -> EnvironmentCapabilityResult:
    return service.refresh(request)