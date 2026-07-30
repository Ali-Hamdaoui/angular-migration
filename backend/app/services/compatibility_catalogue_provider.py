"""Backend-owned immutable compatibility catalogue authority."""

from app.domain.compatibility import CompatibilityCatalogue, CompatibilityCatalogueEntry


class CompatibilityCatalogueProvider:
    """Load the active versioned catalogue independently of HTTP mutations."""

    CURRENT_VERSION = "catalog-v2"

    def load(self, version: str = CURRENT_VERSION) -> CompatibilityCatalogue:
        if version not in {"catalog-v1", self.CURRENT_VERSION}:
            raise ValueError("unsupported compatibility catalogue version")
        entries = tuple(
            CompatibilityCatalogueEntry(
                stage_id=f"angular-{major}-to-{major + 1}",
                source_family=f"angular-{major}.x",
                target_family=f"angular-{major + 1}.x",
                target_angular_exact=f"{major + 1}.0.0",
                target_cli_exact=f"{major + 1}.0.0",
                node_major=20,
                npm_major=10,
                node_exact="20.11.1" if major == 18 else "20.19.0",
                npm_exact="10.2.4",
                cli_exact=f"{major + 1}.0.0",
                support_level="historical_experimental",
                fixture_status="incomplete",
                validation_policy_id="angular-stage-standard-v2",
                known_risks=("historical_fixture_evidence_incomplete",),
                validated_runtime_profiles=()
                if version == "catalog-v1"
                else (("20.11.1" if major == 18 else "20.19.0", "10.2.4"), ("22.23.1", "10.9.8")),
            )
            for major in range(18, 21)
        )
        return CompatibilityCatalogue.build(version, entries)
