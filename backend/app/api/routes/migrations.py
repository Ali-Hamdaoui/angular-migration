"""Read-only migration endpoints; no workflow logic lives in this router."""
from fastapi import APIRouter
from app.domain.mock_migration import MockMigrationRunResponse
from app.services.mock_migration_service import get_mock_migration_run
router = APIRouter(prefix="/migrations", tags=["migrations"])

@router.get("/mock-state", response_model=MockMigrationRunResponse, summary="Read mock migration state")
def read_mock_migration_state() -> MockMigrationRunResponse:
    return get_mock_migration_run()
