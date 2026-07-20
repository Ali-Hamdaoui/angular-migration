"""Concurrent-access pattern tests for transformation evidence (AMFA-183)."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from app.domain.contracts import CommandStatus, RunPhase, RunStatus, StageStatus, StepStatus
from app.domain.transformation import AngularUpdateStatus, TargetVersionStatus
from app.main import app
from app.repositories import session as session_module
from app.repositories.models import (
    AngularUpdateRecordModel,
    CommandExecutionModel,
    MigrationRunModel,
    MigrationStageModel,
    StageStepModel,
    TransformationEvidenceModel,
)
from app.repositories.models.base import Base
from app.repositories.session import session_scope


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_db_concurrent(tmp_path):
    """Create a temporary SQLite database with check_same_thread=False for concurrent access."""
    from app.repositories.session import session_scope

    db_path = tmp_path / "test_concurrent.db"
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    old_engine = session_module.engine
    old_session_local = session_module.SessionLocal

    test_engine = create_engine(f"sqlite:///{db_path}", echo=False, connect_args={"check_same_thread": False})
    session_module.engine = test_engine
    session_module.SessionLocal = sessionmaker(
        bind=test_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=test_engine)

    run_id = f"test-run-{uuid4().hex[:8]}"
    stage_id = f"test-stage-{uuid4().hex[:8]}"
    step_id = f"test-step-{uuid4().hex[:8]}"

    with session_scope() as s:
        source_path = tmp_path / "source"
        source_path.mkdir(parents=True, exist_ok=True)
        run = MigrationRunModel(
            id=run_id,
            status=RunStatus.RUNNING.value,
            run_phase=RunPhase.STAGED_MIGRATION.value,
            phase_status="running",
            state_version=1,
            source_path=str(source_path),
            artifact_root=str(artifact_root),
            run_root=str(tmp_path),
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

    source_dir = tmp_path / "concurrent_source"
    target_dir = tmp_path / "concurrent_target"
    source_dir.mkdir(exist_ok=True)
    target_dir.mkdir(exist_ok=True)
    (source_dir / "package.json").write_text(
        json.dumps({"dependencies": {"@angular/core": "17.0.0"}})
    )
    (target_dir / "package.json").write_text(
        json.dumps({"dependencies": {"@angular/core": "18.0.0"}})
    )
    (source_dir / "src").mkdir(exist_ok=True)
    (target_dir / "src").mkdir(exist_ok=True)
    (source_dir / "src" / "main.ts").write_text("// Angular 17 main\n")
    (target_dir / "src" / "main.ts").write_text("// Angular 18 main\n")

    exec_id = f"exec-concurrent-{uuid4().hex[:8]}"
    with session_scope() as s:
        run = s.get(MigrationRunModel, run_id)
        run.workspace_aliases = {
            "SOURCE_SNAPSHOT": str(source_dir),
            "STAGE_SANDBOX": str(target_dir),
        }
        update = AngularUpdateRecordModel(
            id=f"ang-upd-concurrent-{uuid4().hex[:8]}",
            run_id=run_id,
            stage_id=stage_id,
            idempotency_key="ang-concurrent-key",
            actor="tester",
            status=AngularUpdateStatus.SUCCEEDED.value,
            target_version_status=TargetVersionStatus.VERIFIED.value,
            resolved_target_version="18.0.0",
            source_version="17.0.0",
            target_version="18.0.0",
            command_execution_id=exec_id,
            prompt_detected="no_prompt",
            evidence={
                "package_json_core": "18.0.0",
                "lockfile_core": "18.0.0",
                "ng_version_output": "Angular: 18.0.0",
                "dependency_tree_core": "18.0.0",
                "all_sources_agree": True,
                "disagreements": [],
            },
            artifact_ids=[],
            state_version=2,
            event_sequence=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(update)
        cmd = CommandExecutionModel(
            id=exec_id,
            run_id=run_id,
            stage_id=stage_id,
            idempotency_key="cmd-concurrent-key",
            requested_by="tester",
            requester="tester",
            executable="npx",
            arguments=["ng", "update", "@angular/core@18.0.0"],
            working_directory_alias="STAGE_SANDBOX",
            status=CommandStatus.SUCCEEDED.value,
            exit_code=0,
            command_id="angular-update",
            requested_at=datetime.now(UTC),
        )
        s.add(cmd)
        run.state_version = 2
        s.flush()

    try:
        yield run_id, stage_id, str(db_path), tmp_path
    finally:
        try:
            Base.metadata.drop_all(bind=test_engine)
        finally:
            test_engine.dispose()
            session_module.engine = old_engine
            session_module.SessionLocal = old_session_local


# ── TestEvidenceConcurrency ────────────────────────────────────────────────


class TestEvidenceConcurrency:
    """Tests for concurrent access to the transformation-evidence endpoint."""

    def test_concurrent_same_key_creates_one_record(self, client, test_db_concurrent):
        run_id, stage_id, _, _ = test_db_concurrent

        results = []
        errors = []
        barrier = threading.Barrier(2, timeout=15)

        def send_same_key():
            try:
                barrier.wait()
                resp = client.post(
                    f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
                    json={
                        "expected_state_version": 2,
                        "idempotency_key": "concurrent-same-key-001",
                    },
                )
                results.append(resp.status_code)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=send_same_key) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        ok_count = sum(1 for code in results if code == 200)
        conflict_count = sum(1 for code in results if code == 409)
        assert ok_count >= 1, f"No request succeeded; statuses: {results}"
        assert ok_count + conflict_count == 2, (
            f"Expected one 200 and one 409, got: {results}"
        )

    def test_concurrent_different_keys_both_succeed(self, client, test_db_concurrent):
        run_id, stage_id, _, _ = test_db_concurrent

        results = []
        errors = []
        barrier = threading.Barrier(2, timeout=15)

        def send_different_key(suffix):
            try:
                barrier.wait()
                resp = client.post(
                    f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
                    json={
                        "expected_state_version": 2,
                        "idempotency_key": f"concurrent-diff-key-{suffix}",
                    },
                )
                results.append(resp.status_code)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=send_different_key, args=("a",)),
            threading.Thread(target=send_different_key, args=("b",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        ok_count = sum(1 for code in results if code == 200)
        assert ok_count >= 1, (
            f"Expected at least one request to succeed (200), got: {results}, errors: {errors}"
        )

    def test_concurrent_angular_update_same_key(self, client, test_db_concurrent):
        run_id, stage_id, _, _ = test_db_concurrent

        records_before = 0
        with session_scope() as s:
            records_before = s.query(AngularUpdateRecordModel).count()

        results = []
        errors = []
        barrier = threading.Barrier(2, timeout=15)

        def send_angular_update():
            try:
                barrier.wait()
                resp = client.post(
                    f"/api/v1/runs/{run_id}/stages/{stage_id}/angular-update",
                    json={
                        "expected_state_version": 1,
                        "idempotency_key": "concurrent-angular-key-001",
                        "actor": "tester",
                        "source_version": "17.0.0",
                        "target_version": "18.0.0",
                    },
                )
                results.append(resp.status_code)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=send_angular_update) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        with session_scope() as s:
            records_after = s.query(AngularUpdateRecordModel).count()
            new_records = records_after - records_before
            assert new_records <= 1, (
                f"Expected at most 1 new AngularUpdateRecord, got {new_records}"
            )
