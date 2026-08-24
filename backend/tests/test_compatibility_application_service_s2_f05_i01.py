from datetime import UTC, datetime

import pytest

from app.domain.compatibility import (
    CompatibilityArtifact,
    CompatibilityCatalogue,
    CompatibilityCatalogueEntry,
    CompatibilityResolutionRequest,
)
from app.domain.execution_profile import RuntimeCandidate
from app.domain.runtime_compatibility import classify_runtime_versions
from app.services.compatibility_application_service import (
    CompatibilityApplicationError,
    CompatibilityApplicationService,
    CompatibilityResolver,
)
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.migration_route_service import MigrationRouteService


CHECKSUM = "sha256:" + "a" * 64


def _catalogue():
    return CompatibilityCatalogue.build(
        "catalog-v1",
        tuple(
            CompatibilityCatalogueEntry(
                stage_id=f"angular-{major}-to-{major + 1}",
                source_family=f"angular-{major}.x",
                target_family=f"angular-{major + 1}.x",
                target_angular_exact=f"{major + 1}.0.0",
                target_cli_exact=f"{major + 1}.0.0",
                node_major=20,
                npm_major=10,
                node_exact="20.11.1",
                npm_exact="10.2.4",
                support_level="historical_experimental",
                fixture_status="incomplete",
                validation_policy_id="angular-stage-standard-v2",
                known_risks=("historical_fixture_evidence_incomplete",),
            )
            for major in range(18, 21)
        ),
    )


def _candidate(available=True, **changes):
    values = {
        "profile_id": "node-20-approved",
        "node_executable": r"C:\Tools\node\node.exe",
        "node_exact": "20.11.1",
        "npm_executable": r"C:\Tools\node\npm.cmd",
        "npm_exact": "10.2.4",
        "npx_executable": r"C:\Tools\node\npx.cmd",
        "npx_exact": "10.2.4",
        "available": available,
    }
    values.update(changes)
    return RuntimeCandidate(**values)


def _request(**updates):
    values = {
        "run_id": "run-1",
        "expected_state_version": 3,
        "idempotency_key": "resolve-1",
        "actor": "operator",
        "source_angular_exact": "18.2.4",
        "catalogue_version": "catalog-v1",
        "runtime_candidates": (_candidate(),),
        "resolved_at": datetime.now(UTC),
    }
    values.update(updates)
    return CompatibilityResolutionRequest(**values)


def test_resolves_deterministic_ladder_and_checksum_bound_stage1_profile():
    result = CompatibilityResolver(_catalogue()).resolve(_request())

    assert result.status == "feasible_with_warnings"
    assert [stage.stage_id for stage in result.route] == ["angular-18-to-19", "angular-19-to-20", "angular-20-to-21"]
    assert result.support_level == "historical_experimental"
    assert result.selected_profile is not None
    assert result.selected_profile.angular_exact == "19.0.0"
    assert result.selected_profile.checksum.startswith("sha256:")
    assert result.gate.gate_id == "G05"
    assert result.gate.status == "pending"


def test_accepts_node_runtime_versions_with_the_standard_v_prefix():
    result = CompatibilityResolver(_catalogue()).resolve(_request(runtime_candidates=(_candidate(node_exact="v20.11.1"),)))

    assert result.selected_profile is not None


def test_current_catalogue_accepts_certified_node_18_profile_without_blocking_route():
    catalogue = CompatibilityCatalogueProvider().load()
    candidate = _candidate(profile_id="node-18-certified", node_exact="18.20.8", npm_exact="10.8.2", npx_exact="10.8.2")
    result = CompatibilityResolver(catalogue).resolve(_request(catalogue_version=catalogue.version, runtime_candidates=(candidate,)))

    assert result.status in {"feasible", "feasible_with_warnings"}
    assert result.package.blockers == ()
    assert [stage.stage_id for stage in result.route] == ["angular-18-to-19", "angular-19-to-20", "angular-20-to-21"]
    assert result.selected_profile is not None
    assert result.selected_profile.node_exact == "18.20.8"
    assert result.selected_profile.npm_exact == "10.8.2"
    assert result.gate.status == "pending"


def test_current_catalogue_preserves_certified_node_18_profile():
    catalogue = CompatibilityCatalogueProvider().load()
    candidate = _candidate(profile_id="node-18-certified", node_exact="18.20.8", npm_exact="10.8.2", npx_exact="10.8.2")
    result = CompatibilityResolver(catalogue).resolve(_request(catalogue_version=catalogue.version, runtime_candidates=(candidate,)))

    assert result.status in {"feasible", "feasible_with_warnings"}
    assert result.selected_profile is not None
    assert result.selected_profile.node_exact == "18.20.8"
    assert result.selected_profile.npm_exact == "10.8.2"


