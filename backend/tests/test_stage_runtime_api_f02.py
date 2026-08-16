"""API tests for F02 stage runtime requirement/binding endpoints."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import MigrationRunModel, MigrationStageModel, StageRuntimeBindingModel
from app.repositories.session import session_scope

client = TestClient(app)
NOW = datetime.now(UTC)


def _seed() -> tuple[str, str]:
    run_id = f"run-f02a-{uuid4().hex[:8]}"
    stage_id = f"stage-f02a-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(
            id=stage_id, run_id=run_id, stage_order=1,
            source_version_family="angular-18.x", target_version_family="angular-19.x",
            source_angular_version="18.2.0", target_angular_version="19.0.0",
            status="planned", created_at=NOW,
        ))
        session.commit()
    return run_id, stage_id


def test_resolve_stage_runtime_api():
    run_id, stage_id = _seed()
    response = client.post(
        f"/runs/{run_id}/stages/{stage_id}/runtime/resolve",
        json={"source_family": "angular-18.x", "target_family": "angular-19.x"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "bound"
    assert body["checksum"].startswith("sha256:")
    node = next(b for b in body["bindings"] if b["requirement"]["kind"] == "node")
    assert node["descriptor"]["version_exact"] is not None
    assert len(node["descriptor"]["sha256"]) == 64


def test_record_and_list_stage_binding_api():
    run_id, stage_id = _seed()
    recorded = client.post(f"/runs/{run_id}/stages/{stage_id}/runtime/bindings", json={"run_id": run_id, "actor": "test"})
    assert recorded.status_code == 200
    rows = recorded.json()["bindings"]
    assert len(rows) == 3

    listed = client.get(f"/runs/{run_id}/stages/{stage_id}/runtime/bindings")
    assert listed.status_code == 200
    assert len(listed.json()["bindings"]) == 3

    with session_scope() as session:
        assert session.query(StageRuntimeBindingModel).filter_by(stage_id=stage_id).count() == 3


def test_resolve_unknown_stage_returns_404():
    response = client.post(
        "/runs/run-x/stages/stage-missing/runtime/resolve",
        json={"source_family": "angular-18.x", "target_family": "angular-19.x"},
    )
    assert response.status_code == 404


def test_record_unknown_stage_returns_404():
    response = client.post("/runs/run-x/stages/stage-missing/runtime/bindings", json={"run_id": "run-x"})
    assert response.status_code == 404
