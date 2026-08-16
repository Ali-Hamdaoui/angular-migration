"""Migration route API (V2 F10)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.migration_route_contracts import (
    ComputeRouteRequest,
    MigrationRouteDto,
    RouteRecordDto,
    RouteRecordListDto,
    RouteStageDto,
)
from app.services.migration_route_service import MigrationRouteError, MigrationRouteService

router = APIRouter(tags=["migration-route"])


def get_route_service() -> MigrationRouteService:
    return MigrationRouteService()


def _raise(error: MigrationRouteError) -> None:
    raise HTTPException(status_code=404 if error.code in {"RUN_NOT_FOUND", "ROUTE_NOT_PERSISTED"} else 422,
                        detail={"error_code": error.code, "message": error.message})


def _route_dto(route) -> MigrationRouteDto:
    return MigrationRouteDto(
        source_major=route.source_major,
        target_major=route.target_major,
        catalogue_version=route.catalogue_version,
        stages=[RouteStageDto(**stage.model_dump()) for stage in route.stages],
        checksum=route.checksum,
    )


def _record_dto(row) -> RouteRecordDto:
    return RouteRecordDto(
        id=row.id, run_id=row.run_id, source_major=row.source_major, target_major=row.target_major,
        catalogue_version=row.catalogue_version, stages=row.stages, checksum=row.checksum,
        actor=row.actor, created_at=row.created_at,
    )


@router.post("/routes/compute", response_model=MigrationRouteDto)
def compute_route(
    request: ComputeRouteRequest,
    service: MigrationRouteService = Depends(get_route_service),
) -> MigrationRouteDto:
    try:
        route = service.compute(request.source_major, request.target_major, request.catalogue_version)
    except MigrationRouteError as error:
        _raise(error)
    return _route_dto(route)


@router.post("/runs/{run_id}/routes/compute", response_model=MigrationRouteDto)
def compute_run_route(
    run_id: str,
    service: MigrationRouteService = Depends(get_route_service),
) -> MigrationRouteDto:
    try:
        route = service.compute_for_run(run_id)
    except MigrationRouteError as error:
        _raise(error)
    return _route_dto(route)


@router.post("/runs/{run_id}/routes", response_model=RouteRecordDto)
def persist_run_route(
    run_id: str,
    service: MigrationRouteService = Depends(get_route_service),
) -> RouteRecordDto:
    try:
        route = service.compute_for_run(run_id)
        record = service.persist(run_id, route, actor="operator")
    except MigrationRouteError as error:
        _raise(error)
    return _record_dto(record)


@router.get("/runs/{run_id}/routes", response_model=RouteRecordDto)
def get_run_route(
    run_id: str,
    service: MigrationRouteService = Depends(get_route_service),
) -> RouteRecordDto:
    record = service.get_run_route(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"error_code": "ROUTE_NOT_PERSISTED", "message": "No route persisted for run."})
    return _record_dto(record)


@router.post("/runs/{run_id}/routes/validate", response_model=MigrationRouteDto)
def validate_run_route(
    run_id: str,
    service: MigrationRouteService = Depends(get_route_service),
) -> MigrationRouteDto:
    try:
        route = service.validate_route(run_id)
    except MigrationRouteError as error:
        _raise(error)
    return _route_dto(route)
