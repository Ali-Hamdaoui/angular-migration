"""Migration read-model endpoints; no workflow logic lives in this router."""

from fastapi import APIRouter

from app.domain.contracts import MigrationRunDto
from app.services.mock_migration_service import get_mock_migration_run

router = APIRouter(prefix="/migrations", tags=["migrations"])


@router.get("/mock-state", response_model=MigrationRunDto, summary="Read mock migration state")
def read_mock_migration_state() -> MigrationRunDto:
    return get_mock_migration_run()