"""API tests for F07 workspace authority."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import MigrationRunModel, MigrationStageModel, WorkspaceGenerationModel
from app.repositories.session import session_scope

client = TestClient(app)
NOW = datetime.now(UTC)


def _seed() -> tuple[str, str]:
    run_id = f"run-f07a-{uuid4().hex[:8]}"
    stage_id = f"stage-f07a-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(id=stage_id, run_id=run_id, stage_order=1,
                                        source_version_family="angular-18.x", target_version_family="angular-19.x",
                                        status="planned", created_at=NOW))
        session.commit()
    return run_id, stage_id


def test_promote_and_resolve_active_api():
    run_id, stage_id = _seed()
    promoted = client.post(
        f"/runs/{run_id}/workspaces/STAGE_WORKSPACE_1/promote?stage_id={stage_id}",
        json={"generation": 1, "workspace_path": "/ws/1", "fingerprint": "fp-1"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["allowed"] is True

    resolved = client.get(f"/runs/{run_id}/workspaces/STAGE_WORKSPACE_1/active?stage_id={stage_id}")
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["active"]["generation"] == 1
    assert body["current_generation"] == 1

    # stale promotion rejected with 409
    stale = client.post(
        f"/runs/{run_id}/workspaces/STAGE_WORKSPACE_1/promote?stage_id={stage_id}",
        json={"generation": 1, "workspace_path": "/ws/old", "fingerprint": "fp-old"},
    )
    assert stale.status_code == 409
    assert stale.json()["error_code"] == "STALE_GENERATION"


def test_promote_unknown_run_404():
    response = client.post(
        "/runs/run-missing/workspaces/STAGE_WORKSPACE_1/promote",
        json={"generation": 1, "workspace_path": "/ws/1", "fingerprint": "fp-1"},
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "RUN_NOT_FOUND"


def test_list_generations_api():
    run_id, stage_id = _seed()
    client.post(
        f"/runs/{run_id}/workspaces/STAGE_WORKSPACE_1/promote?stage_id={stage_id}",
        json={"generation": 1, "workspace_path": "/ws/1", "fingerprint": "fp-1"},
    )
    listed = client.get(f"/runs/{run_id}/workspaces/STAGE_WORKSPACE_1/generations?stage_id={stage_id}")
    assert listed.status_code == 200
    assert len(listed.json()["generations"]) == 1
