"""Tests for F13 project capability model."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import MigrationRunModel, ProjectCapabilityModel
from app.repositories.session import session_scope
from app.services.project_capability_service import ProjectCapabilityError, ProjectCapabilityService

NOW = datetime.now(UTC)
client = TestClient(app)


def _angular_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir(parents=True)
    (root / "package.json").write_text(
        json.dumps({
            "name": "app",
            "dependencies": {"@angular/core": "^18.2.0", "@angular/cli": "^18.0.1", "rxjs": "~7.8.1", "zone.js": "~0.14.0"},
            "devDependencies": {"typescript": "~5.4.0"},
            "scripts": {"build": "ng build", "test": "ng test"},
        })
    )
    (root / "angular.json").write_text("{}")
    (root / "tsconfig.json").write_text("{}")
    (root / "package-lock.json").write_text("{}")
    return root


def test_derive_capabilities_from_angular_project(tmp_path: Path):
    root = _angular_project(tmp_path)
    capabilities = {c.key: c.value for c in ProjectCapabilityService().derive(root)}
    assert capabilities["angular_core"] == "18.2.0"
    assert capabilities["angular_cli"] == "18.0.1"
    assert capabilities["typescript"] == "5.4.0"
    assert capabilities["rxjs"] == "7.8.1"
    assert capabilities["workspace_type"] == "single_application"
    assert capabilities["build_script"] == "present"
    assert capabilities["lockfile"] == "package-lock"


def test_derive_package_and_lockfile_capabilities(tmp_path: Path):
    root = _angular_project(tmp_path)
    package = json.loads((root / "package.json").read_text())
    package["devDependencies"].update({"tslint": "^6.1.0", "codelyzer": "^6.0.0", "@angular-eslint/eslint-plugin": "^13.0.0"})
    (root / "package.json").write_text(json.dumps(package))
    (root / "package-lock.json").write_text(json.dumps({"lockfileVersion": 1, "dependencies": {}}))
    capabilities = {c.key: c.value for c in ProjectCapabilityService().derive(root)}
    assert capabilities["package:tslint"] == "present"
    assert capabilities["package:codelyzer"] == "present"
    assert capabilities["package:angular-eslint"] == "present"
    assert capabilities["lockfile_format:v1"] == "present"


def test_derive_capabilities_missing_project(tmp_path: Path):
    capabilities = ProjectCapabilityService().derive(tmp_path / "missing")
    assert capabilities[0].key == "source_root"
    assert capabilities[0].value == "missing"
    # missing package.json in an existing dir
    root = tmp_path / "empty"
    root.mkdir()
    capabilities = ProjectCapabilityService().derive(root)
    assert capabilities[0].key == "package_json"
    assert capabilities[0].value == "missing"


def test_readiness_verdict():
    service = ProjectCapabilityService()
    ok = [{"key": "package_json", "value": "present"}, {"key": "angular_core", "value": "18.2.0"}, {"key": "workspace_type", "value": "single_application"}]
    status, blockers = service.readiness(ok)
    assert status == "ready" and blockers == []
    bad = [{"key": "package_json", "value": "invalid"}]
    status, blockers = service.readiness(bad)
    assert status == "blocked" and "CAPABILITY_PACKAGE_JSON_UNAVAILABLE" in blockers


def test_snapshot_and_persist(tmp_path: Path):
    root = _angular_project(tmp_path)
    run_id = f"run-f13-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized", created_at=NOW, updated_at=NOW))
        session.commit()
    service = ProjectCapabilityService()
    snapshot = service.snapshot(run_id, root, stage_id="stage-1")
    assert snapshot.angular_major == 18
    assert snapshot.checksum.startswith("sha256:")
    assert len(snapshot.capabilities) >= 12
    with session_scope() as session:
        assert session.query(ProjectCapabilityModel).filter_by(run_id=run_id).count() == 1


def test_snapshot_unknown_run_raises(tmp_path: Path):
    root = _angular_project(tmp_path)
    service = ProjectCapabilityService()
    try:
        service.snapshot("run-missing", root)
        assert False, "expected RUN_NOT_FOUND"
    except ProjectCapabilityError as exc:
        assert exc.code == "RUN_NOT_FOUND"


def test_capability_api(tmp_path: Path):
    root = _angular_project(tmp_path)
    run_id = f"run-f13a-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized", created_at=NOW, updated_at=NOW))
        session.commit()
    response = client.post(f"/runs/{run_id}/capabilities", json={"source_root": str(root)})
    assert response.status_code == 200
    body = response.json()
    assert body["angular_major"] == 18
    assert body["checksum"].startswith("sha256:")
    assert any(c["key"] == "build_script" for c in body["capabilities"])

    listed = client.get(f"/runs/{run_id}/capabilities")
    assert listed.status_code == 200
    assert len(listed.json()["snapshots"]) == 1
