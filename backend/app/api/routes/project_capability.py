"""Project capability API (V2 F13)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.project_capability_contracts import (
    CapabilitySnapshotDto,
    CapabilitySnapshotListDto,
    DeriveCapabilitiesRequest,
    ProjectCapabilityDto,
)
from app.services.project_capability_service import ProjectCapabilityError, ProjectCapabilityService

router = APIRouter(tags=["project-capability"])


def get_capability_service() -> ProjectCapabilityService:
    return ProjectCapabilityService()


def _raise(error: ProjectCapabilityError) -> None:
    raise HTTPException(status_code=404 if error.code == "RUN_NOT_FOUND" else 422,
                        detail={"error_code": error.code, "message": error.message})


def _capability_dto(c) -> ProjectCapabilityDto:
    return ProjectCapabilityDto(key=c["key"] if isinstance(c, dict) else c.key, value=c["value"] if isinstance(c, dict) else c.value, detail=c.get("detail", "") if isinstance(c, dict) else c.detail)


def _snapshot_dto(snapshot) -> CapabilitySnapshotDto:
    return CapabilitySnapshotDto(
        run_id=snapshot.run_id, stage_id=snapshot.stage_id, source_root=snapshot.source_root,
        angular_major=snapshot.angular_major,
        capabilities=[_capability_dto(c) for c in snapshot.capabilities],
        checksum=snapshot.checksum,
    )


def _record_dto(row) -> CapabilitySnapshotDto:
    return CapabilitySnapshotDto(
        run_id=row.run_id, stage_id=row.stage_id, source_root=row.source_root,
        angular_major=row.angular_major,
        capabilities=[ProjectCapabilityDto(key=c["key"], value=c["value"], detail=c.get("detail", "")) for c in row.capabilities],
        checksum=row.checksum,
    )


@router.post("/capabilities/derive", response_model=CapabilitySnapshotDto)
def derive_capabilities(
    request: DeriveCapabilitiesRequest,
    service: ProjectCapabilityService = Depends(get_capability_service),
) -> CapabilitySnapshotDto:
    snapshot = service.snapshot(request.run_id, Path(request.source_root), request.stage_id)
    return _snapshot_dto(snapshot)


@router.post("/runs/{run_id}/capabilities", response_model=CapabilitySnapshotDto)
def snapshot_run_capabilities(
    run_id: str,
    request: DeriveCapabilitiesRequest,
    service: ProjectCapabilityService = Depends(get_capability_service),
) -> CapabilitySnapshotDto:
    try:
        snapshot = service.snapshot(run_id, Path(request.source_root), request.stage_id)
    except ProjectCapabilityError as error:
        _raise(error)
    return _snapshot_dto(snapshot)


@router.get("/runs/{run_id}/capabilities", response_model=CapabilitySnapshotListDto)
def list_run_capabilities(
    run_id: str,
    service: ProjectCapabilityService = Depends(get_capability_service),
) -> CapabilitySnapshotListDto:
    return CapabilitySnapshotListDto(snapshots=[_record_dto(row) for row in service.list_run_snapshots(run_id)])
