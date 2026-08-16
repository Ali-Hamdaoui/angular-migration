"""Persistence + API tests for F03 failure diagnostic packs."""

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import FailureDiagnosticPackModel
from app.repositories.session import session_scope
from app.services.diagnostics_application_service import DiagnosticsApplicationService

client = TestClient(app)


def _run_id() -> str:
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.repositories.models import MigrationRunModel

    run_id = f"run-diag-{uuid4().hex[:10]}"
    with session_scope() as session:
        session.add(
            MigrationRunModel(
                id=run_id, status="CREATED", run_phase="initialized",
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
        )
        session.commit()
    return run_id


def _record_pack(run_id: str, execution_id: str | None = None) -> str:
    service = DiagnosticsApplicationService()
    pack = service.record_command_failure(
        run_id=run_id,
        execution_id=execution_id,
        correlation_id="corr-f03",
        error=RuntimeError("npm ci failed"),
        command=("npm", "ci"),
        exit_code=1,
        stdout="",
        stderr="npm ERR! code ERESOLVE\n",
        working_directory_alias="run_workspace",
        runtime_profile_id="profile-1",
        stage_id=None,
        command_id="npm-ci-bootstrap",
        traceback_text="Traceback (most recent call last):\n  File \"x.py\", line 1\nRuntimeError: npm ci failed",
    )
    assert pack is not None
    return pack.pack_id


def test_record_and_get_pack():
    run_id = _run_id()
    pack_id = _record_pack(run_id, execution_id="exec-1")
    response = client.get(f"/diagnostics/packs/{pack_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["fault"]["fault_code"] == "RuntimeError"
    assert body["correlation_id"] == "corr-f03"
    assert body["command_evidence"]["exit_code"] == 1
    assert body["command_evidence"]["stderr"] == "npm ERR! code ERESOLVE\n"
    assert body["workflow_context"]["execution_id"] == "exec-1"
    assert body["workflow_context"]["command_id"] == "npm-ci-bootstrap"
    assert body["checksum"].startswith("sha256:")
    assert "RuntimeError: npm ci failed" in body["sanitized_traceback"]


def test_list_packs_by_run_and_execution():
    from uuid import uuid4

    run_id = _run_id()
    execution_id = f"exec-{uuid4().hex[:10]}"
    _record_pack(run_id, execution_id=execution_id)
    _record_pack(run_id, execution_id=execution_id)
    listed = client.get(f"/diagnostics/runs/{run_id}/packs")
    assert listed.status_code == 200
    assert len(listed.json()["packs"]) == 2
    by_exec = client.get(f"/diagnostics/runs/{run_id}/executions/{execution_id}/packs")
    assert len(by_exec.json()["packs"]) == 2


def test_get_missing_pack_returns_404():
    response = client.get("/diagnostics/packs/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error_code"] == "DIAGNOSTIC_PACK_NOT_FOUND"


def test_pack_persisted_in_sqlite():
    run_id = _run_id()
    pack_id = _record_pack(run_id)
    with session_scope() as session:
        row = session.get(FailureDiagnosticPackModel, pack_id)
        assert row is not None
        assert row.fault_code == "RuntimeError"
        assert row.category == "unknown"
        assert row.correlation_id == "corr-f03"
        assert row.sanitized_traceback