def test_current_catalogue_accepts_unvalidated_node_22_profile_by_official_range():
    catalogue = CompatibilityCatalogueProvider().load()
    candidate = _candidate(node_exact="22.23.2", npm_exact="10.9.8", npx_exact="10.9.8")
    result = CompatibilityResolver(catalogue).resolve(_request(catalogue_version=catalogue.version, runtime_candidates=(candidate,)))

    assert result.status in {"feasible", "feasible_with_warnings"}
    assert result.selected_profile is not None
    assert result.selected_profile.classification == "RANGE_COMPATIBLE"


def test_current_catalogue_accepts_windows_node_22_as_range_compatible():
    catalogue = CompatibilityCatalogueProvider().load()
    candidate = _candidate(profile_id="node-22-range", node_exact="22.23.1", npm_exact="10.9.8", npx_exact="10.9.8")
    result = CompatibilityResolver(catalogue).resolve(_request(catalogue_version=catalogue.version, runtime_candidates=(candidate,)))

    assert result.status in {"feasible", "feasible_with_warnings"}
    assert result.package.blockers == ()
    assert result.selected_profile is not None
    assert result.selected_profile.classification == "RANGE_COMPATIBLE"


def test_current_catalogue_accepts_angular_11_baseline_node12_with_paired_npm6():
    catalogue = CompatibilityCatalogueProvider().load()
    candidate = _candidate(
        profile_id="node-12-range",
        node_exact="12.22.12",
        npm_exact="6.14.16",
        npx_exact="6.14.16",
    )
    result = CompatibilityResolver(catalogue).resolve(_request(
        source_angular_exact="11.0.4",
        catalogue_version=catalogue.version,
        runtime_candidates=(candidate,),
    ))

    assert result.status == "feasible_with_warnings"
    assert result.package.blockers == ()
    assert result.selected_profile is not None
    assert result.selected_profile.classification == "RANGE_COMPATIBLE"


def test_node_22_range_is_compatible_for_every_route_stage():
    catalogue = CompatibilityCatalogueProvider().load()
    for source, target in ((18, 19), (19, 20), (20, 21)):
        entry = catalogue.entry_for(f"angular-{source}.x", f"angular-{target}.x")
        assert entry is not None
        assert classify_runtime_versions(
            node_exact="22.23.1", npm_exact="10.9.8", npx_exact="10.9.8",
            validated_runtime_profiles=entry.validated_runtime_profiles,
            source_node_ranges=entry.source_node_ranges,
            target_node_ranges=entry.target_node_ranges,
        ) == "RANGE_COMPATIBLE"


def test_runtime_range_policy_fails_closed_for_incompatible_and_incomplete_candidates():
    catalogue = CompatibilityCatalogueProvider().load()
    entry = catalogue.entry_for("angular-19.x", "angular-20.x")
    assert entry is not None
    for values in (
        {"node_exact": "16.20.2", "npm_exact": "8.19.4", "npx_exact": "8.19.4"},
        {"node_exact": "18.20.8", "npm_exact": "10.8.2", "npx_exact": "10.8.2"},
        {"node_exact": "not-a-version", "npm_exact": "10.9.8", "npx_exact": "10.9.8"},
        {"node_exact": "22.23.1", "npm_exact": "", "npx_exact": "10.9.8"},
    ):
        assert classify_runtime_versions(
            **values,
            validated_runtime_profiles=entry.validated_runtime_profiles,
            source_node_ranges=entry.source_node_ranges,
            target_node_ranges=entry.target_node_ranges,
        ) == "UNSUPPORTED"


def test_runtime_governance_rejects_mismatched_npm_and_npx_pair():
    catalogue = CompatibilityCatalogueProvider().load()
    candidate = _candidate(node_exact="12.22.12", npm_exact="6.14.16", npx_exact="10.9.8")
    result = CompatibilityResolver(catalogue).resolve(_request(
        source_angular_exact="11.0.4",
        catalogue_version=catalogue.version,
        runtime_candidates=(candidate,),
    ))
    assert result.status == "blocked"
    assert "NO_COMPATIBLE_STAGE1_PROFILE" in result.package.blockers


def _node12_npm8_candidate():
    return _candidate(
        profile_id="runtime-node12",
        node_exact="12.22.12",
        npm_exact="8.19.4",
        npx_exact="8.19.4",
    )


def _node12_npm8_request(**updates):
    catalogue = CompatibilityCatalogueProvider().load()
    return _request(
        source_angular_exact="11.0.4",
        catalogue_version=catalogue.version,
        runtime_candidates=(_node12_npm8_candidate(),),
        **updates,
    )


