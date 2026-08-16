"""Tests for F16 migration preflight checks."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.preflight_checks import PreflightCheckResult, aggregate_verdict
from app.main import app
from app.repositories.models import MigrationRunModel, MigrationStageModel, PreflightCheckResultModel
from app.repositories.session import session_scope
from app.services.preflight_check_service import PreflightCheckError, PreflightCheckService

NOW = datetime.now(UTC)
client = TestClient(app)


def _angular_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({
        "name": "app",
        "dependencies": {"@angular/core": "^18.2.0", "@angular/cli": "^18.0.1", "rxjs": "~7.8.1", "lodash": "^4.17.21"},
        "devDependencies": {"typescript": "~5.4.0"},
        "scripts": {"build": "ng build"},
    }))
    (root / "angular.json").write_text("{}")
    (root / "tsconfig.json").write_text("{}")
    (root / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {"": {}, "node_modules/lodash": {"version": "4.17.21"},
                     "node_modules/typescript": {"version": "5.4.5"},
                     "node_modules/rxjs": {"version": "7.8.1"},
                     "node_modules/zone.js": {"version": "0.14.0"},
                     "node_modules/@angular/core": {"version": "18.2.0"},
                     "node_modules/@angular/cli": {"version": "18.0.1"}},
    }))
    return root


def _seed(run_id: str, source: str = "angular-18.x", target: str = "angular-19.x") -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      source_version_family=source, target_version_family=target,
                                      created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(id=f"stage-{run_id}", run_id=run_id, stage_order=1,
                                        source_version_family=source, target_version_family=target,
                                        status="planned", created_at=NOW))
        session.commit()


def test_aggregate_verdict_deterministic():
    checks = [PreflightCheckResult(check_id="a", name="a", passed=True, detail="ok")]
    first = aggregate_verdict("run", checks)
    second = aggregate_verdict("run", checks)
    assert first.checksum == second.checksum
    assert first.status == "passed"
    blocked = aggregate_verdict("run", [PreflightCheckResult(check_id="a", name="a", passed=False, blockers=("B1",))])
    assert blocked.status == "blocked"
    assert blocked.blockers == ("B1",)


def test_run_checks_on_valid_project(tmp_path: Path):
    root = _angular_project(tmp_path)
    run_id = f"run-f16-{uuid4().hex[:8]}"
    _seed(run_id)
    verdict = PreflightCheckService().run_checks(run_id, root)
    assert verdict.status == "passed"
    assert {c.check_id for c in verdict.checks} == {"capability_readiness", "lockfile_compatibility", "dependency_compatibility"}
    assert all(c.passed for c in verdict.checks)


def test_run_checks_flags_malformed_lockfile(tmp_path: Path):
    root = _angular_project(tmp_path)
    (root / "package-lock.json").write_text("not valid json{{{")
    run_id = f"run-f16-{uuid4().hex[:8]}"
    _seed(run_id)
    verdict = PreflightCheckService().run_checks(run_id, root)
    lockfile_check = next(c for c in verdict.checks if c.check_id == "lockfile_compatibility")
    assert lockfile_check.passed is False
    assert "LOCKFILE_INVALID" in lockfile_check.blockers


def test_run_checks_blocks_on_capability_failure(tmp_path: Path):
    root = tmp_path / "bad"
    root.mkdir()
    (root / "package.json").write_text("invalid json")
    run_id = f"run-f16-{uuid4().hex[:8]}"
    _seed(run_id)
    verdict = PreflightCheckService().run_checks(run_id, root)
    assert verdict.status == "blocked"
    assert any("CAPABILITY" in b for b in verdict.blockers)


def test_persist_and_gate(tmp_path: Path):
    root = _angular_project(tmp_path)
    run_id = f"run-f16-{uuid4().hex[:8]}"
    _seed(run_id)
    service = PreflightCheckService()
    verdict = service.run_checks(run_id, root)
    row = service.persist(run_id, verdict)
    assert row.status == "passed"
    gated = service.gate_run_start(run_id)
    assert gated.id == row.id
    with session_scope() as session:
        assert session.query(PreflightCheckResultModel).filter_by(run_id=run_id).count() == 1


def test_gate_fails_closed_without_verdict(tmp_path: Path):
    run_id = f"run-f16-{uuid4().hex[:8]}"
    _seed(run_id)
    service = PreflightCheckService()
    try:
        service.gate_run_start(run_id)
        assert False, "expected PREFLIGHT_REQUIRED"
    except PreflightCheckError as exc:
        assert exc.code == "PREFLIGHT_REQUIRED"


def test_api_run_and_persist(tmp_path: Path):
    root = _angular_project(tmp_path)
    run_id = f"run-f16a-{uuid4().hex[:8]}"
    _seed(run_id)
    run = client.post(f"/runs/{run_id}/preflight/run", json={"source_root": str(root)})
    assert run.status_code == 200
    assert run.json()["status"] == "passed"
    assert len(run.json()["checks"]) == 3

    persisted = client.post(f"/runs/{run_id}/preflight/persist", json={"source_root": str(root)})
    assert persisted.status_code == 200

    gate = client.post(f"/runs/{run_id}/preflight/gate")
    assert gate.status_code == 200
    assert gate.json()["status"] == "passed"


def test_api_gate_blocks_without_verdict():
    run_id = f"run-f16b-{uuid4().hex[:8]}"
    _seed(run_id)
    gate = client.post(f"/runs/{run_id}/preflight/gate")
    assert gate.status_code == 404
    assert gate.json()["error_code"] == "PREFLIGHT_REQUIRED"
