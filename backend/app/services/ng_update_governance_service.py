"""Angular update governance service (V2 F14)."""

from __future__ import annotations

from app.domain.command import ANGULAR_UPDATE_V3_RENDERER
from app.domain.migration_route import validate_envelope
from app.domain.ng_update_governance import NgUpdateAuthorization, NgUpdateCommandSpec
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.runtime_certification_service import RuntimeCertificationError, RuntimeCertificationService


class NgUpdateGovernanceError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class NgUpdateGovernanceService:
    """Resolve and authorize per-major ng update commands."""

    def __init__(
        self,
        *,
        catalogue_provider: CompatibilityCatalogueProvider | None = None,
        certification_service: RuntimeCertificationService | None = None,
    ) -> None:
        self._catalogue_provider = catalogue_provider or CompatibilityCatalogueProvider()
        self._certification = certification_service or RuntimeCertificationService()

    def spec_for_transition(self, source_major: int, target_major: int, catalogue_version: str | None = None) -> NgUpdateCommandSpec:
        """Resolve the exact update command spec for an adjacent-major transition (F14-01)."""
        blocker = validate_envelope(source_major, target_major)
        if blocker:
            raise NgUpdateGovernanceError("ENVELOPE_VIOLATION", f"transition outside the supported envelope: {blocker}")
        if target_major != source_major + 1:
            raise NgUpdateGovernanceError("NOT_ADJACENT", "ng update governance is per adjacent-major transition only")
        catalogue = self._catalogue_provider.load(catalogue_version or CompatibilityCatalogueProvider.CURRENT_VERSION)
        entry = catalogue.entry_for(f"angular-{source_major}.x", f"angular-{target_major}.x")
        if entry is None:
            raise NgUpdateGovernanceError("CATALOGUE_ENTRY_MISSING", f"No catalogue entry for {source_major}->{target_major}")
        bindings = {
            "target_exact": entry.target_angular_exact,
            "target_cli_exact": entry.target_cli_exact or entry.cli_exact or entry.target_angular_exact,
        }
        rendered = ANGULAR_UPDATE_V3_RENDERER.render_arguments(bindings)
        spec = NgUpdateCommandSpec(
            source_major=source_major,
            target_major=target_major,
            template_id=ANGULAR_UPDATE_V3_RENDERER.template_id,
            executable=ANGULAR_UPDATE_V3_RENDERER.executable,
            target_exact=bindings["target_exact"],
            target_cli_exact=bindings["target_cli_exact"],
            rendered_arguments=rendered,
        )
        return spec.bind_checksum()

    def authorize_update(self, source_major: int, target_major: int, *, stage_id: str) -> NgUpdateAuthorization:
        """Govern an update execution: certified runtime + catalogue-derived spec (F14-02/04).

        The update is authorized only when the stage's transition matches the
        requested source/target majors, its runtime is certified for that
        transition (F11 gate), and the spec resolves from the catalogue.
        """
        spec = self.spec_for_transition(source_major, target_major)
        families = self._certification._stage_runtime.stage_version_families(stage_id)
        if families != (f"angular-{source_major}.x", f"angular-{target_major}.x"):
            return NgUpdateAuthorization(
                source_major=source_major, target_major=target_major,
                spec_checksum=spec.checksum, certified=False, allowed=False,
                reason=f"stage transition {families} does not match the requested {source_major}->{target_major} update",
            )
        try:
            certification = self._certification.enforce_stage_certification(stage_id)
        except RuntimeCertificationError as exc:
            return NgUpdateAuthorization(
                source_major=source_major, target_major=target_major,
                spec_checksum=spec.checksum, certified=False, allowed=False,
                reason=exc.message,
            )
        if not certification.allowed:
            return NgUpdateAuthorization(
                source_major=source_major, target_major=target_major,
                spec_checksum=spec.checksum, certified=certification.certified, allowed=False,
                reason=certification.reason or "runtime is not compatible",
            )
        return NgUpdateAuthorization(
            source_major=source_major, target_major=target_major,
            spec_checksum=spec.checksum, certified=certification.certified, allowed=True,
            reason=f"update authorized against {certification.classification} runtime and catalogue spec",
        )

