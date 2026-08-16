"""API contracts for migration routes (V2 F10)."""

from datetime import datetime

from app.domain.contracts import ContractModel


class RouteStageDto(ContractModel):
    stage_order: int
    source_major: int
    target_major: int
    source_family: str
    target_family: str
    support_level: str


class MigrationRouteDto(ContractModel):
    source_major: int
    target_major: int
    catalogue_version: str
    stages: list[RouteStageDto]
    checksum: str


class RouteRecordDto(ContractModel):
    id: str
    run_id: str
    source_major: int
    target_major: int
    catalogue_version: str
    stages: list[dict]
    checksum: str
    actor: str | None = None
    created_at: datetime


class ComputeRouteRequest(ContractModel):
    source_major: int
    target_major: int
    catalogue_version: str | None = None


class RouteRecordListDto(ContractModel):
    routes: list[RouteRecordDto]
