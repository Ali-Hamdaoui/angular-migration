"""Compatibility catalogue registry: version snapshots, audit trail, queries (V2 F09)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.domain.compatibility import CompatibilityCatalogue, CompatibilityCatalogueEntry
from app.repositories.models import CompatibilityCatalogueModel
from app.repositories.session import session_scope
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider


class CatalogueRegistryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class CompatibilityCatalogueRegistry:
    """Persist catalogue versions with an audit trail and expose queries."""

    def __init__(
        self,
        *,
        provider: CompatibilityCatalogueProvider | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider or CompatibilityCatalogueProvider()
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def record_version(self, version: str | None = None, *, actor: str | None = None, reason: str | None = None) -> CompatibilityCatalogueModel:
        """Persist a catalogue version snapshot with audit metadata (idempotent)."""
        catalogue = self._provider.load(version or CompatibilityCatalogueProvider.CURRENT_VERSION)
        with self._session_scope() as session:
            existing = session.scalar(
                select(CompatibilityCatalogueModel).where(CompatibilityCatalogueModel.version == catalogue.version)
            )
            if existing is not None:
                return existing
            record = CompatibilityCatalogueModel(
                id=f"catalogue-{uuid4().hex[:12]}",
                version=catalogue.version,
                checksum=catalogue.checksum,
                metadata_json={"entries": [entry.model_dump(mode="json") for entry in catalogue.entries], "checksum": catalogue.checksum},
                created_by=actor,
                change_reason=reason,
                created_at=self._now_provider(),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_versions(self) -> list[CompatibilityCatalogueModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(CompatibilityCatalogueModel).order_by(CompatibilityCatalogueModel.created_at.desc())
                ).all()
            )

    def entry(self, source_family: str, target_family: str, version: str | None = None) -> CompatibilityCatalogueEntry | None:
        catalogue = self._provider.load(version or CompatibilityCatalogueProvider.CURRENT_VERSION)
        return catalogue.entry_for(source_family, target_family)

    def entries(self, version: str | None = None) -> list[CompatibilityCatalogueEntry]:
        catalogue = self._provider.load(version or CompatibilityCatalogueProvider.CURRENT_VERSION)
        return list(catalogue.entries)
