"""API integration tests for AMFA-179: Angular update completion and target version verification routes."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.domain.transformation import AngularUpdateStatus, TargetVersionStatus
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_db():
    from app.domain.contracts import RunPhase, RunStatus, StageStatus
    from app.repositories.models import MigrationRunModel, MigrationStageModel
    from app.repositories.models.base import Base
    from app.repositories import session as session_module
    from app.repositories.session import session_scope
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()

    original_engine = session_module.engine
    original_session_local = session_module.SessionLocal

    test_engine = create_engine(f"sqlite:///{tmp_db.name}", echo=False)
    session_module.engine = test_engine
    session_module.SessionLocal = sessionmaker(
        bind=test_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=test_engine)

    run_id = f"test-run-{uuid4().hex[:8]}"
    stage_id = f"test-stage-{uuid4().hex[:8]}"

    with session_scope() as s:
        run = MigrationRunModel(
            id=run_id,
            status=RunStatus.RUNNING.value,
            run_phase=RunPhase.STAGED_MIGRATION.value,
            phase_status="running",
            state_version=1,
            source_path="/tmp/source",
            artifact_root=tempfile.mkdtemp(prefix="artifacts_"),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(run)
        stage = MigrationStageModel(
            id=stage_id,
            run_id=run_id,
            stage_order=1,
            status=StageStatus.PREPARING.value,
            created_at=datetime.now(UTC),
        )
        s.add(stage)

    try:
        yield run_id, stage_id, tmp_db.name
    finally:
        try:
            Base.metadata.drop_all(bind=test_engine)
        finally:
            test_engine.dispose()
            session_module.engine = original_engine
            session_module.SessionLocal = original_session_local
            Path(tmp_db.name).unlink(missing_ok=True)


@pytest.fixture
def seeded_db(test_db):
    """Create a run, stage, and an AngularUpdateRecordModel for testing."""
    run_id, stage_id, tmp_db_path = test_db
    from app.repositories.transformation_models import AngularUpdateRecordModel
    from app.repositories.session import session_scope

    with session_scope() as s:
        record = AngularUpdateRecordModel(
            id=f"ang-{uuid4().hex[:12]}",
            run_id=run_id,
            stage_id=stage_id,
            idempotency_key="seed-key-001",
            actor="tester",
            status=AngularUpdateStatus.RUNNING.value,
            target_version_status=TargetVersionStatus.INCONCLUSIVE.value,
            source_version="17.0.0",
            target_version="18.0.0",
            artifact_ids=[],
            state_version=1,
            event_sequence=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(record)

    return run_id, stage_id, tmp_db_path


class TestCompleteAngularUpdate:
    def test_complete_happy_path(self, client, seeded_db):
        run_id, stage_id, _ = seeded_db
        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/angular-update/complete",
            json={
                "run_id": run_id,
                "stage_id": stage_id,
                "expected_state_version": 1,
                "idempotency_key": "complete-001",
                "actor": "tester",
                "command_execution_id": "exec-test-001",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["status"] == "succeeded"
        assert data["stage_id"] == stage_id
        assert data["run_id"] == run_id

    def test_complete_run_not_found(self, client, seeded_db):
        run_id, stage_id, _ = seeded_db
        response = client.post(
            f"/api/v1/runs/nonexistent/stages/{stage_id}/angular-update/complete",
            json={
                "run_id": run_id,
                "stage_id": stage_id,
                "expected_state_version": 1,
                "idempotency_key": "complete-404",
                "actor": "tester",
                "command_execution_id": "exec-test-002",
            },
        )
        assert response.status_code == 404

    def test_complete_no_active_update(self, client, test_db):
        run_id, stage_id, _ = test_db
        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/angular-update/complete",
            json={
                "run_id": run_id,
                "stage_id": stage_id,
                "expected_state_version": 1,
                "idempotency_key": "complete-no-update",
                "actor": "tester",
                "command_execution_id": "exec-test-003",
            },
        )
        assert response.status_code == 409

    def test_complete_stale_state_version(self, client, seeded_db):
        run_id, stage_id, _ = seeded_db
        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/angular-update/complete",
            json={
                "run_id": run_id,
                "stage_id": stage_id,
                "expected_state_version": 99,
                "idempotency_key": "complete-stale",
                "actor": "tester",
                "command_execution_id": "exec-test-004",
            },
        )
        assert response.status_code == 409


class TestVerifyTargetVersion:
    def test_verify_happy_path(self, client, seeded_db):
        run_id, stage_id, _ = seeded_db
        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/target-version/verify",
            json={
                "run_id": run_id,
                "stage_id": stage_id,
                "expected_state_version": 1,
                "idempotency_key": "verify-001",
                "actor": "tester",
                "command_execution_id": "exec-verify-001",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "target_version_status" in data
        assert "evidence_sources" in data
        assert "all_sources_agree" in data
        assert "disagreements" in data
        assert "artifact_ids" in data
        assert data["run_id"] == run_id
        assert data["stage_id"] == stage_id

    def test_verify_run_not_found(self, client, seeded_db):
        run_id, stage_id, _ = seeded_db
        response = client.post(
            f"/api/v1/runs/nonexistent/stages/{stage_id}/target-version/verify",
            json={
                "run_id": run_id,
                "stage_id": stage_id,
                "expected_state_version": 1,
                "idempotency_key": "verify-404",
                "actor": "tester",
                "command_execution_id": "exec-verify-002",
            },
        )
        assert response.status_code == 404

    def test_verify_no_update_record(self, client, test_db):
        run_id, stage_id, _ = test_db
        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/target-version/verify",
            json={
                "run_id": run_id,
                "stage_id": stage_id,
                "expected_state_version": 1,
                "idempotency_key": "verify-no-record",
                "actor": "tester",
                "command_execution_id": "exec-verify-003",
            },
        )
        assert response.status_code == 404
