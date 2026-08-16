"""Tests for F22 candidate workspace promotion."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import CandidatePromotionModel, MigrationRunModel, MigrationStageModel
from app.repositories.session import session_scope
from app.services.candidate_promotion_service import CandidatePromotionError, CandidatePromotionService

NOW = datetime.now(UTC)
client = TestClient(app)


def _seed(stage_id: str, root: Path | None = None):
    import tempfile

    run_id = f"run-{uuid4().hex[:8]}"
    root = root or Path(tempfile.mkdtemp(prefix="f22-run-"))
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      source_version_family="angular-18.x", target_version_family="angular-19.x",
                                      run_root=str(root), created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(id=stage_id, run_id=run_id, stage_order=1,
                                        source_version_family="angular-18.x", target_version_family="angular-19.x",
                                        status="planned", created_at=NOW))
        session.commit()
    return run_id


def _candidate(base: Path | None = None) -> Path:
    ws = (base or Path("/tmp")) / f"candidate-{uuid4().hex[:8]}"
    ws.mkdir(parents=True)
    (ws / "package.json").write_text('{"name":"candidate"}')
    (ws / "main.ts").write_text("export const ok = 1;\n")
    return ws


def _run_root() -> Path:
    import tempfile

    return Path(tempfile.mkdtemp(prefix="f22-cand-"))


def test_validate_candidate_ready():
    stage_id = f"stage-{uuid4().hex[:8]}"
    root = _run_root()
    run_id = _seed(stage_id, root)
    candidate = _candidate(root)
    service = CandidatePromotionService()
    decision = service.validate_candidate(candidate, run_id=run_id, stage_id=stage_id)
    assert decision.status == "candidate_ready"
    assert decision.validated is True
    assert decision.generation == 1
    assert decision.checksum.startswith("sha256:")


def test_validate_missing_candidate_rejected():
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    service = CandidatePromotionService()
    decision = service.validate_candidate(Path("/tmp/does-not-exist"), run_id=run_id, stage_id=stage_id)
    assert decision.validated is False
    assert "CANDIDATE_WORKSPACE_MISSING" in decision.blockers


def test_promote_candidate_atomic_and_generation_increment():
    stage_id = f"stage-{uuid4().hex[:8]}"
    root = _run_root()
    run_id = _seed(stage_id, root)
    candidate = _candidate(root)
    service = CandidatePromotionService()
    first = service.promote_candidate(run_id=run_id, stage_id=stage_id, candidate_path=candidate)
    assert first.status == "promoted"
    assert first.generation == 1
    second = service.promote_candidate(run_id=run_id, stage_id=stage_id, candidate_path=candidate)
    assert second.generation == 2
    # last-good generation remains active (rollback safety)
    safety = service.rollback_safety(run_id=run_id, stage_id=stage_id)
    assert safety.validated is True
    assert safety.generation == 2


def test_promote_rejected_candidate_not_promoted():
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    service = CandidatePromotionService()
    decision = service.promote_candidate(run_id=run_id, stage_id=stage_id, candidate_path=Path("/tmp/missing"))
    assert decision.status == "rejected"
    assert not decision.validated


def test_persist_and_list():
    stage_id = f"stage-{uuid4().hex[:8]}"
    root = _run_root()
    run_id = _seed(stage_id, root)
    candidate = _candidate(root)
    service = CandidatePromotionService()
    decision = service.validate_candidate(candidate, run_id=run_id, stage_id=stage_id)
    row = service.persist(decision)
    assert row.checksum == decision.checksum
    with session_scope() as session:
        assert session.query(CandidatePromotionModel).filter_by(stage_id=stage_id).count() == 1


def test_candidate_outside_run_root_rejected():
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id)
    candidate = _candidate()  # /tmp, outside the run root
    service = CandidatePromotionService()
    decision = service.validate_candidate(candidate, run_id=run_id, stage_id=stage_id)
    assert decision.validated is False
    assert "CANDIDATE_OUTSIDE_RUN_ROOT" in decision.blockers


def test_run_id_mismatch_raises():
    stage_id = f"stage-{uuid4().hex[:8]}"
    root = _run_root()
    run_id = _seed(stage_id, root)
    candidate = _candidate(root)
    service = CandidatePromotionService()
    try:
        service.validate_candidate(candidate, run_id="run-other", stage_id=stage_id)
        assert False, "expected RUN_ID_MISMATCH"
    except CandidatePromotionError as exc:
        assert exc.code == "RUN_ID_MISMATCH"


def test_unknown_stage_raises():
    service = CandidatePromotionService()
    try:
        service.validate_candidate(Path("/tmp"), run_id="run", stage_id="missing")
        assert False, "expected STAGE_NOT_FOUND"
    except CandidatePromotionError as exc:
        assert exc.code == "STAGE_NOT_FOUND"


def test_api_validate_and_promote(tmp_path: Path):
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id, tmp_path)
    candidate = _candidate(tmp_path)
    validated = client.post(f"/runs/{run_id}/stages/{stage_id}/candidate/validate", json={"candidate_path": str(candidate)})
    assert validated.status_code == 200
    assert validated.json()["validated"] is True

    promoted = client.post(f"/runs/{run_id}/stages/{stage_id}/candidate/promote", json={"candidate_path": str(candidate)})
    assert promoted.status_code == 200
    assert promoted.json()["status"] == "promoted"

    safety = client.post(f"/runs/{run_id}/stages/{stage_id}/candidate/rollback-safety")
    assert safety.status_code == 200
    assert safety.json()["validated"] is True
