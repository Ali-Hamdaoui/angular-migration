"""Backend-owned immutable compatibility catalogue authority (V2 F09).

Covers the full Angular 11 → 21 adjacent-major envelope.  Node/TypeScript/RxJS
constraints are derived from the official Angular version-compatibility
documentation (angular.dev/reference/versions, 2026 snapshot).  The catalogue is
the immutable runtime authority consulted by planning, preflight, and
validation; certification metadata records how each entry was proven.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.compatibility import CompatibilityCatalogue, CompatibilityCatalogueEntry, RuntimeProofProfile
from app.domain.execution_profile import Version

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
    11: ("4.0.0", "4.2.0"),
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

_RXJS_RANGES: dict[int, tuple[str, ...]] = {
    11: ("^6.5.3",),
    12: ("^6.5.3", "^7.0.0"),
    13: ("^6.5.3", "^7.4.0"),
    14: ("^6.5.3", "^7.4.0"),
    15: ("^6.5.3", "^7.4.0"),
    16: ("^6.5.3", "^7.4.0"),
    17: ("^6.5.3", "^7.4.0"),
    18: ("^6.5.3", "^7.4.0"),
    19: ("^6.5.3", "^7.4.0"),
    20: ("^6.5.3", "^7.4.0"),
    21: ("^6.5.3", "^7.4.0"),
}

# Official Angular source/target Node ranges.  A stage uses the intersection
# of its two adjacent Angular-family rows; npm has no equivalent official
# Angular-major range and is governed by executable/probe policy instead.
_NODE_RANGES: dict[int, tuple[str, ...]] = {
    11: ("^10.13.0", "^12.11.0"),
    12: ("^12.14.0", "^14.15.0"),
    13: ("^12.20.0", "^14.15.0", "^16.10.0"),
    14: ("^14.15.0", "^16.10.0"),
    15: ("^14.20.0", "^16.13.0", "^18.10.0"),
    16: ("^16.14.0", "^18.10.0"),
    17: ("^18.13.0", "^20.9.0"),
    18: ("^18.19.1", "^20.11.1", "^22.0.0"),
    19: ("^18.19.1", "^20.11.1", "^22.0.0"),
    20: ("^20.19.0", "^22.12.0", "^24.0.0"),
    21: ("^20.19.0", "^22.12.0", "^24.0.0"),
}


#: Historical certified transitions as labeled by catalog-v3. They lacked
#: immutable repository evidence artifacts, so catalog-v4 no longer certifies
#: catalogue entries from static seed data; certification requires the reviewed
#: qualification-evidence promotion path (P0-0). The v1/v2/v3 builders retain
#: these values byte-for-byte so historical versions stay loadable unchanged.
CERTIFIED_TRANSITIONS: frozenset[tuple[int, int]] = frozenset({(18, 19), (19, 20), (20, 21)})

CERTIFIED_RUNTIME_PROFILES: dict[tuple[int, int], tuple[tuple[str, str], ...]] = {
    (18, 19): (("18.20.8", "10.8.2"),),
    (19, 20): (("20.20.2", "10.8.2"),),
    (20, 21): (("22.23.2", "10.9.8"),),
}

DEV_RUNTIMES_PROVEN_PROFILES: dict[tuple[int, int], tuple[tuple[str, str], ...]] = {
    (11, 12): (("12.22.12", "8.19.4"),),
    (12, 13): (("16.20.2", "8.19.4"),),
    (13, 14): (("16.20.2", "8.19.4"),),
    (14, 15): (("16.20.2", "8.19.4"),),
    (15, 16): (("16.20.2", "8.19.4"),),
    (16, 17): (("20.11.1", "8.19.4"),),
    (17, 18): (("22.23.1", "8.19.4"),),
    (18, 19): (("22.23.1", "8.19.4"),),
    (19, 20): (("22.23.1", "8.19.4"),),
    (20, 21): (("22.23.1", "8.19.4"),),
}

#: Fixed certification timestamp so the catalogue is byte-identical across loads
#: (immutable authority; a per-load datetime would break checksum equality).
CERTIFIED_AT = datetime(2026, 8, 16, tzinfo=UTC)

DEV_RUNTIMES_PROVEN_EVIDENCE: dict[tuple[int, int], RuntimeProofProfile] = {
    (11, 12): RuntimeProofProfile(source_angular_exact="11.0.4", target_angular_exact="12.2.17", target_cli_exact="12.2.18", node_exact="12.22.12", npm_exact="8.19.4", proof_source="dev-runtimes-real-e2e", proof_status="observed", proved_at=CERTIFIED_AT),
    (12, 13): RuntimeProofProfile(source_angular_exact="12.2.17", target_angular_exact="13.3.12", target_cli_exact="13.3.11", node_exact="16.20.2", npm_exact="8.19.4", proof_source="dev-runtimes-real-e2e", proof_status="observed", proved_at=CERTIFIED_AT),
    (13, 14): RuntimeProofProfile(source_angular_exact="13.3.12", target_angular_exact="14.3.0", target_cli_exact="14.2.13", node_exact="16.20.2", npm_exact="8.19.4", proof_source="dev-runtimes-real-e2e", proof_status="observed", proved_at=CERTIFIED_AT),
    (14, 15): RuntimeProofProfile(source_angular_exact="14.3.0", target_angular_exact="15.2.10", target_cli_exact="15.2.11", node_exact="16.20.2", npm_exact="8.19.4", proof_source="dev-runtimes-real-e2e", proof_status="observed", proved_at=CERTIFIED_AT),
    (15, 16): RuntimeProofProfile(source_angular_exact="15.2.10", target_angular_exact="16.2.12", target_cli_exact="16.2.16", node_exact="16.20.2", npm_exact="8.19.4", proof_source="dev-runtimes-real-e2e", proof_status="observed", proved_at=CERTIFIED_AT),
    (16, 17): RuntimeProofProfile(source_angular_exact="16.2.12", target_angular_exact="17.3.12", target_cli_exact="17.3.17", node_exact="20.11.1", npm_exact="10.2.4", proof_source="dev-runtimes-real-e2e", proof_status="observed", proved_at=CERTIFIED_AT),
    (17, 18): RuntimeProofProfile(source_angular_exact="17.3.12", target_angular_exact="18.2.14", target_cli_exact="18.2.21", node_exact="22.23.1", npm_exact="8.19.4", proof_source="dev-runtimes-real-e2e", proof_status="observed", proved_at=CERTIFIED_AT),
    (18, 19): RuntimeProofProfile(source_angular_exact="18.2.14", target_angular_exact="19.2.25", target_cli_exact="19.2.27", node_exact="22.23.1", npm_exact="8.19.4", proof_source="dev-runtimes-real-e2e", proof_status="observed", proved_at=CERTIFIED_AT),
    (19, 20): RuntimeProofProfile(source_angular_exact="19.2.25", target_angular_exact="20.3.27", target_cli_exact="20.3.34", node_exact="22.23.1", npm_exact="8.19.4", proof_source="dev-runtimes-real-e2e", proof_status="observed", proved_at=CERTIFIED_AT),
    (20, 21): RuntimeProofProfile(source_angular_exact="20.3.27", target_angular_exact="21.2.19", target_cli_exact="21.2.20", node_exact="22.23.1", npm_exact="8.19.4", proof_source="dev-runtimes-real-e2e", proof_status="observed", proved_at=CERTIFIED_AT),
}

# Exact migration cohorts proven by the dev-runtimes real executions. Official
# supported ranges remain separate catalogue fields and are not replaced by
# these selected exact package versions.
PROVEN_TARGET_COHORTS: dict[tuple[int, int], tuple[str, str, str, str, str]] = {
    (11, 12): ("12.2.17", "12.2.18", "4.3.5", "6.6.7", "0.11.8"),
    (12, 13): ("13.3.12", "13.3.11", "4.6.4", "6.6.7", "0.11.8"),
    (13, 14): ("14.3.0", "14.2.13", "4.6.4", "6.6.7", "0.11.8"),
    (14, 15): ("15.2.10", "15.2.11", "4.9.5", "7.8.0", "0.12.0"),
    (15, 16): ("16.2.12", "16.2.16", "5.1.6", "6.6.7", "0.13.3"),
    (16, 17): ("17.3.12", "17.3.17", "5.4.5", "7.8.1", "0.14.4"),
}


class CompatibilityCatalogueProvider:
    """Load the active versioned catalogue independently of HTTP mutations.

    Since catalog-v4 no entry is certified from static seed data: official
    envelope ranges and observed evidence remain, while exact certification
    requires promoted immutable qualification evidence (P0-0).
    """

    CURRENT_VERSION = "catalog-v4"

    @staticmethod
    def source_runtime_constraints() -> dict[str, dict[int, tuple[str, ...]] | dict[int, tuple[str, str]]]:
        """Return source-family constraints shared by baseline resolution."""
        node_ranges = {major: tuple(ranges) for major, ranges in _NODE_RANGES.items()}
        typescript_ranges = {major: tuple(ranges) for major, ranges in _TYPESCRIPT_RANGES.items()}
        rxjs_ranges = {major: tuple(ranges) for major, ranges in _RXJS_RANGES.items()}
        return {
            "node_ranges": node_ranges,
            "typescript_ranges": typescript_ranges,
            "rxjs_ranges": rxjs_ranges,
        }

    @staticmethod
    def node_in_official_intersection(
        node_exact: str, source_ranges: tuple[str, ...], target_ranges: tuple[str, ...]
    ) -> bool:
        """Public envelope check reused by certification promotion."""
        return _node_in_intersection(node_exact, source_ranges, target_ranges)

    def load(self, version: str = CURRENT_VERSION) -> CompatibilityCatalogue:
        if version != self.CURRENT_VERSION and version not in {"catalog-v1", "catalog-v2", "catalog-v3"}:
            raise ValueError("unsupported compatibility catalogue version")
        if version in {"catalog-v1", "catalog-v2"}:
            return self._load_legacy(version)
        if version == "catalog-v3":
            return self._load_catalog_v3()
        entries = []
        for major in range(11, 21):
            entries.append(self._entry_for(major))
        catalogue = CompatibilityCatalogue.build(version, tuple(entries))
        _assert_current_catalogue_certification_truth(catalogue)
        return catalogue

    def _load_catalog_v3(self) -> CompatibilityCatalogue:
        """Preserve the exact historical v3 contract (certified 18-19/19-20/20-21)."""
        entries = tuple(self._historical_entry_for(major, (major, major + 1) in CERTIFIED_TRANSITIONS) for major in range(11, 21))
        return CompatibilityCatalogue.build("catalog-v3", entries)

    @classmethod
    def _historical_entry_for(cls, major: int, certified: bool) -> CompatibilityCatalogueEntry:
        target = major + 1
        cohort = PROVEN_TARGET_COHORTS.get((major, target))
        target_angular_exact, target_cli_exact, typescript_exact, rxjs_exact, zone_js_exact = (
            cohort
            if cohort is not None
            else (f"{target}.0.0", f"{target}.0.0", None, None, None)
        )
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
        source_node_ranges = _NODE_RANGES.get(major, ())
        target_node_ranges = _NODE_RANGES.get(target, ())
        raw_proven = DEV_RUNTIMES_PROVEN_PROFILES.get((major, target), ())
        proven_profiles = tuple(
            p for p in raw_proven if _node_in_intersection(p[0], source_node_ranges, target_node_ranges)
        )
        raw_evidence = DEV_RUNTIMES_PROVEN_EVIDENCE.get((major, target))
        if raw_evidence is not None and _node_in_intersection(raw_evidence.node_exact, source_node_ranges, target_node_ranges) and proven_profiles:
            proven_evidence: tuple[RuntimeProofProfile, ...] = (raw_evidence,)
        else:
            proven_evidence = ()
            if raw_evidence is not None and not _node_in_intersection(raw_evidence.node_exact, source_node_ranges, target_node_ranges):
                proven_profiles = ()
        return CompatibilityCatalogueEntry(
            stage_id=f"angular-{major}-to-{target}",
            source_family=f"angular-{major}.x",
            target_family=f"angular-{target}.x",
            target_angular_exact=target_angular_exact,
            target_cli_exact=target_cli_exact,
            typescript_exact=typescript_exact,
            typescript_minimum=ts_minimum,
            typescript_exclusive_maximum=ts_maximum,
            rxjs_exact=rxjs_exact,
            rxjs_minimum="6.5.3",
            rxjs_ranges=_RXJS_RANGES[target],
            zone_js_exact=zone_js_exact,
            node_major=node_major,
            npm_major=10,
            node_minimum=node_minimum,
            node_exact=node_exact,
            npm_exact=npm_exact,
            cli_exact=target_cli_exact,
            support_level=support_level,
            fixture_status=fixture_status,
            validation_policy_id="angular-stage-standard-v2",
            known_risks=() if certified else ("historical_fixture_evidence_incomplete",),
            validated_runtime_profiles=validated,
            source_node_ranges=source_node_ranges,
            target_node_ranges=target_node_ranges,
            proven_runtime_profiles=proven_profiles,
            proven_runtime_evidence=proven_evidence,
            proven_runtime_source="dev-runtimes-real-e2e" if proven_profiles else None,
            certification_status="certified" if certified else "seeded_official",
            certification_source="bridge-certification" if certified else "angular.dev/reference/versions",
            certified_at=CERTIFIED_AT if certified else None,
        )

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
    def _entry_for(cls, major: int) -> CompatibilityCatalogueEntry:
        target = major + 1
        cohort = PROVEN_TARGET_COHORTS.get((major, target))
        target_angular_exact, target_cli_exact, typescript_exact, rxjs_exact, zone_js_exact = (
            cohort
            if cohort is not None
            else (f"{target}.0.0", f"{target}.0.0", None, None, None)
        )
        node_minimum = _NODE_MINIMUMS[target]
        ts_minimum, ts_maximum = _TYPESCRIPT_RANGES[target]
        node_major = _node_major_for(node_minimum)
        validated = ()
        node_exact = None
        npm_exact = None
        source_node_ranges = _NODE_RANGES.get(major, ())
        target_node_ranges = _NODE_RANGES.get(target, ())
        # Stop promoting a DEV_RUNTIMES_PROVEN runtime when its exact Node falls
        # outside the official source/target intersection. Do not invent a
        # replacement merely to keep the entry populated.
        raw_proven = DEV_RUNTIMES_PROVEN_PROFILES.get((major, target), ())
        proven_profiles = tuple(
            p for p in raw_proven if _node_in_intersection(p[0], source_node_ranges, target_node_ranges)
        )
        raw_evidence = DEV_RUNTIMES_PROVEN_EVIDENCE.get((major, target))
        if raw_evidence is not None and _node_in_intersection(raw_evidence.node_exact, source_node_ranges, target_node_ranges) and proven_profiles:
            proven_evidence: tuple[RuntimeProofProfile, ...] = (raw_evidence,)
        else:
            proven_evidence = ()
            # evidence invalid => also drop profiles to keep them consistent
            if raw_evidence is not None and not _node_in_intersection(raw_evidence.node_exact, source_node_ranges, target_node_ranges):
                proven_profiles = ()
        return CompatibilityCatalogueEntry(
            stage_id=f"angular-{major}-to-{target}",
            source_family=f"angular-{major}.x",
            target_family=f"angular-{target}.x",
            target_angular_exact=target_angular_exact,
            target_cli_exact=target_cli_exact,
            typescript_exact=typescript_exact,
            typescript_minimum=ts_minimum,
            typescript_exclusive_maximum=ts_maximum,
            rxjs_exact=rxjs_exact,
            rxjs_minimum="6.5.3",
            rxjs_ranges=_RXJS_RANGES[target],
            zone_js_exact=zone_js_exact,
            node_major=node_major,
            npm_major=10,
            node_minimum=node_minimum,
            node_exact=node_exact,
            npm_exact=npm_exact,
            cli_exact=target_cli_exact,
            support_level="historical_experimental",
            fixture_status="incomplete",
            validation_policy_id="angular-stage-standard-v2",
            known_risks=("historical_fixture_evidence_incomplete",),
            validated_runtime_profiles=validated,
            source_node_ranges=source_node_ranges,
            target_node_ranges=target_node_ranges,
            proven_runtime_profiles=proven_profiles,
            proven_runtime_evidence=proven_evidence,
            proven_runtime_source="dev-runtimes-real-e2e" if proven_profiles else None,
            certification_status="seeded_official",
            certification_source="angular.dev/reference/versions",
            certified_at=None,
            evidence_classification="observed" if proven_evidence else "official_envelope",
        )


def _node_major_for(minimum: str) -> int:
    return int(minimum.split(".", 1)[0])


def _assert_current_catalogue_certification_truth(catalogue: CompatibilityCatalogue) -> None:
    """Current catalogues certify only through promoted immutable evidence."""
    for entry in catalogue.entries:
        if entry.certification_status != "certified":
            continue
        if entry.evidence_classification != "certified" or not entry.proven_runtime_evidence:
            raise ValueError("current catalogue entries cannot claim certification without promoted evidence")
        if any(proof.proof_status != "certified" or not proof.evidence_artifact_id or not proof.evidence_checksum for proof in entry.proven_runtime_evidence):
            raise ValueError("certified catalogue evidence must bind immutable artifacts")


def _satisfies_caret(version: Version, value: str) -> bool:
    if not value.startswith("^"):
        return False
    minimum = Version.parse(value[1:])
    return bool(minimum and version.at_least(minimum) and version.major == minimum.major)


def _satisfies_any(version: Version, ranges: tuple[str, ...]) -> bool:
    return any(_satisfies_caret(version, v) for v in ranges)


def _node_in_intersection(node_exact: str, source_ranges: tuple[str, ...], target_ranges: tuple[str, ...]) -> bool:
    ver = Version.parse(node_exact)
    if ver is None:
        return False
    return _satisfies_any(ver, source_ranges) and _satisfies_any(ver, target_ranges)
