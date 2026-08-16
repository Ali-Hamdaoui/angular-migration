"""Backend-owned immutable compatibility catalogue authority (V2 F09).

Covers the full Angular 11 → 21 adjacent-major envelope.  Node/TypeScript/RxJS
constraints are derived from the official Angular version-compatibility
documentation (angular.dev/reference/versions, 2026 snapshot).  The catalogue is
the immutable runtime authority consulted by planning, preflight, and
validation; certification metadata records how each entry was proven.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.compatibility import CompatibilityCatalogue, CompatibilityCatalogueEntry

#: Node.js minimum per target Angular major (official Angular compatibility).
_NODE_MINIMUMS: dict[int, str] = {
    12: "12.14.0",
    13: "12.20.0",
    14: "14.15.0",
    15: "14.20.0",
    16: "16.14.0",
    17: "18.13.0",
    18: "18.19.1",
    19: "18.19.1",
    20: "20.19.0",
    21: "20.19.0",
}

#: TypeScript range per target Angular major (official Angular compatibility).
_TYPESCRIPT_RANGES: dict[int, tuple[str, str]] = {
    12: ("4.2.3", "4.4.0"),
    13: ("4.4.3", "4.7.0"),
    14: ("4.6.2", "4.9.0"),
    15: ("4.8.2", "5.0.0"),
    16: ("4.9.3", "5.2.0"),
    17: ("5.2.0", "5.5.0"),
    18: ("5.4.0", "5.6.0"),
    19: ("5.5.0", "5.7.0"),
    20: ("5.8.0", "5.9.0"),
    21: ("5.9.0", "6.0.0"),
}


#: The certified (runtime-proven) transition; the rest of the envelope is
#: seeded with official compatibility data and historical_experimental
#: support until bridge certification (F11) promotes entries.
CERTIFIED_TRANSITIONS: frozenset[tuple[int, int]] = frozenset({(18, 19), (19, 20), (20, 21)})

#: Runtime profiles proven by bridge certification (F11) for each certified
#: transition: (node_exact, npm_exact) pairs verified on the migration VM.
CERTIFIED_RUNTIME_PROFILES: dict[tuple[int, int], tuple[tuple[str, str], ...]] = {
    (18, 19): (("18.20.8", "10.8.2"),),
    (19, 20): (("20.20.2", "10.8.2"),),
    (20, 21): (("22.23.2", "10.9.8"),),
}


class CompatibilityCatalogueProvider:
    """Load the active versioned catalogue independently of HTTP mutations."""

    CURRENT_VERSION = "catalog-v3"

    def load(self, version: str = CURRENT_VERSION) -> CompatibilityCatalogue:
        if version not in {"catalog-v1", "catalog-v2", self.CURRENT_VERSION}:
            raise ValueError("unsupported compatibility catalogue version")
        if version in {"catalog-v1", "catalog-v2"}:
            return self._load_legacy(version)
        entries = []
        for major in range(11, 21):
            certified = (major, major + 1) in CERTIFIED_TRANSITIONS
            entries.append(self._entry_for(major, certified))
        return CompatibilityCatalogue.build(version, tuple(entries))

    def _load_legacy(self, version: str) -> CompatibilityCatalogue:
        """Preserve the exact historical v1/v2 contract (Angular 18-21 envelope)."""
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

    @classmethod
    def _entry_for(cls, major: int, certified: bool) -> CompatibilityCatalogueEntry:
        target = major + 1
        node_minimum = _NODE_MINIMUMS[target]
        ts_minimum, ts_maximum = _TYPESCRIPT_RANGES[target]
        support_level = "historical_validated" if certified else "historical_experimental"
        fixture_status = "passed" if certified else "incomplete"
        node_major = _node_major_for(node_minimum)
        if certified:
            validated = CERTIFIED_RUNTIME_PROFILES.get((major, target), ())
            certified_runtime = validated[0] if validated else None
            node_exact = certified_runtime[0] if certified_runtime else node_minimum
            npm_exact = certified_runtime[1] if certified_runtime else "10.2.4"
        else:
            validated = ()
            node_exact = None
            npm_exact = None
        return CompatibilityCatalogueEntry(
            stage_id=f"angular-{major}-to-{target}",
            source_family=f"angular-{major}.x",
            target_family=f"angular-{target}.x",
            target_angular_exact=f"{target}.0.0",
            target_cli_exact=f"{target}.0.0",
            typescript_minimum=ts_minimum,
            typescript_exclusive_maximum=ts_maximum,
            rxjs_minimum="6.5.3",
            node_major=node_major,
            npm_major=10,
            node_minimum=node_minimum,
            node_exact=node_exact,
            npm_exact=npm_exact,
            cli_exact=f"{target}.0.0",
            support_level=support_level,
            fixture_status=fixture_status,
            validation_policy_id="angular-stage-standard-v2",
            known_risks=() if certified else ("historical_fixture_evidence_incomplete",),
            validated_runtime_profiles=validated,
            certification_status="certified" if certified else "seeded_official",
            certification_source="angular.dev/reference/versions" if not certified else "bridge-certification",
            certified_at=datetime.now(UTC) if certified else None,
        )


def _node_major_for(minimum: str) -> int:
    return int(minimum.split(".", 1)[0])
