"""Source and target path validation API."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.domain.path_validation import PathValidationRequest, PathValidationResult
from app.services.path_validation_application_service import PathValidationApplicationService

router = APIRouter(prefix="/sources", tags=["sources"])


def get_path_validation_service() -> PathValidationApplicationService:
    return PathValidationApplicationService(get_settings())


@router.post("/validate-paths", response_model=PathValidationResult)
def validate_paths(
    request: PathValidationRequest,
    service: PathValidationApplicationService = Depends(get_path_validation_service),
) -> PathValidationResult:
    return service.validate(request)


@router.get("/path-validations/{validation_id}", response_model=PathValidationResult)
def get_path_validation(
    validation_id: str,
    service: PathValidationApplicationService = Depends(get_path_validation_service),
) -> PathValidationResult:
    result = service.get(validation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Path validation not found")
    return result