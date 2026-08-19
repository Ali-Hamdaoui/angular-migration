from types import SimpleNamespace

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
