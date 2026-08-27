"""Compare a prepared stage plan with the current immutable catalogue authority."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.compatibility import CompatibilityCatalogueEntry
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider


@dataclass(frozen=True)
class StagePlanAuthority:
    catalogue_version: str
    catalogue_checksum: str
    source_family: str
    target_family: str
    target_exact: str
    target_cli_exact: str
    target_cohort: dict[str, str]


@dataclass(frozen=True)
class StagePlanAuthorityComparison:
    stale: bool
    reason_code: str | None
    differences: tuple[str, ...]
    authority: StagePlanAuthority


class StagePlanAuthorityError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StagePlanAuthorityService:
    """Provide one generic current-authority comparison for prepared stages."""

    def __init__(self, *, provider: CompatibilityCatalogueProvider | None = None) -> None:
        self._provider = provider or CompatibilityCatalogueProvider()

    def current(self, source_family: str, target_family: str) -> StagePlanAuthority:
        catalogue = self._provider.load()
        entry = catalogue.entry_for(source_family, target_family)
        if entry is None:
            raise StagePlanAuthorityError(
                "CATALOGUE_ENTRY_MISSING",
                f"No compatibility catalogue entry for {source_family} -> {target_family}",
            )
        return self._authority(catalogue.version, catalogue.checksum, entry)

    def compare(self, stage_plan: dict, plan: dict | None = None) -> StagePlanAuthorityComparison:
        source_family = stage_plan.get("source_family")
        target_family = stage_plan.get("target_family")
        if not isinstance(source_family, str) or not isinstance(target_family, str):
            raise StagePlanAuthorityError(
                "STAGE_PLAN_AUTHORITY_INPUT_INCOMPLETE",
                "Prepared stage plan lacks source and target families",
            )
        authority = self.current(source_family, target_family)
        differences: list[str] = []
        if stage_plan.get("target_exact") != authority.target_exact:
            differences.append("target_exact")
        if stage_plan.get("target_cli_exact") != authority.target_cli_exact:
            differences.append("target_cli_exact")
        if stage_plan.get("target_cohort") != authority.target_cohort:
            differences.append("target_cohort")
        if plan is not None:
            if plan.get("catalogue_version") != authority.catalogue_version:
                differences.append("catalogue_version")
            if plan.get("catalogue_checksum") != authority.catalogue_checksum:
                differences.append("catalogue_checksum")
        return StagePlanAuthorityComparison(
            stale=bool(differences),
            reason_code="STAGE_PLAN_AUTHORITY_STALE" if differences else None,
            differences=tuple(differences),
            authority=authority,
        )

    @staticmethod
    def _authority(version: str, checksum: str, entry: CompatibilityCatalogueEntry) -> StagePlanAuthority:
        return StagePlanAuthority(
            catalogue_version=version,
            catalogue_checksum=checksum,
            source_family=entry.source_family,
            target_family=entry.target_family,
            target_exact=entry.target_angular_exact,
            target_cli_exact=entry.target_cli_exact,
            target_cohort=entry.target_cohort(),
        )
