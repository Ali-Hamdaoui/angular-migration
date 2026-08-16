"""Tests for F15 third-party compatibility scanner."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import MigrationRunModel, MigrationStageModel, ThirdPartyCompatibilityReportModel
from app.repositories.session import session_scope
from app.services.third_party_compatibility_service import (
    ThirdPartyCompatibilityError,
    ThirdPartyCompatibilityScanner,
)


NOW = datetime.now(UTC)
client = TestClient(app)


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({
        "dependencies": {
            "@angular/core": "^18.2.0",
            "@ngrx/store": "^17.0.0",
            "lodash": "^4.17.21",
            "express": "^4.19.0",
        },
        "devDependencies": {"jasmine-core": "~5.1.0"},
    }))
    (root / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {
            "": {"dependencies": {}},
            "node_modules/lodash": {"version": "4.17.21"},
            "node_modules/express": {"version": "4.19.2"},
            "node_modules/@ngrx/store": {"version": "17.0.0", "peerDependencies": {"@angular/core": "^17.0.0"}},
        },
    }))
    return root


def test_extract_inventory_excludes_angular_and_toolchain(tmp_path: Path):
    root = _workspace(tmp_path)
    inventory = ThirdPartyCompatibilityScanner().extract_inventory(root)
    names = {item.name for item in inventory}
    assert "@angular/core" not in names
    assert "jasmine-core" not in names
    assert {"lodash", "express", "@ngrx/store"} <= names
    by_name = {item.name: item for item in inventory}
    assert by_name["lodash"].resolved == "4.17.21"


def test_extract_inventory_missing_package_json(tmp_path: Path):
    scanner = ThirdPartyCompatibilityScanner()
    try:
        scanner.extract_inventory(tmp_path / "missing")
        assert False, "expected PACKAGE_JSON_MISSING"
    except ThirdPartyCompatibilityError as exc:
        assert exc.code == "PACKAGE_JSON_MISSING"


def _seed(stage_id: str) -> str:
    run_id = f"run-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized", created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(id=stage_id, run_id=run_id, stage_order=1,
                                        source_version_family="angular-18.x", target_version_family="angular-19.x",
                                        status="planned", created_at=NOW))
        session.commit()
    return run_id


def test_scan_stage_classifies_inventory(tmp_path: Path):
    root = _workspace(tmp_path)
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    report = ThirdPartyCompatibilityScanner().scan_stage(root, run_id=run_id, stage_id=stage_id)
    assert report.source_major == 18
    assert report.target_major == 19
    by_name = {f.name: f for f in report.findings}
    assert by_name["lodash"].status == "compatible"
    assert by_name["lodash"].resolved == "4.17.21"
    # @ngrx/store@17 peers @angular/core ^17 -> peer conflict for target 19
    assert by_name["@ngrx/store"].status == "peer_conflict"
    assert report.status == "blocked"
    assert "@ngrx/store" in report.blockers


def test_classify_peer_range_allowing_target_is_compatible(tmp_path: Path):
    root = tmp_path / "ws2"
    root.mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"@ngrx/store": "^18.0.0"}}))
    (root / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {"node_modules/@ngrx/store": {"version": "18.0.0", "peerDependencies": {"@angular/core": ">=18.0.0 <20.0.0"}}},
    }))
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    report = ThirdPartyCompatibilityScanner().scan_stage(root, run_id=run_id, stage_id=stage_id)
    by_name = {f.name: f for f in report.findings}
    assert by_name["@ngrx/store"].status == "compatible"
    assert report.status in {"compatible", "warnings"}


def test_classify_peer_range_excluding_target_is_peer_conflict(tmp_path: Path):
    root = tmp_path / "ws4"
    root.mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"@ngrx/store": "^18.0.0"}}))
    (root / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {"node_modules/@ngrx/store": {"version": "18.0.0", "peerDependencies": {"@angular/core": "^18.0.0"}}},
    }))
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    report = ThirdPartyCompatibilityScanner().scan_stage(root, run_id=run_id, stage_id=stage_id)
    finding = next(f for f in report.findings if f.name == "@ngrx/store")
    assert finding.status == "peer_conflict"
    assert report.status == "blocked"


def test_classify_unresolved_is_unknown_not_fabricated(tmp_path: Path):
    root = tmp_path / "ws3"
    root.mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"some-lib": "1.2.3"}}))
    (root / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {}}))
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    report = ThirdPartyCompatibilityScanner().scan_stage(root, run_id=run_id, stage_id=stage_id)
    finding = report.findings[0]
    assert finding.status == "unknown"
    assert finding.resolved is None


def test_scan_stage_unknown_stage_raises(tmp_path: Path):
    root = _workspace(tmp_path)
    scanner = ThirdPartyCompatibilityScanner()
    try:
        scanner.scan_stage(root, run_id="run", stage_id="missing")
        assert False, "expected STAGE_NOT_FOUND"
    except ThirdPartyCompatibilityError as exc:
        assert exc.code == "STAGE_NOT_FOUND"


def test_persist_and_list_report(tmp_path: Path):
    root = _workspace(tmp_path)
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    scanner = ThirdPartyCompatibilityScanner()
    report = scanner.scan_stage(root, run_id=run_id, stage_id=stage_id)
    row = scanner.persist(run_id, report)
    assert row.status == report.status
    assert len(row.inventory) >= 3
    listed = scanner.list_stage_reports(stage_id)
    assert len(listed) == 1
    with session_scope() as session:
        assert session.query(ThirdPartyCompatibilityReportModel).filter_by(stage_id=stage_id).count() == 1


def test_api_scan_and_report(tmp_path: Path):
    root = _workspace(tmp_path)
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    scanned = client.post(f"/runs/{run_id}/stages/{stage_id}/compatibility/scan", json={"workspace_path": str(root)})
    assert scanned.status_code == 200
    assert scanned.json()["target_major"] == 19
    assert any(f["name"] == "lodash" for f in scanned.json()["findings"])

    recorded = client.post(f"/runs/{run_id}/stages/{stage_id}/compatibility/reports", json={"workspace_path": str(root)})
    assert recorded.status_code == 200
    assert recorded.json()["stage_id"] == stage_id

    listed = client.get(f"/runs/{run_id}/stages/{stage_id}/compatibility/reports")
    assert listed.status_code == 200
    assert len(listed.json()["reports"]) == 1
