"""Source snapshot API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import get_settings
from app.domain.snapshot import CreateSourceSnapshotRequest, SourceSnapshotDto
from app.services.source_snapshot_application_service import (
    SnapshotApplicationError,
    SourceSnapshotApplicationService,
)

router = APIRouter(prefix="/runs", tags=["snapshots"])


def get_snapshot_service() -> SourceSnapshotApplicationService:
    return SourceSnapshotApplicationService(get_settings())


@router.post(
    "/{run_id}/snapshots",
    response_model=SourceSnapshotDto,
    status_code=201,
)
def create_snapshot(
    run_id: str,
    request: CreateSourceSnapshotRequest,
    http_request: Request,
    service: SourceSnapshotApplicationService = Depends(get_snapshot_service),
) -> SourceSnapshotDto:
    try:
        return service.create(run_id, request)
    except SnapshotApplicationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error_code": error.code, "message": error.message},
        ) from error


@router.get(
    "/{run_id}/snapshots/{snapshot_id}",
    response_model=SourceSnapshotDto,
)
def inspect_snapshot(
    run_id: str,
    snapshot_id: str,
    service: SourceSnapshotApplicationService = Depends(get_snapshot_service),
) -> SourceSnapshotDto:
    result = service.get(run_id, snapshot_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Source snapshot not found")
    return result
