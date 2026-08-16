"""Tests for F26 partial migration delivery."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import (
    MigrationRunModel,
    MigrationStageModel,
    PartialDeliveryModel,
    StageValidationSealModel,
)
from app.repositories.session import session_scope
from app.services.partial_delivery_service import PartialDeliveryError, PartialDeliveryService
from app.services.stage_validation_seal_service import StageValidationSealService

NOW = datetime.now(UTC)
client = TestClient(app)


def _seed(run_id: str, stages: int = 3, source: str = "angular-11.x", target: str = "angular-14.x") -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      source_version_family=source, target_version_family=target,
                                      created_at=NOW, updated_at=NOW))
        for order in range(1, stages + 1):
            session.add(MigrationStageModel(id=f"stage-{run_id}-{order}", run_id=run_id, stage_order=order,
                                            source_version_family=f"angular-{10+order}.x", target_version_family=f"angular-{11+order}.x",
                                            source_angular_version=f"{10+order}.0.0", target_angular_version=f"{11+order}.0.0",
                                            status="planned", created_at=NOW))
        session.commit()


def _seal_stage(run_id: str, order: int) -> None:
    stage_id = f"stage-{run_id}-{order}"
    root = Path(f"/tmp/f26-{uuid4().hex[:6]}")
    root.mkdir(parents=True)
    (root / "package.json").write_text('{"name":"app"}')
    StageValidationSealService().seal_stage(stage_id, root, run_id=run_id)


def test_deliver_partial_at_furthest_sealed():
    run_id = f"run-f26-{uuid4().hex[:8]}"
    _seed(run_id, stages=3)
    _seal_stage(run_id, 1)
    _seal_stage(run_id, 2)
    root = Path(f"/tmp/f26w-{uuid4().hex[:6]}")
    root.mkdir(parents=True)
    (root / "package.json").write_text('{"name":"app"}')
    service = PartialDeliveryService()
    decision = service.deliver_partial(run_id, root)
    assert decision.delivered_at_stage == 2
    assert decision.validated is True
    assert decision.delivered_fingerprint.startswith("sha256:")
    assert decision.checksum.startswith("sha256:")
    assert decision.remaining_stages  # work after stage 2 remains


def test_deliver_partial_no_sealed_stage_raises():
    run_id = f"run-f26-{uuid4().hex[:8]}"
    _seed(run_id, stages=2)
    service = PartialDeliveryService()
    try:
        service.deliver_partial(run_id, Path("/tmp"))
        assert False, "expected NO_SEALED_STAGE"
    except PartialDeliveryError as exc:
        assert exc.code == "NO_SEALED_STAGE"


def test_validate_partial_workspace_blocks_missing():
    run_id = f"run-f26-{uuid4().hex[:8]}"
    _seed(run_id, stages=2)
    _seal_stage(run_id, 1)
    service = PartialDeliveryService()
    decision = service.deliver_partial(run_id, Path("/tmp/does-not-exist"))
    assert decision.validated is False
    assert decision.resumable is True


def test_resume_partial():
    run_id = f"run-f26-{uuid4().hex[:8]}"
    _seed(run_id, stages=3)
    _seal_stage(run_id, 1)
    root = Path(f"/tmp/f26r-{uuid4().hex[:6]}")
    root.mkdir(parents=True)
    (root / "package.json").write_text('{"name":"app"}')
    service = PartialDeliveryService()
    service.deliver_partial(run_id, root)
    resume = service.resume_partial(run_id)
    assert resume["delivered_at_stage"] == 1
    assert resume["resume_action"] == "resume_chain_from_delivered_stage"


def test_api_deliver_and_resume():
    run_id = f"run-f26-{uuid4().hex[:8]}"
    _seed(run_id, stages=2)
    _seal_stage(run_id, 1)
    root = Path(f"/tmp/f26a-{uuid4().hex[:6]}")
    root.mkdir(parents=True)
    (root / "package.json").write_text('{"name":"app"}')
    delivered = client.post(f"/runs/{run_id}/partial-delivery", json={"workspace_path": str(root)})
    assert delivered.status_code == 200
    assert delivered.json()["delivered_at_stage"] == 1
    assert delivered.json()["validated"] is True

    resumed = client.post(f"/runs/{run_id}/partial-delivery/resume", json={})
    assert resumed.status_code == 200
    assert resumed.json()["resume_action"] == "resume_chain_from_delivered_stage"

    listed = client.get(f"/runs/{run_id}/partial-deliveries")
    assert listed.status_code == 200
    assert len(listed.json()["deliveries"]) == 1
    with session_scope() as session:
        assert session.query(PartialDeliveryModel).filter_by(run_id=run_id).count() == 1


def test_api_deliver_unknown_run_404():
    response = client.post("/runs/run-missing/partial-delivery", json={"workspace_path": "/tmp"})
    assert response.status_code == 404
    assert response.json()["error_code"] == "RUN_NOT_FOUND"
