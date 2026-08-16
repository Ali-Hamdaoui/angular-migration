"""Tests for F23 full terminal workflow."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import MigrationRunModel, StageChainRunModel, WorkflowEventModel
from app.repositories.session import session_scope
from app.services.terminal_lifecycle_service import TerminalLifecycleError, TerminalLifecycleService

NOW = datetime.now(UTC)
client = TestClient(app)


def _seed(run_id: str, source: str = "angular-18.x", target: str = "angular-19.x") -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      source_version_family=source, target_version_family=target,
                                      created_at=NOW, updated_at=NOW))
        session.commit()


def test_lifecycle_sequence_setup_phase():
    run_id = f"run-f23-{uuid4().hex[:8]}"
    _seed(run_id)
    service = TerminalLifecycleService()
    sequence = service.lifecycle_sequence(run_id)
    assert sequence["current_phase"] == "setup"
    assert sequence["phases"] == ["setup", "execution_profile", "chain_start", "stages", "sealing", "delivery"]
    assert sequence["chain_status"] == "not_started"


def test_drive_next_starts_chain():
    run_id = f"run-f23-{uuid4().hex[:8]}"
    _seed(run_id)
    service = TerminalLifecycleService()
    sequence = service.drive_next(run_id)
    assert sequence["chain_status"] == "created"
    with session_scope() as session:
        assert session.query(StageChainRunModel).filter_by(run_id=run_id).count() == 1


def test_drive_starts_chain_even_with_events_but_no_chain():
    """A run with events but no chain must still be at setup, and drive must start it."""
    run_id = f"run-f23-{uuid4().hex[:8]}"
    _seed(run_id)
    with session_scope() as session:
        session.add(WorkflowEventModel(id=f"ev-{run_id}", run_id=run_id, event_type="run_created",
                                       sequence=1, payload={}, occurred_at=NOW))
        session.commit()
    service = TerminalLifecycleService()
    sequence = service.lifecycle_sequence(run_id)
    assert sequence["current_phase"] == "setup"
    driven = service.drive_next(run_id)
    assert driven["chain_status"] == "created"


def test_lifecycle_evidence_composes_events():
    run_id = f"run-f23-{uuid4().hex[:8]}"
    _seed(run_id)
    with session_scope() as session:
        session.add(WorkflowEventModel(id=f"ev-{run_id}", run_id=run_id, event_type="run_created",
                                       sequence=1, payload={}, occurred_at=NOW))
        session.commit()
    evidence = TerminalLifecycleService().lifecycle_evidence(run_id)
    assert len(evidence["events"]) == 1
    assert evidence["events"][0]["event_type"] == "run_created"
    assert "next_action" in evidence


def test_unknown_run_raises():
    service = TerminalLifecycleService()
    try:
        service.lifecycle_sequence("run-missing")
        assert False, "expected RUN_NOT_FOUND"
    except TerminalLifecycleError as exc:
        assert exc.code == "RUN_NOT_FOUND"


def test_api_lifecycle():
    run_id = f"run-f23-{uuid4().hex[:8]}"
    _seed(run_id)
    sequence = client.get(f"/terminal/runs/{run_id}/lifecycle")
    assert sequence.status_code == 200
    assert sequence.json()["current_phase"] == "setup"

    evidence = client.get(f"/terminal/runs/{run_id}/lifecycle/evidence")
    assert evidence.status_code == 200

    driven = client.post(f"/terminal/runs/{run_id}/lifecycle/drive", json={})
    assert driven.status_code == 200
    assert driven.json()["chain_status"] == "created"


def test_api_lifecycle_unknown_run_404():
    response = client.get("/terminal/runs/run-missing/lifecycle")
    assert response.status_code == 404
    assert response.json()["error_code"] == "RUN_NOT_FOUND"