def test_production_range_compatible_blocks_with_stage_runtime_certification_required():
    result = CompatibilityResolver(CompatibilityCatalogueProvider().load()).resolve(_node12_npm8_request())

    assert result.selected_profile is not None
    assert result.selected_profile.classification == "RANGE_COMPATIBLE"
    assert result.status == "blocked"
    assert "STAGE_RUNTIME_CERTIFICATION_REQUIRED" in result.package.blockers


def test_qualification_range_compatible_is_allowed():
    result = CompatibilityResolver(CompatibilityCatalogueProvider().load()).resolve(
        _node12_npm8_request(run_mode="QUALIFICATION")
    )

    assert result.status == "feasible_with_warnings"
    assert "STAGE_RUNTIME_CERTIFICATION_REQUIRED" not in result.package.blockers
    assert result.selected_profile is not None
    assert result.selected_profile.classification == "RANGE_COMPATIBLE"
    assert result.gate.status == "pending"


def test_production_exact_certified_is_allowed():
    entries = tuple(
        entry.model_copy(update={"validated_runtime_profiles": (("20.11.1", "10.2.4"),)})
        for entry in _catalogue().entries
    )
    catalogue = CompatibilityCatalogue.build("catalog-v1", entries)
    candidate = _candidate()
    result = CompatibilityResolver(catalogue).resolve(_request(
        source_angular_exact="18.2.4",
        catalogue_version=catalogue.version,
        runtime_candidates=(candidate,),
    ))

    assert result.selected_profile is not None
    assert result.selected_profile.classification == "EXACT_CERTIFIED"
    assert result.status in {"feasible", "feasible_with_warnings"}
    assert result.package.blockers == ()


def test_qualification_does_not_modify_certification_state():
    resolver = CompatibilityResolver(CompatibilityCatalogueProvider().load())
    result = resolver.resolve(_node12_npm8_request(run_mode="QUALIFICATION"))

    assert result.selected_profile is not None
    assert result.selected_profile.classification == "RANGE_COMPATIBLE"
    assert result.selected_profile.classification != "EXACT_CERTIFIED"


def test_service_replays_identical_idempotent_request_and_rejects_payload_reuse():
    service = CompatibilityApplicationService(resolver=CompatibilityResolver(_catalogue()))
    request = _request()

    first = service.resolve(request)
    replay = service.resolve(request)
    assert replay.idempotent_replay is True
    assert replay.package.package_checksum == first.package.package_checksum

    with pytest.raises(CompatibilityApplicationError) as error:
        service.resolve(request.model_copy(update={"source_angular_exact": "18.2.5"}))
    assert error.value.code == "IDEMPOTENCY_PAYLOAD_MISMATCH"


def test_stale_state_and_prerequisite_checksum_fail_before_resolution():
    service = CompatibilityApplicationService(
        resolver=CompatibilityResolver(_catalogue()),
        state_version_reader=lambda _: 4,
        artifact_reader=lambda _: "sha256:" + "b" * 64,
    )
    with pytest.raises(CompatibilityApplicationError) as stale:
        service.resolve(_request())
    assert stale.value.code == "STALE_STATE_VERSION"

    service = CompatibilityApplicationService(
        resolver=CompatibilityResolver(_catalogue()),
        artifact_reader=lambda _: "sha256:" + "b" * 64,
    )
    with pytest.raises(CompatibilityApplicationError) as mismatch:
        service.resolve(_request(prerequisite_artifacts=(CompatibilityArtifact(artifact_id="input", checksum=CHECKSUM),)))
    assert mismatch.value.code == "PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH"


def test_unsupported_family_and_unavailable_runtime_fail_closed():
    resolver = CompatibilityResolver(_catalogue())
    unsupported = resolver.resolve(_request(source_angular_exact="17.3.0"))
    assert unsupported.status == "blocked"
    assert "SOURCE_FAMILY_UNSUPPORTED" in unsupported.package.blockers
    unavailable = resolver.resolve(_request(runtime_candidates=(_candidate(available=False),)))
    assert unavailable.status == "blocked"
    assert "NO_COMPATIBLE_STAGE1_PROFILE" in unavailable.package.blockers


def test_g05_uses_generic_adjacent_route_for_arbitrary_target():
    catalogue = CompatibilityCatalogueProvider().load()
    result = CompatibilityResolver(catalogue).resolve(
        _request(source_angular_exact="13.2.7", target_family="18.x", catalogue_version=catalogue.version)
    )

    assert [stage.stage_id for stage in result.route] == [
        "angular-13-to-14",
        "angular-14-to-15",
        "angular-15-to-16",
        "angular-16-to-17",
        "angular-17-to-18",
    ]
    assert result.target_family == "angular-18.x"


