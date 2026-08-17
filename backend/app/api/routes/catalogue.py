"""Compatibility catalogue query API (V2 F09-02/04)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.catalogue_contracts import (
    CatalogueEntryDto,
    CatalogueEntryListDto,
    CatalogueVersionDto,
    CatalogueVersionListDto,
)
from app.services.catalogue_registry_service import CompatibilityCatalogueRegistry

router = APIRouter(prefix="/catalogue", tags=["compatibility-catalogue"])


def get_catalogue_registry() -> CompatibilityCatalogueRegistry:
    return CompatibilityCatalogueRegistry()


def _entry_dto(entry) -> CatalogueEntryDto:
    return CatalogueEntryDto(
        stage_id=entry.stage_id,
        source_family=entry.source_family,
        target_family=entry.target_family,
        target_angular_exact=entry.target_angular_exact,
        target_cli_exact=entry.target_cli_exact,
        typescript_minimum=entry.typescript_minimum,
        typescript_exclusive_maximum=entry.typescript_exclusive_maximum,
        rxjs_minimum=entry.rxjs_minimum,
        rxjs_ranges=list(entry.rxjs_ranges),
        node_major=entry.node_major,
        npm_major=entry.npm_major,
        node_minimum=entry.node_minimum,
        npm_exact=entry.npm_exact,
        support_level=entry.support_level,
        fixture_status=entry.fixture_status,
        known_risks=list(entry.known_risks),
        blockers=list(entry.blockers),
        validated_runtime_profiles=[list(profile) for profile in entry.validated_runtime_profiles],
        proven_runtime_profiles=[list(profile) for profile in entry.proven_runtime_profiles],
        proven_runtime_evidence=[profile.model_dump(mode="json") for profile in entry.proven_runtime_evidence],
        proven_runtime_source=entry.proven_runtime_source,
        source_node_ranges=list(entry.source_node_ranges),
        target_node_ranges=list(entry.target_node_ranges),
        certification_status=entry.certification_status,
        certification_source=entry.certification_source,
        certified_at=entry.certified_at,
    )


@router.get("", response_model=CatalogueEntryListDto)
def get_catalogue(
    version: str | None = None,
    registry: CompatibilityCatalogueRegistry = Depends(get_catalogue_registry),
) -> CatalogueEntryListDto:
    catalogue = registry.load_catalogue(version)
    return CatalogueEntryListDto(version=catalogue.version, checksum=catalogue.checksum, entries=[_entry_dto(e) for e in catalogue.entries])


@router.get("/entries/{source_family}/{target_family}", response_model=CatalogueEntryDto)
def get_catalogue_entry(
    source_family: str,
    target_family: str,
    version: str | None = None,
    registry: CompatibilityCatalogueRegistry = Depends(get_catalogue_registry),
) -> CatalogueEntryDto:
    entry = registry.entry(source_family, target_family, version)
    if entry is None:
        raise HTTPException(status_code=404, detail={"error_code": "CATALOGUE_ENTRY_MISSING", "message": f"No entry for {source_family} -> {target_family}"})
    return _entry_dto(entry)


@router.get("/versions", response_model=CatalogueVersionListDto)
def list_catalogue_versions(
    registry: CompatibilityCatalogueRegistry = Depends(get_catalogue_registry),
) -> CatalogueVersionListDto:
    versions = registry.list_versions()
    return CatalogueVersionListDto(
        versions=[
            CatalogueVersionDto(
                id=v.id, version=v.version, checksum=v.checksum,
                created_by=v.created_by, change_reason=v.change_reason, created_at=v.created_at,
            )
            for v in versions
        ]
    )


@router.post("/versions", response_model=CatalogueVersionDto)
def record_catalogue_version(
    version: str | None = None,
    actor: str | None = None,
    reason: str | None = None,
    registry: CompatibilityCatalogueRegistry = Depends(get_catalogue_registry),
) -> CatalogueVersionDto:
    record = registry.record_version(version, actor=actor, reason=reason)
    return CatalogueVersionDto(
        id=record.id, version=record.version, checksum=record.checksum,
        created_by=record.created_by, change_reason=record.change_reason, created_at=record.created_at,
    )


def _catalogue(registry: CompatibilityCatalogueRegistry, version: str | None):
    from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider

    return CompatibilityCatalogueProvider().load(version or CompatibilityCatalogueProvider.CURRENT_VERSION)
