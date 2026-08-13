"""Backend-owned immutable compatibility catalogue authority."""

from app.domain.compatibility import CompatibilityCatalogue, CompatibilityCatalogueEntry


class CompatibilityCatalogueProvider:
    """Load the active versioned catalogue independently of HTTP mutations."""

    CURRENT_VERSION = "catalog-v3"

    _PROVEN_V3 = (
        # source, target core, target CLI/build, TS, RxJS, Zone, angular-eslint, Node, npm
        (11, "12.2.17", "12.2.18", "4.3.5", "6.6.7", "0.11.8", None, "12.22.12", "8.19.4"),
        (12, "13.3.12", "13.3.11", "4.6.4", "6.6.7", "0.11.8", "13.5.0", "16.20.2", "8.19.4"),
        (13, "14.3.0", "14.2.13", "4.6.4", "6.6.7", "0.11.8", "14.4.0", "16.20.2", "8.19.4"),
        (14, "15.2.10", "15.2.11", "4.9.5", "6.6.7", "0.11.8", "15.2.1", "16.20.2", "8.19.4"),
        (15, "16.2.12", "16.2.16", "5.1.6", "6.6.7", "0.13.3", "16.3.1", "16.20.2", "8.19.4"),
        (16, "17.3.12", "17.3.17", "5.4.5", "6.6.7", "0.14.10", "17.5.3", "20.11.1", "10.2.4"),
        (17, "18.2.14", "18.2.21", "5.5.4", "6.6.7", "0.14.10", "18.4.3", "22.23.1", "8.19.4"),
        (18, "19.2.25", "19.2.27", "5.8.3", "6.6.7", "0.15.1", "19.8.1", "22.23.1", "8.19.4"),
        (19, "20.3.27", "20.3.34", "5.9.3", "6.6.7", "0.15.1", "20.7.0", "22.23.1", "8.19.4"),
        (20, "21.2.19", "21.2.20", "5.9.3", "6.6.7", "0.15.1", "21.4.0", "22.23.1", "8.19.4"),
    )

    def load(self, version: str = CURRENT_VERSION) -> CompatibilityCatalogue:
        if version not in {"catalog-v1", "catalog-v2", self.CURRENT_VERSION}:
            raise ValueError("unsupported compatibility catalogue version")
        if version == self.CURRENT_VERSION:
            entries = tuple(
                CompatibilityCatalogueEntry(
                    stage_id=f"angular-{major}-to-{major + 1}",
                    source_family=f"angular-{major}.x",
                    target_family=f"angular-{major + 1}.x",
                    target_angular_exact=core,
                    target_cli_exact=cli,
                    typescript_exact=typescript,
                    rxjs_exact=rxjs,
                    zone_js_exact=zone,
                    angular_eslint_exact=angular_eslint,
                    node_major=int(node.split(".", 1)[0]),
                    npm_major=int(npm.split(".", 1)[0]),
                    node_exact=node,
                    npm_exact=npm,
                    cli_exact=cli,
                    support_level="historical_validated",
                    fixture_status="passed",
                    validation_policy_id="angular-stage-standard-v2",
                    known_risks=(),
                    validated_runtime_profiles=((node, npm),),
                )
                for major, core, cli, typescript, rxjs, zone, angular_eslint, node, npm in self._PROVEN_V3
            )
            return CompatibilityCatalogue.build(version, entries)
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
