"""Tests for F12 dynamic stage orchestration."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import MigrationRunModel, StageChainRunModel
from app.repositories.session import session_scope
from app.services.stage_chain_orchestrator import StageChainOrchestrator, StageOrchestrationError

NOW = datetime.now(UTC)
client = TestClient(app)


def _seed(run_id: str, source: str = "angular-11.x", target: str = "angular-14.x") -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      source_version_family=source, target_version_family=target,
                                      created_at=NOW, updated_at=NOW))
        session.commit()


def test_start_chain_from_route():
    run_id = f"run-f12-{uuid4().hex[:8]}"
    _seed(run_id, "angular-11.x", "angular-14.x")
    orchestrator = StageChainOrchestrator()
    state = orchestrator.start_chain(run_id)
    assert state.status == "created"
    assert len(state.stages) == 3
    assert state.stages[0].source_major == 11
    assert state.stages[-1].target_major == 14
    assert state.checksum.startswith("sha256:")


def test_advance_completes_chain():
    run_id = f"run-f12-{uuid4().hex[:8]}"
    _seed(run_id, "angular-11.x", "angular-13.x")
    orchestrator = StageChainOrchestrator()
    orchestrator.start_chain(run_id)
    first = orchestrator.advance(run_id)
    # first stage (11->12) is experimental -> gate fails -> repairing
    assert first.status == "repairing"
    assert first.stages[0].status == "failed"
    assert first.stages[0].failure_code == "STAGE_GATE_NOT_PASSED"


def test_failure_routes_to_repair_and_resume():
    run_id = f"run-f12-{uuid4().hex[:8]}"
    _seed(run_id)
    orchestrator = StageChainOrchestrator()
    orchestrator.start_chain(run_id)
    failed = orchestrator.mark_stage_failed(run_id, 1, "COMMAND_EXIT_NONZERO")
    assert failed.status == "repairing"
    assert failed.stages[0].failure_code == "COMMAND_EXIT_NONZERO"
    resumed = orchestrator.resume(run_id)
    assert resumed.status in {"running", "repairing"}


def test_resume_without_start_raises():
    run_id = f"run-f12-{uuid4().hex[:8]}"
    _seed(run_id)
    orchestrator = StageChainOrchestrator()
    try:
        orchestrator.resume(run_id)
        assert False, "expected CHAIN_NOT_STARTED"
    except StageOrchestrationError as exc:
        assert exc.code == "CHAIN_NOT_STARTED"


def test_api_chain_lifecycle():
    run_id = f"run-f12-{uuid4().hex[:8]}"
    _seed(run_id, "angular-11.x", "angular-13.x")
    started = client.post(f"/runs/{run_id}/chain/start")
    assert started.status_code == 200
    assert len(started.json()["stages"]) == 2

    advanced = client.post(f"/runs/{run_id}/chain/advance")
    assert advanced.status_code == 200
    assert advanced.json()["status"] == "repairing"

    failed = client.post(f"/runs/{run_id}/chain/stages/1/fail?failure_code=COMMAND_EXIT_NONZERO")
    assert failed.status_code == 200
    assert failed.json()["stages"][0]["failure_code"] == "COMMAND_EXIT_NONZERO"

    resumed = client.post(f"/runs/{run_id}/chain/resume")
    assert resumed.status_code == 200

    current = client.get(f"/runs/{run_id}/chain")
    assert current.status_code == 200
    with session_scope() as session:
        assert session.query(StageChainRunModel).filter_by(run_id=run_id).count() == 1
