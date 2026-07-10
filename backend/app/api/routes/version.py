from fastapi import APIRouter
from app.domain.system import VersionResponse
from app.services.system_service import get_version_info
router = APIRouter(tags=["system"])

@router.get("/version", response_model=VersionResponse, summary="Read application version")
def read_version() -> VersionResponse:
    return get_version_info()
