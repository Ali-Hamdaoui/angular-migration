"""API integration tests for G03 transformation endpoints."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.domain.transformation import (
    AngularUpdateStatus,
    ChangedFileClassification,
    ChangedFileEntry,
    DiffSummary,
    G08Decision,
    TargetVersionStatus,
    TransformationEvidenceResult,
)
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_db():
    """Create a temporary SQLite database for testing."""
    from app.domain.contracts import RunPhase, RunStatus, StageStatus, StepStatus
    from app.repositories.models import (
        MigrationRunModel, MigrationStageModel, StageStepModel,
        AngularUpdateRecordModel, TransformationEvidenceModel, G08ApprovalModel,
    )
    from app.repositories.models.base import Base
    from app.repositories.session import engine, session_scope

    # Use a temporary database
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()

    old_engine = engine.url
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.repositories import session as session_module

    test_engine = create_engine(f"sqlite:///{tmp_db.name}", echo=False)
    session_module.engine = test_engine
    session_module.SessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=test_engine)

    # Create a test run and stage
    from datetime import UTC, datetime

    from uuid import uuid4
    run_id = f"test-run-{uuid4().hex[:8]}"
    stage_id = f"test-stage-{uuid4().hex[:8]}"
    step_id = f"test-step-{uuid4().hex[:8]}"

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
            source_version_family="Angular",
            target_version_family="Angular",
            source_version_detected="17.0.0",
            target_version_resolved="18.0.0",
            status=StageStatus.PREPARING.value,
            created_at=datetime.now(UTC),
        )
        s.add(stage)
        step = StageStepModel(
                id=step_id,
                run_id=run_id,
                stage_id=stage_id,
                name="angular-update",
                status=StepStatus.PENDING.value,
                component_type="AngularUpdateService",
            )
        s.add(step)

    yield run_id, stage_id, tmp_db.name

    Base.metadata.drop_all(bind=test_engine)
    Path(tmp_db.name).unlink(missing_ok=True)
    session_module.engine = create_engine(str(old_engine))
    session_module.SessionLocal = sessionmaker(bind=session_module.engine, autocommit=False, autoflush=False, expire_on_commit=False)


class TestAngularUpdateAPI:
    def test_start_update_happy_path(self, client, test_db):
        run_id, stage_id, _ = test_db
        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/angular-update",
            json={
                "expected_state_version": 1,
                "idempotency_key": "test-start-001",
                "actor": "tester",
                "source_version": "17.0.0",
                "target_version": "18.0.0",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["status"] == "running"
        assert data["stage_id"] == stage_id

    def test_get_update(self, client, test_db):
        run_id, stage_id, _ = test_db
        # Start the update first
        client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/angular-update",
            json={
                "expected_state_version": 1,
                "idempotency_key": "test-get-001",
                "actor": "tester",
                "source_version": "17.0.0",
                "target_version": "18.0.0",
            },
        )
        response = client.get(f"/api/v1/runs/{run_id}/stages/{stage_id}/angular-update")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"

    def test_update_stale_version(self, client, test_db):
        run_id, stage_id, _ = test_db
        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/angular-update",
            json={
                "expected_state_version": 99,  # wrong version
                "idempotency_key": "test-stale-001",
                "actor": "tester",
                "source_version": "17.0.0",
                "target_version": "18.0.0",
            },
        )
        assert response.status_code == 409

    def test_update_not_found(self, client, test_db):
        run_id, _, _ = test_db
        response = client.get(f"/api/v1/runs/{run_id}/stages/nonexistent/angular-update")
        assert response.status_code == 404


class TestTransformationEvidenceAPI:
    def test_generate_evidence(self, client, test_db):
        run_id, stage_id, _ = test_db
        # Create sandbox paths
        source_sandbox = tempfile.mkdtemp(prefix="src_sandbox_")
        target_sandbox = tempfile.mkdtemp(prefix="tgt_sandbox_")

        # Create some test files in sandboxes
        Path(source_sandbox, "package.json").write_text(
            json.dumps({"dependencies": {"@angular/core": "17.0.0"}})
        )
        Path(target_sandbox, "package.json").write_text(
            json.dumps({"dependencies": {"@angular/core": "18.0.0"}})
        )
        Path(source_sandbox, "src").mkdir(parents=True, exist_ok=True)
        Path(target_sandbox, "src").mkdir(parents=True, exist_ok=True)
        Path(source_sandbox, "src/main.ts").write_text("// Angular 17 main\n")
        Path(target_sandbox, "src/main.ts").write_text("// Angular 18 main\n")

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "test-evidence-001",
                "actor": "tester",
                "source_sandbox_path": source_sandbox,
                "target_sandbox_path": target_sandbox,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["total_files_changed"] >= 1
        assert data["diff_checksum"] is not None

        # Cleanup
        import shutil
        shutil.rmtree(source_sandbox, ignore_errors=True)
        shutil.rmtree(target_sandbox, ignore_errors=True)

    def test_get_evidence(self, client, test_db):
        run_id, stage_id, _ = test_db
        source_sandbox = tempfile.mkdtemp(prefix="src_")
        target_sandbox = tempfile.mkdtemp(prefix="tgt_")
        Path(source_sandbox, "file.ts").write_text("a")
        Path(target_sandbox, "file.ts").write_text("b")

        client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "test-evidence-get-002",
                "actor": "tester",
                "source_sandbox_path": source_sandbox,
                "target_sandbox_path": target_sandbox,
            },
        )
        response = client.get(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_files_changed"] >= 1

        import shutil
        shutil.rmtree(source_sandbox, ignore_errors=True)
        shutil.rmtree(target_sandbox, ignore_errors=True)


class TestG08ApprovalAPI:
    def test_get_g08_not_found(self, client, test_db):
        run_id, stage_id, _ = test_db
        response = client.get(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08"
        )
        assert response.status_code == 404

    def test_g08_decision_with_complete_evidence(self, client, test_db):
        run_id, stage_id, tmp_db_path = test_db

        # Setup: Create angular update and evidence records first
        from app.repositories.session import session_scope
        from app.repositories.models import MigrationRunModel
        from app.repositories.transformation_models import (
            AngularUpdateRecordModel,
            TransformationEvidenceModel,
        )
        from datetime import UTC, datetime

        # We need to inject some test data into the DB for the G08 endpoint
        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            assert run is not None

            update = AngularUpdateRecordModel(
                id=f"ang-{stage_id}",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key="test-ang-g08",
                actor="tester",
                status=AngularUpdateStatus.SUCCEEDED.value,
                target_version_status=TargetVersionStatus.VERIFIED.value,
                resolved_target_version="18.0.0",
                source_version="17.0.0",
                target_version="18.0.0",
                artifact_ids=[],
                state_version=2,
                event_sequence=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            s.add(update)
            evidence = TransformationEvidenceModel(
                id=f"tev-{stage_id}",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key="test-evidence-g08",
                actor="tester",
                status="completed",
                overall_risk_level="low",
                total_files_changed=10,
                diff_checksum="sha256:test123",
                diff_summary=DiffSummary(
                    total_files_changed=10,
                    total_lines_added=100,
                    total_lines_removed=50,
                    diff_checksum="sha256:test123",
                ).model_dump(mode="json"),
                evidence_complete=True,
                artifact_ids=[],
                state_version=3,
                event_sequence=2,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            s.add(evidence)
            # Update the run's state_version to match
            run.state_version = 3
            s.flush()

        # Initialize G08
        init_resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/package",
            json={
                "expected_state_version": 3,
                "idempotency_key": "g08-init-test",
                "actor": "tester",
                "decision": "approved",
                "gate_id": "G08",
            },
        )
        assert init_resp.status_code == 200, f"Init failed: {init_resp.text}"
        init_data = init_resp.json()
        assert init_data["status"] == "pending"
        new_state_version = init_data["state_version"]

        # Approve G08
        decide_resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json={
                "expected_state_version": new_state_version,
                "idempotency_key": "g08-decide-test",
                "actor": "tester",
                "decision": "approved",
                "gate_id": "G08",
            },
        )
        assert decide_resp.status_code == 200, f"Decide failed: {decide_resp.text}"
        decide_data = decide_resp.json()
        assert decide_data["decision"] == "approved"

    def test_g08_reject_incomplete(self, client, test_db):
        run_id, stage_id, tmp_db_path = test_db

        from app.repositories.session import session_scope
        from app.repositories.models import MigrationRunModel
        from app.repositories.transformation_models import (
            AngularUpdateRecordModel,
            TransformationEvidenceModel,
        )
        from app.domain.contracts import RiskLevel
        from datetime import UTC, datetime

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            assert run is not None

            update = AngularUpdateRecordModel(
                id=f"ang-rej-{stage_id}",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key="test-ang-rej-g08",
                actor="tester",
                status=AngularUpdateStatus.FAILED.value,
                target_version_status=TargetVersionStatus.FAILED.value,
                source_version="17.0.0",
                target_version="18.0.0",
                artifact_ids=[],
                state_version=2,
                event_sequence=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            s.add(update)
            evidence = TransformationEvidenceModel(
                id=f"tev-rej-{stage_id}",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key="test-evidence-rej-g08",
                actor="tester",
                status="blocked",
                overall_risk_level=RiskLevel.HIGH.value,
                total_files_changed=0,
                diff_checksum="sha256:none",
                diff_summary=DiffSummary(
                    total_files_changed=0,
                    total_lines_added=0,
                    total_lines_removed=0,
                    diff_checksum="sha256:none",
                ).model_dump(mode="json"),
                evidence_complete=False,
                artifact_ids=[],
                state_version=3,
                event_sequence=2,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            s.add(evidence)
            # Update the run's state_version to match
            run.state_version = 3
            s.flush()

        init_resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/package",
            json={
                "expected_state_version": 3,
                "idempotency_key": "g08-init-rej-test",
                "actor": "tester",
                "decision": "approved",
                "gate_id": "G08",
            },
        )
        assert init_resp.status_code == 200
        init_data = init_resp.json()
        new_state_version = init_data["state_version"]

        decide_resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json={
                "expected_state_version": new_state_version,
                "idempotency_key": "g08-decide-rej-test",
                "actor": "tester",
                "decision": "approved",
                "gate_id": "G08",
            },
        )
        assert decide_resp.status_code == 200
        decide_data = decide_resp.json()
        # Should be rejected because evidence is incomplete
        assert decide_data["decision"] != "approved"
        assert decide_data["status"] == "stale"
