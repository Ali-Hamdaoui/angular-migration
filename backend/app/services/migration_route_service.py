"""Deterministic migration route service: compute, persist, retrieve (V2 F10)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.migration_route import MigrationRoute, RouteStage, validate_envelope
from app.repositories.models import MigrationRunModel, MigrationRouteModel
from app.repositories.session import session_scope
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider


class MigrationRouteError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class MigrationRouteService:
    """Compute the deterministic adjacent-major chain from the catalogue."""

    def __init__(
        self,
        *,
        catalogue_provider: CompatibilityCatalogueProvider | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalogue_provider = catalogue_provider or CompatibilityCatalogueProvider()
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def compute(self, source_major: int, target_major: int, catalogue_version: str | None = None) -> MigrationRoute:
        """Compute the deterministic route for a source -> target pair (F10-02/03).

        The envelope is validated first; the chain is derived only from the
        compatibility catalogue, so identical inputs always produce an
        identical, checksum-frozen route.
        """
        blocker = validate_envelope(source_major, target_major)
        if blocker:
            raise MigrationRouteError("ENVELOPE_VIOLATION", f"source/target outside the supported envelope: {blocker}", {"blocker": blocker})
        try:
            catalogue = self._catalogue_provider.load(catalogue_version or CompatibilityCatalogueProvider.CURRENT_VERSION)
        except ValueError as exc:
            raise MigrationRouteError(
                "UNSUPPORTED_CATALOGUE_VERSION",
                f"unsupported catalogue version {catalogue_version!r}",
                {"catalogue_version": catalogue_version},
            ) from exc
        stages = []
        for order, major in enumerate(range(source_major, target_major), start=1):
            source_family = f"angular-{major}.x"
            target_family = f"angular-{major + 1}.x"
            entry = catalogue.entry_for(source_family, target_family)
            if entry is None:
                raise MigrationRouteError(
                    "CATALOGUE_ROUTE_MISSING",
                    f"No catalogue entry for {source_family} -> {target_family}",
                    {"major": major},
                )
            stages.append(
                RouteStage(
                    stage_order=order,
                    source_major=major,
                    target_major=major + 1,
                    source_family=source_family,
                    target_family=target_family,
                    support_level=entry.support_level,
                )
            )
        route = MigrationRoute(
            source_major=source_major,
            target_major=target_major,
            catalogue_version=catalogue.version,
            stages=tuple(stages),
        )
        return route.bind_checksum()

    def compute_for_run(self, run_id: str, catalogue_version: str | None = None) -> MigrationRoute:
        """Derive source/target majors from the run and compute its route (F10-04)."""
        with self._session_scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise MigrationRouteError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            source_major = _major_from_family(run.source_version_family)
            target_major = _major_from_family(run.target_version_family)
        return self.compute(source_major, target_major, catalogue_version)

    def persist(self, run_id: str, route: MigrationRoute, *, actor: str | None = None) -> MigrationRouteModel:
        """Persist the immutable route for a run (idempotent by checksum)."""
        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise MigrationRouteError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            existing = session.scalar(
                select(MigrationRouteModel).where(
                    MigrationRouteModel.run_id == run_id,
                    MigrationRouteModel.checksum == route.checksum,
                )
            )
            if existing is not None:
                return existing
            record = MigrationRouteModel(
                id="route-" + hashlib.sha256(f"{run_id}:{route.checksum}".encode()).hexdigest()[:24],
                run_id=run_id,
                source_major=route.source_major,
                target_major=route.target_major,
                catalogue_version=route.catalogue_version,
                stages=[stage.model_dump(mode="json") for stage in route.stages],
                checksum=route.checksum,
                actor=actor,
                created_at=self._now_provider(),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_run_route(self, run_id: str) -> MigrationRouteModel | None:
        with self._session_scope() as session:
            return session.scalar(
                select(MigrationRouteModel)
                .where(MigrationRouteModel.run_id == run_id)
                .order_by(MigrationRouteModel.created_at.desc())
                .limit(1)
            )

    def validate_route(self, run_id: str) -> MigrationRoute:
        """Recompute the route deterministically and compare with the persisted one.

        Raises ROUTE_DRIFT when the persisted route no longer matches the
        catalogue-derived route (immutability enforcement, F10-03).
        """
        route = self.compute_for_run(run_id)
        persisted = self.get_run_route(run_id)
        if persisted is None:
            raise MigrationRouteError("ROUTE_NOT_PERSISTED", f"No route persisted for run {run_id}")
        if persisted.checksum != route.checksum or persisted.source_major != route.source_major or persisted.target_major != route.target_major:
            raise MigrationRouteError(
                "ROUTE_DRIFT",
                "The persisted migration route drifted from the catalogue-derived route",
                {"persisted": persisted.checksum, "derived": route.checksum},
            )
        return route


def _major_from_family(family: str | None) -> int:
    if not family:
        raise MigrationRouteError("RUN_VERSION_FAMILY_MISSING", "run source/target version families are not set")
    try:
        return int(family.removeprefix("angular-").removesuffix(".x"))
    except ValueError as exc:
        raise MigrationRouteError("RUN_VERSION_FAMILY_INVALID", f"invalid version family {family}") from exc
