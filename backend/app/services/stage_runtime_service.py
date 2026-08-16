"""Stage runtime requirement derivation, resolution, and binding persistence (V2 F02)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.compatibility import CompatibilityCatalogueEntry
from app.domain.runtime_execution import (
    RuntimeExecutableKind,
    RuntimeRequirement,
    RuntimeRequirementBinding,
)
from app.domain.stage_runtime import StageRuntimeBinding, StageRuntimeRequirement
from app.repositories.models import MigrationRunModel, MigrationStageModel, StageRuntimeBindingModel
from app.repositories.session import session_scope
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.runtime_resolution_application_service import _build_worker_version_probe
from app.services.runtime_resolver_authority import RuntimeMatrix, RuntimeResolverAuthority


class StageRuntimeError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class StageRuntimeApplicationService:
    """Derive stage runtime requirements, resolve them, and persist bindings."""

    def __init__(
        self,
        *,
        catalogue_provider: CompatibilityCatalogueProvider | None = None,
        authority: RuntimeResolverAuthority | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
        settings=None,
    ) -> None:
        from app.core.config import get_settings

        self._settings = settings or get_settings()
        self._catalogue_provider = catalogue_provider or CompatibilityCatalogueProvider()
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        if authority is None:
            matrix = RuntimeMatrix(
                node_install_root=self._settings.runtime_node_install_root.expanduser().resolve(),
                angular_cli_root=self._settings.runtime_angular_cli_root.expanduser().resolve(),
            )
            authority = RuntimeResolverAuthority(
                matrix, probe=_build_worker_version_probe(self._settings, matrix), now_provider=self._now_provider
            )
        self._authority = authority

    def stage_version_families(self, stage_id: str) -> tuple[str, str]:
        """Return the persisted stage's source/target version families."""
        with self._session_scope() as session:
            stage = session.get(MigrationStageModel, stage_id)
            if stage is None:
                raise StageRuntimeError("STAGE_NOT_FOUND", f"Migration stage {stage_id} not found")
            return (stage.source_version_family or "", stage.target_version_family or "")

    def derive_requirement(
        self,
        stage_id: str,
        source_family: str,
        target_family: str,
        catalogue_version: str | None = None,
    ) -> StageRuntimeRequirement:
        """Derive the stage's runtime requirement from the compatibility catalogue."""
        catalogue = self._catalogue_provider.load(catalogue_version or CompatibilityCatalogueProvider.CURRENT_VERSION)
        entry = catalogue.entry_for(source_family, target_family)
        if entry is None:
            raise StageRuntimeError(
                "CATALOGUE_ENTRY_MISSING",
                f"No compatibility catalogue entry for {source_family} -> {target_family}",
            )
        if entry.support_level == "blocked":
            raise StageRuntimeError(
                "STAGE_BLOCKED",
                f"Compatibility catalogue marks {source_family} -> {target_family} as blocked",
                {"blockers": list(entry.blockers)},
            )
        return self._requirement_from_entry(stage_id, entry, catalogue.version)

    @staticmethod
    def _requirement_from_entry(stage_id: str, entry: CompatibilityCatalogueEntry, catalogue_version: str) -> StageRuntimeRequirement:
        # Range-compatible stages may bind any governed installation that can
        # satisfy both Angular-family rows; do not pin resolution to the
        # historical certified Node major.
        runtime_id = "angular-stage-runtime"
        node_requirement = RuntimeRequirement(
            kind=RuntimeExecutableKind.NODE,
            runtime_id=runtime_id,
            minimum_version=entry.node_minimum or entry.node_exact or f"{entry.node_major}.0.0",
        )
        npm_minimum = f"{entry.npm_major}.0.0"
        requirements = (
            node_requirement,
            RuntimeRequirement(kind=RuntimeExecutableKind.NPM, runtime_id=runtime_id, minimum_version=npm_minimum),
            RuntimeRequirement(kind=RuntimeExecutableKind.NPX, runtime_id=runtime_id, minimum_version=npm_minimum),
        )
        return StageRuntimeRequirement(
            stage_id=stage_id,
            source_family=entry.source_family,
            target_family=entry.target_family,
            catalogue_version=catalogue_version,
            requirements=requirements,
        )

    def resolve_stage(
        self,
        stage_id: str,
        source_family: str,
        target_family: str,
        catalogue_version: str | None = None,
    ) -> StageRuntimeBinding:
        """Derive the stage requirement and resolve it against the machine matrix."""
        with self._session_scope() as session:
            if session.get(MigrationStageModel, stage_id) is None:
                raise StageRuntimeError("STAGE_NOT_FOUND", f"Migration stage {stage_id} not found")
        requirement = self.derive_requirement(stage_id, source_family, target_family, catalogue_version)
        resolved = self._authority.resolve(list(requirement.requirements))
        bound = all(item.descriptor is not None for item in resolved)
        if not bound:
            missing = [item.requirement.kind.value for item in resolved if item.descriptor is None]
            binding = StageRuntimeBinding(
                stage_id=stage_id,
                requirement=requirement,
                bindings=tuple(resolved),
                status="blocked",
                blocked_reason="machine runtime matrix cannot satisfy stage requirement for: " + ", ".join(missing),
                resolved_at=self._now_provider(),
            )
            return binding.bind_checksum()
        binding = StageRuntimeBinding(
            stage_id=stage_id,
            requirement=requirement,
            bindings=tuple(resolved),
            status="bound",
            resolved_at=self._now_provider(),
        )
        return binding.bind_checksum()

    def record_binding(self, run_id: str, binding: StageRuntimeBinding, *, actor: str | None = None) -> list[StageRuntimeBindingModel]:
        """Persist the resolved stage binding rows idempotently.

        Blocked resolutions persist a status-only row per kind so evidence of a
        failed binding attempt is durable, never silently absent.
        """
        now = self._now_provider()
        rows: list[StageRuntimeBindingModel] = []
        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise StageRuntimeError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            stage = session.get(MigrationStageModel, binding.stage_id)
            if stage is None:
                raise StageRuntimeError("STAGE_NOT_FOUND", f"Migration stage {binding.stage_id} not found")
            for item in binding.bindings:
                existing = session.get(StageRuntimeBindingModel, _binding_id(binding.stage_id, item.requirement.kind.value))
                if existing is not None:
                    rows.append(existing)
                    continue
                row = StageRuntimeBindingModel(
                    id=_binding_id(binding.stage_id, item.requirement.kind.value),
                    run_id=run_id,
                    stage_id=binding.stage_id,
                    kind=item.requirement.kind.value,
                    runtime_id=item.descriptor.runtime_id if item.descriptor else None,
                    version_exact=item.descriptor.version_exact if item.descriptor else None,
                    sha256=item.descriptor.sha256 if item.descriptor else None,
                    resolved_path=item.descriptor.resolved_path if item.descriptor else None,
                    source=item.descriptor.source if item.descriptor else None,
                    status=binding.status,
                    blocked_reason=item.blocked_reason or binding.blocked_reason,
                    created_at=now,
                )
                session.add(row)
                rows.append(row)
            session.commit()
            for row in rows:
                session.refresh(row)
        return rows

    def list_stage_bindings(self, stage_id: str) -> list[StageRuntimeBindingModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(StageRuntimeBindingModel)
                    .where(StageRuntimeBindingModel.stage_id == stage_id)
                    .order_by(StageRuntimeBindingModel.created_at.desc())
                ).all()
            )

    def list_run_bindings(self, run_id: str) -> list[StageRuntimeBindingModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(StageRuntimeBindingModel)
                    .where(StageRuntimeBindingModel.run_id == run_id)
                    .order_by(StageRuntimeBindingModel.created_at.desc())
                ).all()
            )


def _binding_id(stage_id: str, kind: str) -> str:
    import hashlib

    return "srb-" + hashlib.sha256(f"{stage_id}:{kind}".encode()).hexdigest()[:24]
