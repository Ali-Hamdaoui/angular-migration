from datetime import UTC, datetime
from types import SimpleNamespace

from app.api.compatibility_contracts import FeasibilityCreateRequest
from app.domain.compatibility import CompatibilityArtifact
from app.services.compatibility_application_service import CompatibilityResolver
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.compatibility_evidence_application_service import CompatibilityEvidenceApplicationService
from app.services.planning_input_resolver import PlanningInputResolver


class Session:
    def __init__(self, analysis):
        self.analysis = analysis

    def get(self, model, key):
        return SimpleNamespace(binding={"source_analysis_id": "analysis-1"}) if model.__name__ == "PreflightModel" else self.analysis


def test_source_version_resolution_accepts_single_declared_semver_range_from_legacy_evidence():
    run = SimpleNamespace(source_version_detected=None, preflight_id="preflight-1", source_version_family=None)
    analysis = SimpleNamespace(snapshot={"versions": [{"package": "@angular/core", "declared": "~11.0.4", "resolved": None}]})

    assert PlanningInputResolver._exact_source_from_evidence(Session(analysis), run) == "11.0.4"
    assert run.source_version_family == "angular-11.x"


def test_single_version_resolution_rejects_broad_ranges():
    assert PlanningInputResolver._single_version(">=11.0.0 <12.0.0") is None


def _feasibility_payload(run_mode="PRODUCTION"):
    return FeasibilityCreateRequest(
        expected_state_version=3,
        idempotency_key="feasibility:auto:job-1",
        source_angular_exact="11.0.4",
        catalogue_version="catalog-v4",
        registry_snapshot_id="registry-snapshot-v1",
        registry_snapshot_checksum="sha256:" + "0" * 64,
        prerequisite_artifacts=[CompatibilityArtifact(artifact_id="artifact-1", checksum="sha256:" + "a" * 64)],
        run_mode=run_mode,
    )


def _evidence_request(payload):
    service = CompatibilityEvidenceApplicationService(
        resolver=CompatibilityResolver(CompatibilityCatalogueProvider().load()),
        now_provider=lambda: datetime.now(UTC),
    )
    return service._request("run-1", payload, "operator", datetime.now(UTC))


def test_a_missing_run_mode_defaults_to_production():
    run = SimpleNamespace(run_policy_snapshot={"input_checksum": "sha256:in", "artifact_set_checksum": "sha256:as", "gate_version": "g05-v1"})

    assert PlanningInputResolver._run_mode(run) == "PRODUCTION"
    assert _evidence_request(_feasibility_payload()).run_mode == "PRODUCTION"


def test_b_qualification_run_mode_reaches_compatibility_resolution_request():
    run = SimpleNamespace(run_policy_snapshot={"input_checksum": "sha256:in", "artifact_set_checksum": "sha256:as", "gate_version": "g05-v1", "run_mode": "QUALIFICATION"})

    assert PlanningInputResolver._run_mode(run) == "QUALIFICATION"
    assert _evidence_request(_feasibility_payload(run_mode="QUALIFICATION")).run_mode == "QUALIFICATION"