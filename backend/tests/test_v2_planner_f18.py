"""Tests for F18 V2 analyzer and planner."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import MigrationRunModel, V2PlanningModel
from app.repositories.session import session_scope
from app.services.v2_planner_service import V2PlannerService, V2PlanningError

NOW = datetime.now(UTC)
client = TestClient(app)


def _seed(run_id: str, source: str = "angular-11.x", target: str = "angular-16.x") -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      source_version_family=source, target_version_family=target,
                                      created_at=NOW, updated_at=NOW))
        session.commit()


def test_derive_plan_for_any_source_target():
    run_id = f"run-f18-{uuid4().hex[:8]}"
    _seed(run_id, "angular-11.x", "angular-16.x")
    plan = V2PlannerService().derive_plan(run_id)
    assert plan.source_major == 11
    assert plan.target_major == 16
    assert len(plan.stages) == 5
    assert plan.checksum.startswith("sha256:")
    assert all(stage.node_minimum for stage in plan.stages)
    assert plan.stages[0].target_family == "angular-12.x"


def test_plan_is_deterministic():
    run_id = f"run-f18-{uuid4().hex[:8]}"
    _seed(run_id)
    service = V2PlannerService()
    first = service.derive_plan(run_id)
    second = service.derive_plan(run_id)
    assert first.checksum == second.checksum
    assert first.model_dump() == second.model_dump()


def test_analyze_produces_findings():
    run_id = f"run-f18-{uuid4().hex[:8]}"
    _seed(run_id)
    findings = V2PlannerService().analyze(run_id)
    assert any(f.finding_id == "route_derived" for f in findings)


def test_analyze_with_source_root():
    run_id = f"run-f18-{uuid4().hex[:8]}"
    _seed(run_id)
    root = Path(f"/tmp/f18-{uuid4().hex[:6]}")
    root.mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"@angular/core": "^11.0.0"}}))
    findings = V2PlannerService().analyze(run_id, root)
    assert any(f.finding_id in {"capability_ready", "capability_blockers"} for f in findings)


def test_plan_stage_knowledge_changes_with_observed_capabilities(tmp_path: Path):
    run_id = f"run-f18-cap-{uuid4().hex[:8]}"
    _seed(run_id, "angular-11.x", "angular-13.x")
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "package.json").write_text(json.dumps({
        "dependencies": {"@angular/core": "^11.0.0"},
        "devDependencies": {"tslint": "^6.1.0", "codelyzer": "^6.0.0"},
    }))
    (legacy / "angular.json").write_text("{}")
    (legacy / "package-lock.json").write_text(json.dumps({"lockfileVersion": 1, "dependencies": {}}))
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "package.json").write_text(json.dumps({"dependencies": {"@angular/core": "^11.0.0"}}))
    (clean / "angular.json").write_text("{}")
    (clean / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {}}))

    service = V2PlannerService()
    legacy_plan = service.derive_plan(run_id, legacy)
    clean_plan = service.derive_plan(run_id, clean)
    legacy_changes = {
        (item["package"], item["action"])
        for stage in legacy_plan.stages
        for item in stage.expected_dependency_changes
    }
    clean_changes = {
        (item["package"], item["action"])
        for stage in clean_plan.stages
        for item in stage.expected_dependency_changes
    }
    assert ("tslint", "remove") in legacy_changes
    assert ("codelyzer", "remove") in legacy_changes
    assert ("package-lock", "use-legacy-parser") in legacy_changes
    assert ("tslint", "remove") not in clean_changes
    assert ("package-lock", "use-legacy-parser") not in clean_changes
    assert legacy_plan.checksum != clean_plan.checksum


def test_validation_reloads_the_immutable_capability_snapshot(tmp_path: Path):
    run_id = f"run-f18-snapshot-{uuid4().hex[:8]}"
    _seed(run_id, "angular-11.x", "angular-13.x")
    root = tmp_path / "project"
    root.mkdir()
    package = {"dependencies": {"@angular/core": "^11.0.0"}}
    (root / "package.json").write_text(json.dumps(package))
    (root / "angular.json").write_text("{}")

    service = V2PlannerService()
    original = service.derive_plan(run_id, root)
    service.persist(run_id, original)

    package["devDependencies"] = {"tslint": "^6.1.0"}
    (root / "package.json").write_text(json.dumps(package))
    validated = service.validate_plan(run_id)
    assert validated.checksum == original.checksum
    assert validated.capability_snapshot_id == original.capability_snapshot_id
    changed = service.derive_plan(run_id, root)
    assert changed.checksum != original.checksum


def test_angular_eslint_rule_requires_angular_eslint_capability(tmp_path: Path):
    run_id = f"run-f18-eslint-{uuid4().hex[:8]}"
    _seed(run_id, "angular-12.x", "angular-13.x")
    with_eslint = tmp_path / "with-eslint"
    with_eslint.mkdir()
    (with_eslint / "package.json").write_text(json.dumps({
        "dependencies": {"@angular/core": "^12.0.0"},
        "devDependencies": {"@angular-eslint/eslint-plugin": "^12.0.0"},
    }))
    (with_eslint / "angular.json").write_text("{}")
    without_eslint = tmp_path / "without-eslint"
    without_eslint.mkdir()
    (without_eslint / "package.json").write_text(json.dumps({"dependencies": {"@angular/core": "^12.0.0"}}))
    (without_eslint / "angular.json").write_text("{}")
    service = V2PlannerService()
    with_changes = service.derive_plan(run_id, with_eslint).stages[0].expected_dependency_changes
    without_changes = service.derive_plan(run_id, without_eslint).stages[0].expected_dependency_changes
    assert any(item["package"] == "@angular-eslint" for item in with_changes)
    assert not any(item["package"] == "@angular-eslint" for item in without_changes)


def test_persist_and_get_plan():
    run_id = f"run-f18-{uuid4().hex[:8]}"
    _seed(run_id, "angular-14.x", "angular-17.x")
    service = V2PlannerService()
    plan = service.derive_plan(run_id)
    row = service.persist(run_id, plan)
    assert row.checksum == plan.checksum
    assert len(row.stages) == 3
    with session_scope() as session:
        assert session.query(V2PlanningModel).filter_by(run_id=run_id).count() == 1


def test_unknown_run_raises():
    service = V2PlannerService()
    try:
        service.derive_plan("run-missing")
        assert False, "expected RUN_NOT_FOUND"
    except V2PlanningError as exc:
        assert exc.code == "RUN_NOT_FOUND"


def test_api_plan_11_to_21():
    run_id = f"run-f18-{uuid4().hex[:8]}"
    _seed(run_id, "angular-11.x", "angular-21.x")
    response = client.post(f"/runs/{run_id}/v2/plan", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["source_major"] == 11
    assert body["target_major"] == 21
    assert len(body["stages"]) == 10
    assert body["checksum"].startswith("sha256:")

    persisted = client.post(f"/runs/{run_id}/v2/plan/persist", json={})
    assert persisted.status_code == 200
    got = client.get(f"/runs/{run_id}/v2/plan")
    assert got.status_code == 200
    assert got.json()["checksum"] == persisted.json()["checksum"]


def test_api_plan_missing_run_404():
    response = client.post("/runs/run-missing/v2/plan", json={})
    assert response.status_code == 404
    assert response.json()["error_code"] == "RUN_NOT_FOUND"


def test_plan_validation_detects_drift():
    run_id = f"run-f18-{uuid4().hex[:8]}"
    _seed(run_id, "angular-11.x", "angular-16.x")
    service = V2PlannerService()
    plan = service.derive_plan(run_id)
    service.persist(run_id, plan)
    validated = service.validate_plan(run_id)
    assert validated.checksum == plan.checksum

    # drift: change the run's target family
    with session_scope() as session:
        run = session.get(MigrationRunModel, run_id)
        run.target_version_family = "angular-17.x"
        session.commit()
    try:
        service.validate_plan(run_id)
        assert False, "expected PLAN_DRIFT"
    except V2PlanningError as exc:
        assert exc.code == "PLAN_DRIFT"
