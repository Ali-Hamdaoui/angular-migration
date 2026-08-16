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
