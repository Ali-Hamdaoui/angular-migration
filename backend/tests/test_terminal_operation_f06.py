"""Tests for F06 terminal operation."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import FailureDiagnosticPackModel, MigrationRunModel
from app.repositories.session import session_scope
from app.services.terminal_operation_service import TerminalOperationService

NOW = datetime.now(UTC)
client = TestClient(app)


def _seed(run_id: str) -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      source_version_family="angular-18.x", target_version_family="angular-19.x",
                                      created_at=NOW, updated_at=NOW))
        session.add(FailureDiagnosticPackModel(
            id=f"diag-{run_id}-0", run_id=run_id, fault_code="NPM_ERESOLVE", category="dependency",
            severity="error", message="npm ERR! code ERESOLVE", workflow_context={}, sanitized_traceback="",
            checksum="sha256:" + "a" * 64, state_version=1, created_at=NOW,
        ))
        session.commit()


def test_next_action_projection():
    run_id = f"run-f06-{uuid4().hex[:8]}"
    _seed(run_id)
    action = TerminalOperationService().next_action(run_id)
    assert action["run_id"] == run_id
    assert "next_permitted_action" in action
    assert isinstance(action["remaining_work"], list)


def test_terminal_diagnostics_composes_failure_intelligence():
    run_id = f"run-f06-{uuid4().hex[:8]}"
    _seed(run_id)
    diagnostics = TerminalOperationService().terminal_diagnostics(run_id)
    assert diagnostics["diagnostic_packs"] == [f"diag-{run_id}-0"]
    assert len(diagnostics["failure_groups"]) >= 1


def test_terminal_resume():
    run_id = f"run-f06-{uuid4().hex[:8]}"
    _seed(run_id)
    resume = TerminalOperationService().terminal_resume(run_id)
    assert resume["run_id"] == run_id
    assert resume["chain_status"] == "not_started"
    assert "next" in resume


def test_api_next_action():
    run_id = f"run-f06-{uuid4().hex[:8]}"
    _seed(run_id)
    response = client.get(f"/terminal/runs/{run_id}/next-action")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert "next_permitted_action" in body


def test_api_diagnostics_and_resume():
    run_id = f"run-f06-{uuid4().hex[:8]}"
    _seed(run_id)
    diag = client.get(f"/terminal/runs/{run_id}/diagnostics")
    assert diag.status_code == 200
    assert len(diag.json()["failure_groups"]) >= 1

    resume = client.post(f"/terminal/runs/{run_id}/resume", json={"actor": "operator"})
    assert resume.status_code == 200
    assert resume.json()["run_id"] == run_id


def test_api_next_action_unknown_run_404():
    response = client.get("/terminal/runs/run-missing/next-action")
    assert response.status_code == 404
