from datetime import UTC, datetime

import pytest

from app.domain.compatibility import (
    CompatibilityArtifact,
    CompatibilityCatalogue,
    CompatibilityCatalogueEntry,
    CompatibilityResolutionRequest,
)
from app.domain.execution_profile import RuntimeCandidate
from app.services.compatibility_application_service import (
    CompatibilityApplicationError,
    CompatibilityApplicationService,
    CompatibilityResolver,
)
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider


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


def test_current_catalogue_accepts_validated_node_22_profile_without_blocking_route():
    catalogue = CompatibilityCatalogueProvider().load()
    candidate = _candidate(profile_id="node-22-approved", node_exact="22.23.1", npm_exact="10.9.8", npx_exact="10.9.8")
    result = CompatibilityResolver(catalogue).resolve(_request(catalogue_version=catalogue.version, runtime_candidates=(candidate,)))

    assert result.status == "feasible_with_warnings"
    assert result.package.blockers == ()
    assert [stage.stage_id for stage in result.route] == ["angular-18-to-19", "angular-19-to-20", "angular-20-to-21"]
    assert result.selected_profile is not None
    assert result.selected_profile.node_exact == "22.23.1"
    assert result.selected_profile.npm_exact == "10.9.8"
    assert result.gate.status == "pending"


def test_current_catalogue_preserves_validated_node_20_profile():
    catalogue = CompatibilityCatalogueProvider().load()
    result = CompatibilityResolver(catalogue).resolve(_request(catalogue_version=catalogue.version))

    assert result.status == "feasible_with_warnings"
    assert result.selected_profile is not None
    assert result.selected_profile.node_exact == "20.11.1"
    assert result.selected_profile.npm_exact == "10.2.4"


def test_current_catalogue_rejects_nearby_unvalidated_node_22_profile():
    catalogue = CompatibilityCatalogueProvider().load()
    candidate = _candidate(node_exact="22.23.2", npm_exact="10.9.8", npx_exact="10.9.8")
    result = CompatibilityResolver(catalogue).resolve(_request(catalogue_version=catalogue.version, runtime_candidates=(candidate,)))

    assert result.status == "blocked"
    assert result.selected_profile is None
    assert "NO_COMPATIBLE_STAGE1_PROFILE" in result.package.blockers


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
