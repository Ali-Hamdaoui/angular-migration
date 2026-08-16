"""Tests for F24 stage validation and sealing."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import MigrationRunModel, MigrationStageModel, StageValidationSealModel
from app.repositories.session import session_scope
from app.services.stage_validation_seal_service import StageValidationError, StageValidationSealService

NOW = datetime.now(UTC)
client = TestClient(app)


def _seed(stage_id: str, source: str = "angular-18.x", target: str = "angular-19.x") -> str:
    run_id = f"run-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      source_version_family=source, target_version_family=target,
                                      created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(id=stage_id, run_id=run_id, stage_order=1,
                                        source_version_family=source, target_version_family=target,
                                        source_angular_version="18.2.0", target_angular_version="19.0.0",
                                        status="planned", created_at=NOW))
        session.commit()
    return run_id


def _workspace(tmp_path: Path, run_root: Path) -> Path:
    ws = run_root / f"ws-{uuid4().hex[:8]}"
    ws.mkdir(parents=True)
    (ws / "package.json").write_text('{"name":"app"}')
    return ws


def test_validate_stage_passes():
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    ws = _workspace(Path("/tmp"), Path("/tmp"))
    service = StageValidationSealService()
    result = service.validate_stage(stage_id, ws)
    assert result.passed is True
    assert result.checksum.startswith("sha256:")
    assert "build" not in result.checks


def test_validate_missing_workspace_fails():
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    service = StageValidationSealService()
    result = service.validate_stage(stage_id, Path("/tmp/does-not-exist"))
    assert result.passed is False
    assert "STAGE_WORKSPACE_MISSING" in result.blockers


def test_seal_stage_and_immutability():
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    ws = _workspace(Path("/tmp"), Path("/tmp"))
    service = StageValidationSealService()
    seal = service.seal_stage(stage_id, ws)
    assert seal.checksum.startswith("sha256:")
    assert service.is_sealed(stage_id) is not None
    # cannot re-seal
    try:
        service.seal_stage(stage_id, ws)
        assert False, "expected STAGE_ALREADY_SEALED"
    except StageValidationError as exc:
        assert exc.code == "STAGE_ALREADY_SEALED"
    # assert_unsealed enforcement
    try:
        service.assert_unsealed(stage_id)
        assert False, "expected STAGE_ALREADY_SEALED"
    except StageValidationError as exc:
        assert exc.code == "STAGE_ALREADY_SEALED"


def test_seal_requires_validation_pass():
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    service = StageValidationSealService()
    try:
        service.seal_stage(stage_id, Path("/tmp/missing"))
        assert False, "expected STAGE_NOT_VALIDATED"
    except StageValidationError as exc:
        assert exc.code == "STAGE_NOT_VALIDATED"


def test_api_validate_seal_and_list(tmp_path: Path):
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    ws = _workspace(tmp_path, tmp_path)
    validated = client.post(f"/runs/{run_id}/stages/{stage_id}/validate", json={"workspace_path": str(ws)})
    assert validated.status_code == 200
    assert validated.json()["passed"] is True

    sealed = client.post(f"/runs/{run_id}/stages/{stage_id}/seal", json={"workspace_path": str(ws)})
    assert sealed.status_code == 200
    assert sealed.json()["checksum"].startswith("sha256:")

    # re-seal -> 409
    again = client.post(f"/runs/{run_id}/stages/{stage_id}/seal", json={"workspace_path": str(ws)})
    assert again.status_code == 409
    assert again.json()["error_code"] == "STAGE_ALREADY_SEALED"

    got = client.get(f"/runs/{run_id}/stages/{stage_id}/seal")
    assert got.status_code == 200
    listed = client.get(f"/runs/{run_id}/seals")
    assert listed.status_code == 200
    assert len(listed.json()["seals"]) == 1
    with session_scope() as session:
        assert session.query(StageValidationSealModel).filter_by(stage_id=stage_id).count() == 1
