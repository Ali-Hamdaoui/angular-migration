"""API contracts for the compatibility catalogue (V2 F09)."""

from datetime import datetime
from typing import Literal

from app.domain.contracts import ContractModel


class CatalogueEntryDto(ContractModel):
    stage_id: str
    source_family: str
    target_family: str
    target_angular_exact: str
    target_cli_exact: str
    typescript_minimum: str | None = None
    typescript_exclusive_maximum: str | None = None
    rxjs_minimum: str | None = None
    node_major: int
    npm_major: int
    node_minimum: str | None = None
    npm_exact: str | None = None
    support_level: Literal["officially_supported", "historical_validated", "historical_experimental", "blocked"]
    fixture_status: Literal["passed", "incomplete", "failed"]
    known_risks: list[str]
    blockers: list[str]
    validated_runtime_profiles: list[list[str]]
    certification_status: str | None = None
    certification_source: str | None = None
    certified_at: datetime | None = None


class CatalogueEntryListDto(ContractModel):
    version: str
    checksum: str
    entries: list[CatalogueEntryDto]


class CatalogueVersionDto(ContractModel):
    id: str
    version: str
    checksum: str
    created_by: str | None = None
    change_reason: str | None = None
    created_at: datetime


class CatalogueVersionListDto(ContractModel):
    versions: list[CatalogueVersionDto]
