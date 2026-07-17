import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes.source_analysis import get_source_analysis_service
from app.main import app

from app.domain.source_analysis import SourceAnalysisRequest
from app.services.source_analysis_service import SourceAnalysisService


def test_analyze_reads_versions_lockfile_and_topology(tmp_path: Path):
    source = tmp_path / "app"
    source.mkdir()
    (source / "package.json").write_text(json.dumps({
        "dependencies": {"@angular/core": "^18.2.0", "rxjs": "^7.8.0"},
        "devDependencies": {"@angular/cli": "^18.2.0", "typescript": "~5.5.0"},
    }), encoding="utf-8")
    (source / "package-lock.json").write_text(json.dumps({
        "packages": {
            "": {},
            "node_modules/@angular/core": {"version": "18.2.3"},
            "node_modules/@angular/cli": {"version": "18.2.3"},
            "node_modules/rxjs": {"version": "7.8.1"},
            "node_modules/typescript": {"version": "5.5.4"},
        }
    }), encoding="utf-8")
    (source / "angular.json").write_text(json.dumps({"projects": {"app": {"projectType": "application"}}}), encoding="utf-8")

    result = SourceAnalysisService().analyze(SourceAnalysisRequest(
        source_path=str(source), idempotency_key="analysis-1"
    ))

    assert result.snapshot.status == "accepted"
    assert result.snapshot.package_manager == "npm"
    assert result.snapshot.topology.projects == ["app"]
    assert next(item for item in result.snapshot.versions if item.package == "@angular/core").resolved == "18.2.3"


def test_analyze_blocks_missing_lockfile_and_unsupported_angular(tmp_path: Path):
    source = tmp_path / "app"
    source.mkdir()
    (source / "package.json").write_text(json.dumps({"dependencies": {"@angular/core": "^10.2.0"}}), encoding="utf-8")

    result = SourceAnalysisService().analyze(SourceAnalysisRequest(
        source_path=str(source), idempotency_key="analysis-2"
    ))

    assert result.snapshot.status == "blocked"
    assert "NPM_LOCKFILE_MISSING" in result.snapshot.blockers
    assert "ANGULAR_VERSION_UNSUPPORTED" in result.snapshot.blockers

def test_source_analysis_routes_are_registered_and_use_the_typed_contract(tmp_path: Path):
    source = tmp_path / "app"
    source.mkdir()
    (source / "package.json").write_text(json.dumps({"dependencies": {"@angular/core": "^18.2.0"}}), encoding="utf-8")
    (source / "package-lock.json").write_text(json.dumps({"packages": {"node_modules/@angular/core": {"version": "18.2.3"}}}), encoding="utf-8")

    class Service:
        def analyze(self, request: SourceAnalysisRequest):
            return SourceAnalysisService().analyze(request)

        def get(self, analysis_id: str):
            return None

    app.dependency_overrides[get_source_analysis_service] = Service
    try:
        with TestClient(app) as client:
            for prefix in ("", "/api/v1"):
                response = client.post(f"{prefix}/sources/analyze", json={
                    "source_path": str(source),
                    "idempotency_key": f"route-analysis-{prefix or 'legacy'}",
                    "actor": "test",
                })
                assert response.status_code == 200
                assert response.json()["snapshot"]["status"] == "review_required"
            paths = client.get("/openapi.json").json()["paths"]
            assert "/sources/analyze" in paths
            assert "/api/v1/sources/analyze" in paths
    finally:
        app.dependency_overrides.clear()
