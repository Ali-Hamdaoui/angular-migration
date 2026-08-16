"""Tests for F25 stage rollback and resume."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import MigrationRunModel, MigrationStageModel, StageValidationSealModel
from app.repositories.session import session_scope
from app.services.stage_rollback_service import StageRollbackError, StageRollbackService

NOW = datetime.now(UTC)
client = TestClient(app)


def _seed(run_id: str, stages: int = 2, source: str = "angular-11.x", target: str = "angular-13.x") -> None:
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


def _seed_chain(run_id: str) -> None:
    from app.services.stage_chain_orchestrator import StageChainOrchestrator

    StageChainOrchestrator().start_chain(run_id)


def _seal_stage(run_id: str, order: int) -> None:
    from app.services.stage_validation_seal_service import StageValidationSealService

    stage_id = f"stage-{run_id}-{order}"
    with session_scope() as session:
        stage = session.get(MigrationStageModel, stage_id)
        assert stage is not None
    root = Path(f"/tmp/f25-{uuid4().hex[:6]}")
    root.mkdir(parents=True)
    (root / "package.json").write_text('{"name":"app"}')
    StageValidationSealService().seal_stage(stage_id, root)


def test_find_rollback_point_highest_sealed():
    run_id = f"run-f25-{uuid4().hex[:8]}"
    _seed(run_id, stages=3)
    _seal_stage(run_id, 1)
    _seal_stage(run_id, 2)
    service = StageRollbackService()
    assert service.find_rollback_point(run_id) == 2


def test_rollback_no_point():
    run_id = f"run-f25-{uuid4().hex[:8]}"
    _seed(run_id, stages=2)
    _seed_chain(run_id)
    service = StageRollbackService()
    decision = service.rollback(run_id)
    assert decision.status == "no_rollback_point"
    assert decision.rollback_point_stage_order is None


def test_rollback_resets_stages_after_point_and_preserves_evidence():
    run_id = f"run-f25-{uuid4().hex[:8]}"
    _seed(run_id, stages=3)
    _seed_chain(run_id)
    _seal_stage(run_id, 1)
    service = StageRollbackService()
    decision = service.rollback(run_id)
    assert decision.status == "rolled_back"
    assert decision.rollback_point_stage_order == 1
    assert decision.evidence_preserved is True
    # sealed evidence preserved
    with session_scope() as session:
        assert session.query(StageValidationSealModel).filter_by(run_id=run_id).count() == 1
    # idempotent re-rollback (same checksum -> no duplicate row, no crash)
    again = service.rollback(run_id)
    assert again.status == "rolled_back"
    with session_scope() as session:
        from app.repositories.models import StageRollbackModel

        assert session.query(StageRollbackModel).filter_by(run_id=run_id).count() == 1


def test_resume_from_sealed():
    run_id = f"run-f25-{uuid4().hex[:8]}"
    _seed(run_id, stages=3)
    _seed_chain(run_id)
    _seal_stage(run_id, 1)
    service = StageRollbackService()
    resume = service.resume_from_sealed(run_id)
    assert resume["rollback_point_stage_order"] == 1
    assert resume["next_stage_order"] == 2
    assert resume["resume_action"] == "advance_next_stage"


def test_resume_without_sealed_raises():
    run_id = f"run-f25-{uuid4().hex[:8]}"
    _seed(run_id)
    service = StageRollbackService()
    try:
        service.resume_from_sealed(run_id)
        assert False, "expected NO_ROLLBACK_POINT"
    except StageRollbackError as exc:
        assert exc.code == "NO_ROLLBACK_POINT"


def test_api_rollback_and_resume():
    run_id = f"run-f25-{uuid4().hex[:8]}"
    _seed(run_id, stages=3)
    _seed_chain(run_id)
    _seal_stage(run_id, 1)
    rolled = client.post(f"/runs/{run_id}/rollback")
    assert rolled.status_code == 200
    assert rolled.json()["status"] == "rolled_back"

    resumed = client.post(f"/runs/{run_id}/resume-from-sealed")
    assert resumed.status_code == 200
    assert resumed.json()["next_stage_order"] == 2

    listed = client.get(f"/runs/{run_id}/rollbacks")
    assert listed.status_code == 200
    assert len(listed.json()["rollbacks"]) >= 1


def test_api_rollback_unknown_run_404():
    response = client.post("/runs/run-missing/rollback")
    assert response.status_code == 404
    assert response.json()["error_code"] == "RUN_NOT_FOUND"