def test_angular_14_to_15_uses_the_proven_exact_target_cohort():
    entry = next(
        item
        for item in CompatibilityCatalogueProvider().load().entries
        if item.stage_id == "angular-14-to-15"
    )

    assert entry.target_angular_exact == "15.2.10"
    assert entry.target_cli_exact == "15.2.11"
    assert entry.target_cohort() == {
        "@angular/animations": "15.2.10",
        "@angular/common": "15.2.10",
        "@angular/compiler": "15.2.10",
        "@angular/compiler-cli": "15.2.10",
        "@angular/core": "15.2.10",
        "@angular/forms": "15.2.10",
        "@angular/platform-browser": "15.2.10",
        "@angular/platform-browser-dynamic": "15.2.10",
        "@angular/router": "15.2.10",
        "@angular/cli": "15.2.11",
        "@angular-devkit/build-angular": "15.2.11",
        "typescript": "4.9.5",
        "rxjs": "7.8.0",
        "zone.js": "0.12.0",
    }


@pytest.mark.parametrize(
    ("source", "target", "count"),
    [("11.2.14", "angular-21.x", 10), ("20.3.27", "angular-21.x", 1)],
)
def test_g05_route_matches_migration_route_authority(source, target, count):
    catalogue = CompatibilityCatalogueProvider().load()
    result = CompatibilityResolver(catalogue).resolve(
        _request(source_angular_exact=source, target_family=target, catalogue_version=catalogue.version)
    )
    authority = MigrationRouteService().compute(
        int(source.split(".")[0]),
        int(target.removeprefix("angular-").removesuffix(".x")),
        catalogue=catalogue,
    )

    assert len(result.route) == count
    assert [(stage.source_family, stage.target_family) for stage in result.route] == [
        (stage.source_family, stage.target_family) for stage in authority.stages
    ]


def test_g05_canonicalizes_short_target_family():
    request = _request(target_family="21.x", catalogue_version="catalog-v3")
    assert request.target_family == "angular-21.x"
    result = CompatibilityResolver(CompatibilityCatalogueProvider().load()).resolve(request)
    assert len(result.route) == 3


@pytest.mark.parametrize(
    ("source", "target", "blocker"),
    [
        ("10.0.0", "angular-21.x", "SOURCE_FAMILY_UNSUPPORTED"),
        ("11.0.0", "angular-11.x", "TARGET_MUST_BE_GREATER_THAN_SOURCE"),
        ("18.0.0", "angular-17.x", "TARGET_MUST_BE_GREATER_THAN_SOURCE"),
        ("not-a-version", "angular-21.x", "SOURCE_FAMILY_UNSUPPORTED"),
    ],
)
def test_g05_rejects_invalid_source_target_pairs(source, target, blocker):
    result = CompatibilityResolver(CompatibilityCatalogueProvider().load()).resolve(
        _request(source_angular_exact=source, target_family=target, catalogue_version="catalog-v3")
    )
    assert result.status == "blocked"
    assert blocker in result.package.blockers


def test_g05_rejects_malformed_target():
    with pytest.raises(ValueError):
        _request(target_family="angular-21")


def test_g05_reports_missing_catalogue_transition():
    catalogue = CompatibilityCatalogue.build("catalog-v1", (_catalogue().entries[0], _catalogue().entries[2]))
    result = CompatibilityResolver(catalogue).resolve(
        _request(target_family="angular-21.x", catalogue_version=catalogue.version)
    )
    assert result.status == "blocked"
    assert "CATALOGUE_ROUTE_MISSING_19_20" in result.package.blockers


def test_direct_public_registry_without_proxy_is_accepted():
    result = CompatibilityResolver(_catalogue()).resolve(_request(runtime_candidates=(_candidate(proxy_configured=False),)))
    assert result.status == "feasible_with_warnings"
    assert result.selected_profile is not None


def test_registry_unavailable_remains_blocked():
    result = CompatibilityResolver(_catalogue()).resolve(_request(runtime_candidates=(_candidate(registry_configured=False),)))
    assert result.status == "blocked"
    assert "NO_COMPATIBLE_STAGE1_PROFILE" in result.package.blockers


def test_catalogue_rejects_unproven_historical_validated_claim():
    with pytest.raises(ValueError):
        CompatibilityCatalogueEntry(
            stage_id="angular-18-to-19",
            source_family="angular-18.x",
            target_family="angular-19.x",
            target_angular_exact="19.0.0",
            target_cli_exact="19.0.0",
            node_major=20,
            npm_major=10,
            support_level="historical_validated",
            fixture_status="incomplete",
            validation_policy_id="policy-v1",
        )
