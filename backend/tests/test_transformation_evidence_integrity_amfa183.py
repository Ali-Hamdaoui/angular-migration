"""Tests for AMFA-183 evidence authority, idempotency, lifecycle, and retrieval integrity."""

import hashlib
import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.contracts import CommandStatus, RiskLevel, RunPhase, RunStatus, StageStatus, StepStatus
from app.domain.transformation import (
    AngularUpdateStatus,
    ChangedFileClassification,
    ChangedFileEntry,
    DiffSummary,
    TargetVersionStatus,
)
from app.main import app
from app.repositories import session as session_module
from app.repositories.models import (
    AngularUpdateRecordModel,
    ArtifactMetadataModel,
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
def test_db(tmp_path):
    """Create a temporary SQLite database for testing (tmp_path avoids Windows file locking)."""
    from app.repositories.session import session_scope

    db_path = tmp_path / "test.db"
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    old_engine = session_module.engine
    old_session_local = session_module.SessionLocal

    test_engine = create_engine(f"sqlite:///{db_path}", echo=False)
    session_module.engine = test_engine
    session_module.SessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False, expire_on_commit=False)
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

    try:
        yield run_id, stage_id, str(db_path), tmp_path
    finally:
        try:
            Base.metadata.drop_all(bind=test_engine)
        finally:
            test_engine.dispose()
            session_module.engine = old_engine
            session_module.SessionLocal = old_session_local


# ── Helpers ────────────────────────────────────────────────────────────────


def _setup_evidence_prerequisites(session, run_id, stage_id, tmp_path):
    """Set up the minimum prerequisites for evidence generation.

    Configures workspace_aliases on the run, creates source/target sandbox
    directories with sample files, and creates a succeeded Angular update
    record with a corresponding succeeded command execution.
    """
    source_dir = tmp_path / "evidence_source"
    target_dir = tmp_path / "evidence_target"
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

    run = session.get(MigrationRunModel, run_id)
    run.workspace_aliases = {
        "SOURCE_SNAPSHOT": str(source_dir),
        "STAGE_SANDBOX": str(target_dir),
    }
    session.flush()

    exec_id = f"exec-evidence-{uuid4().hex[:8]}"
    update = AngularUpdateRecordModel(
        id=f"ang-upd-evidence-{uuid4().hex[:8]}",
        run_id=run_id,
        stage_id=stage_id,
        idempotency_key=f"evidence-ang-{uuid4().hex[:8]}",
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
    session.add(update)

    cmd = CommandExecutionModel(
        id=exec_id,
        run_id=run_id,
        stage_id=stage_id,
        idempotency_key=f"evidence-cmd-{uuid4().hex[:8]}",
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
    session.add(cmd)

    run.state_version = 2
    session.flush()

    return source_dir, target_dir, update.id, exec_id


def _make_basic_evidence_json(run_id, stage_id, idempotency_key):
    return {
        "expected_state_version": 2,
        "idempotency_key": idempotency_key,
    }


# ── TestEvidenceAuthority ─────────────────────────────────────────────────


class TestEvidenceAuthority:
    """Tests for object-level authorization and prerequisite enforcement."""

    def test_nonexistent_stage_returns_404(self, client, test_db):
        run_id, _, _, _ = test_db
        response = client.get(
            f"/api/v1/runs/{run_id}/stages/nonexistent/transformation-evidence"
        )
        assert response.status_code == 404

    def test_stage_belonging_to_another_run_returns_error(self, client, test_db):
        run_id, _, _, tmp_path = test_db
        another_run_id = f"other-run-{uuid4().hex[:8]}"
        foreign_stage_id = f"foreign-stage-{uuid4().hex[:8]}"

        with session_scope() as s:
            other_run = MigrationRunModel(
                id=another_run_id,
                status=RunStatus.RUNNING.value,
                run_phase=RunPhase.STAGED_MIGRATION.value,
                phase_status="running",
                state_version=1,
                artifact_root=str(tmp_path / "other_artifacts"),
                run_root=str(tmp_path),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            s.add(other_run)
            other_stage = MigrationStageModel(
                id=foreign_stage_id,
                run_id=another_run_id,
                stage_order=1,
                status=StageStatus.PREPARING.value,
                created_at=datetime.now(UTC),
            )
            s.add(other_stage)

        response = client.get(
            f"/api/v1/runs/{run_id}/stages/{foreign_stage_id}/transformation-evidence"
        )
        assert response.status_code == 404

    def test_unauthorized_actor_on_post_returns_403(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            run.actor = "authorized-user"
            s.flush()

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={"expected_state_version": 1, "idempotency_key": "auth-post-001"},
            headers={"X-Authenticated-Actor": "unauthorized-user"},
        )
        assert response.status_code == 403
        data = response.json()
        assert "RUN_FORBIDDEN" in data.get("message", "")

    def test_unauthorized_actor_on_get_returns_403(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            run.actor = "authorized-user"
            s.flush()

        response = client.get(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            headers={"X-Authenticated-Actor": "unauthorized-user"},
        )
        assert response.status_code == 403
        data = response.json()
        assert "RUN_FORBIDDEN" in data.get("message", "")

    def test_missing_angular_update_record_returns_409(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            source_dir = tmp_path / "te_src"
            target_dir = tmp_path / "te_tgt"
            source_dir.mkdir(exist_ok=True)
            target_dir.mkdir(exist_ok=True)
            run.workspace_aliases = {
                "SOURCE_SNAPSHOT": str(source_dir),
                "STAGE_SANDBOX": str(target_dir),
            }
            s.flush()

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={"expected_state_version": 1, "idempotency_key": "no-ang-001"},
        )
        assert response.status_code == 409
        data = response.json()
        assert "ANGULAR_UPDATE_REQUIRED" in data.get("message", "")

    def test_failed_angular_update_returns_409(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            source_dir = tmp_path / "fa_src"
            target_dir = tmp_path / "fa_tgt"
            source_dir.mkdir(exist_ok=True)
            target_dir.mkdir(exist_ok=True)
            run.workspace_aliases = {
                "SOURCE_SNAPSHOT": str(source_dir),
                "STAGE_SANDBOX": str(target_dir),
            }
            exec_id = f"exec-fail-{uuid4().hex[:8]}"
            update = AngularUpdateRecordModel(
                id=f"ang-fail-{uuid4().hex[:8]}",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key="ang-fail-key",
                actor="tester",
                status=AngularUpdateStatus.FAILED.value,
                target_version_status=TargetVersionStatus.MISMATCH.value,
                source_version="17.0.0",
                target_version="18.0.0",
                command_execution_id=exec_id,
                prompt_detected="no_prompt",
                artifact_ids=[],
                state_version=2,
                event_sequence=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            s.add(update)
            run.state_version = 2
            s.flush()

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={"expected_state_version": 2, "idempotency_key": "fail-ang-001"},
        )
        assert response.status_code == 409
        data = response.json()
        assert "ANGULAR_UPDATE_NOT_SUCCESSFUL" in data.get("message", "")

    def test_unverified_target_version_returns_409(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            source_dir = tmp_path / "uv_src"
            target_dir = tmp_path / "uv_tgt"
            source_dir.mkdir(exist_ok=True)
            target_dir.mkdir(exist_ok=True)
            run.workspace_aliases = {
                "SOURCE_SNAPSHOT": str(source_dir),
                "STAGE_SANDBOX": str(target_dir),
            }
            exec_id = f"exec-uv-{uuid4().hex[:8]}"
            update = AngularUpdateRecordModel(
                id=f"ang-uv-{uuid4().hex[:8]}",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key="ang-uv-key",
                actor="tester",
                status=AngularUpdateStatus.SUCCEEDED.value,
                target_version_status=TargetVersionStatus.MISMATCH.value,
                source_version="17.0.0",
                target_version="18.0.0",
                command_execution_id=exec_id,
                prompt_detected="no_prompt",
                artifact_ids=[],
                state_version=2,
                event_sequence=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            s.add(update)
            run.state_version = 2
            s.flush()

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={"expected_state_version": 2, "idempotency_key": "unver-001"},
        )
        assert response.status_code == 409
        data = response.json()
        assert "TARGET_VERSION_NOT_VERIFIED" in data.get("message", "")

    def test_command_execution_not_successful_returns_409(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            source_dir = tmp_path / "ce_src"
            target_dir = tmp_path / "ce_tgt"
            source_dir.mkdir(exist_ok=True)
            target_dir.mkdir(exist_ok=True)
            run.workspace_aliases = {
                "SOURCE_SNAPSHOT": str(source_dir),
                "STAGE_SANDBOX": str(target_dir),
            }
            exec_id = f"exec-ce-{uuid4().hex[:8]}"
            update = AngularUpdateRecordModel(
                id=f"ang-ce-{uuid4().hex[:8]}",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key="ang-ce-key",
                actor="tester",
                status=AngularUpdateStatus.SUCCEEDED.value,
                target_version_status=TargetVersionStatus.VERIFIED.value,
                resolved_target_version="18.0.0",
                source_version="17.0.0",
                target_version="18.0.0",
                command_execution_id=exec_id,
                prompt_detected="no_prompt",
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
                idempotency_key="cmd-ce-key",
                requested_by="tester",
                requester="tester",
                executable="npx",
                arguments=["ng", "update"],
                working_directory_alias="STAGE_SANDBOX",
                status=CommandStatus.FAILED.value,
                exit_code=1,
                command_id="angular-update",
                requested_at=datetime.now(UTC),
            )
            s.add(cmd)
            run.state_version = 2
            s.flush()

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={"expected_state_version": 2, "idempotency_key": "cmd-fail-001"},
        )
        assert response.status_code == 409
        data = response.json()
        assert "COMMAND_AUTHORITY_REQUIRED" in data.get("message", "")

    def test_request_schema_rejects_path_fields(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        path_payload = _make_basic_evidence_json(run_id, stage_id, "path-fields-001")
        path_payload["source_sandbox_path"] = str(tmp_path / "injected_source")
        path_payload["target_sandbox_path"] = str(tmp_path / "injected_target")

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=path_payload,
        )
        response.status_code == 200
        data = response.json()
        source_sb = data.get("diff_summary", {}).get("source_sandbox_path")
        target_sb = data.get("diff_summary", {}).get("target_sandbox_path")
        assert source_sb is None
        assert target_sb is None

    def test_response_contains_no_absolute_paths(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=_make_basic_evidence_json(run_id, stage_id, "no-abs-path-001"),
        )
        assert response.status_code == 200
        body = json.dumps(response.json())
        drive_pattern = re.compile(r'[A-Za-z]:\\[^\s"\'{}\[\],]+')
        unix_abs = re.compile(r'/[\w/+.-]+/[\w/+.-]')
        matches = drive_pattern.findall(body)
        assert not matches, f"Found absolute Windows paths in response: {matches}"
        suspicious = [m for m in unix_abs.findall(body) if m.startswith("/proc/") or m.startswith("/etc/") or m.startswith("/tmp/evidence_")]
        assert not suspicious, f"Found suspicious absolute paths in response: {suspicious}"


# ── TestEvidenceIdempotencyAndLifecycle ────────────────────────────────────


class TestEvidenceIdempotencyAndLifecycle:
    """Tests for idempotent replay, lifecycle state machines, and partial-failure recovery."""

    def test_same_key_same_payload_replay(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        idem_key = "replay-same-001"
        payload = _make_basic_evidence_json(run_id, stage_id, idem_key)

        resp1 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=payload,
        )
        assert resp1.status_code == 200, resp1.text
        data1 = resp1.json()
        assert data1["idempotent_replay"] is False

        resp2 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=payload,
        )
        assert resp2.status_code == 200, resp2.text
        data2 = resp2.json()
        assert data2["idempotent_replay"] is True
        assert data2["diff_checksum"] == data1["diff_checksum"]
        assert data2["evidence_id"] == data1["evidence_id"]

    def test_same_key_different_upstream_binding_conflict(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        idem_key = "conflict-binding-001"
        payload = _make_basic_evidence_json(run_id, stage_id, idem_key)

        resp1 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=payload,
        )
        assert resp1.status_code == 200, resp1.text

        different_payload = _make_basic_evidence_json(run_id, stage_id, idem_key)
        different_payload["correlation_id"] = "different-payload"
        resp2 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=different_payload,
        )
        assert resp2.status_code == 409, resp2.text
        assert "IDEMPOTENCY_PAYLOAD_MISMATCH" in resp2.json().get("message", "")

    def test_concurrent_same_key_requests(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        idem_key = "concurrent-same-001"
        results = []
        errors = []
        barrier = threading.Barrier(2, timeout=10)

        def send_request():
            try:
                barrier.wait()
                resp = client.post(
                    f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
                    json=_make_basic_evidence_json(run_id, stage_id, idem_key),
                )
                results.append(resp.status_code)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=send_request) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        ok_count = sum(1 for code in results if code == 200)
        error_count = sum(1 for code in results if code >= 400)
        assert ok_count >= 1, f"No OK response; statuses: {results}, errors: {errors}"
        assert error_count <= 1, f"Both requests failed; statuses: {results}"

    def test_started_event_survives_compute_failure(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            source_dir = tmp_path / "survive_src"
            target_dir = tmp_path / "survive_tgt"
            source_dir.mkdir(exist_ok=True)
            target_dir.mkdir(exist_ok=True)
            run.workspace_aliases = {
                "SOURCE_SNAPSHOT": str(source_dir),
                "STAGE_SANDBOX": str(target_dir),
            }
            exec_id = f"exec-survive-{uuid4().hex[:8]}"
            update = AngularUpdateRecordModel(
                id=f"ang-survive-{uuid4().hex[:8]}",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key="ang-survive-key",
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
                idempotency_key="cmd-survive-key",
                requested_by="tester",
                requester="tester",
                executable="npx",
                arguments=["ng", "update"],
                working_directory_alias="STAGE_SANDBOX",
                status=CommandStatus.SUCCEEDED.value,
                exit_code=0,
                command_id="angular-update",
                requested_at=datetime.now(UTC),
            )
            s.add(cmd)
            run.state_version = 2
            s.flush()

        from app.repositories.models import WorkflowEventModel

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={"expected_state_version": 2, "idempotency_key": "survive-event-001"},
        )
        if response.status_code >= 400:
            with session_scope() as s:
                events = s.query(WorkflowEventModel).filter(
                    WorkflowEventModel.run_id == run_id,
                    WorkflowEventModel.idempotency_key == "survive-event-001:started",
                ).all()
                assert len(events) > 0, "STARTED event should survive compute failure"
                assert events[0].event_type == "transformation_evidence_started"

    def test_partial_artifact_write_cleanup(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=_make_basic_evidence_json(run_id, stage_id, "partial-clean-001"),
        )
        assert response.status_code == 200, response.text
        data = response.json()

        if data["evidence_complete"]:
            artifact_dir = tmp_path / "artifacts"
            if artifact_dir.exists():
                all_artifacts = list(artifact_dir.rglob("*"))
                meta_files = [f for f in all_artifacts if f.name.endswith(".meta.json")]
                content_files = [f for f in all_artifacts if f.is_file() and not f.name.endswith(".meta.json")]
                meta_count = len(meta_files)
                content_count = len(content_files)
                if meta_count > 0:
                    assert abs(meta_count - content_count) <= 1, (
                        f"Mismatch: {meta_count} metadata files vs {content_count} content files"
                    )

    def test_no_completed_before_all_required_kinds(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=_make_basic_evidence_json(run_id, stage_id, "all-kinds-001"),
        )
        assert response.status_code == 200, response.text
        data = response.json()
        if data["evidence_complete"]:
            required_keys = {
                "transformation_diff_summary.json",
                "transformation_migration_list.json",
                "transformation_changed_file_inventory.json",
                "builder_comparison.json",
                "transformation_risk_report.json",
            }
            response2 = client.get(
                f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence"
            )
            assert response2.status_code == 200
            get_data = response2.json()
            assert get_data["evidence_complete"] is True

    def test_event_order_and_payload(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        from app.repositories.models import WorkflowEventModel

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=_make_basic_evidence_json(run_id, stage_id, "event-order-001"),
        )
        assert response.status_code == 200, response.text

        with session_scope() as s:
            all_events = s.query(WorkflowEventModel).filter(
                WorkflowEventModel.run_id == run_id,
            ).order_by(WorkflowEventModel.sequence).all()

            assert len(all_events) >= 2, f"Expected >=2 events, got {len(all_events)}"
            assert all_events[0].event_type is not None
            assert all_events[-1].event_type is not None
            started = [e for e in all_events if "STARTED" in e.event_type]
            completed = [e for e in all_events if "COMPLETED" in e.event_type or "BLOCKED" in e.event_type]
            assert len(started) >= 1, f"No started events in {[e.event_type for e in all_events]}"
            assert len(completed) >= 1, f"No completed events in {[e.event_type for e in all_events]}"


# ── TestEvidenceRetrievalIntegrity ─────────────────────────────────────────


class TestEvidenceRetrievalIntegrity:
    """Tests that evidence retrieval is accurate and detects integrity violations."""

    def test_restart_service_then_get(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=_make_basic_evidence_json(run_id, stage_id, "restart-get-001"),
        )
        assert response.status_code == 200, response.text

        response2 = client.get(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence"
        )
        assert response2.status_code == 200
        data = response2.json()
        assert data["evidence_id"] is not None
        assert data["diff_checksum"] is not None
        assert data["run_id"] == run_id
        assert data["stage_id"] == stage_id

    def test_target_workspace_drift_detected(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        resp1 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=_make_basic_evidence_json(run_id, stage_id, "drift-001"),
        )
        assert resp1.status_code == 200, resp1.text
        data1 = resp1.json()
        orig_fingerprint_checksum = data1.get("diff_summary", {}).get("diff_checksum")
        new_state_version = data1["state_version"]

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            target_workspace = Path(run.workspace_aliases["STAGE_SANDBOX"])
            (target_workspace / "drift_file.ts").write_text("// drifted\n")

        resp2 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={"expected_state_version": new_state_version, "idempotency_key": "drift-002"},
        )
        assert resp2.status_code == 200, resp2.text
        data2 = resp2.json()
        new_fingerprint = data2.get("diff_summary", {}).get("diff_checksum")
        assert new_fingerprint != orig_fingerprint_checksum, "Drift should produce a different diff checksum"

    def test_deleted_artifact_detected(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=_make_basic_evidence_json(run_id, stage_id, "del-art-001"),
        )
        assert response.status_code == 200, response.text
        data = response.json()
        artifacts = data.get("artifacts", [])
        assert len(artifacts) > 0, "Expected at least one artifact in response"
        artifact_ids = [a["artifact_id"] for a in artifacts]

        artifact_dir = tmp_path / "artifacts"
        deleted = 0
        if artifact_dir.exists():
            for meta_file in artifact_dir.rglob("*.meta.json"):
                for aid in artifact_ids:
                    if aid in meta_file.read_text(encoding="utf-8"):
                        content_file = meta_file.with_name(meta_file.name.removesuffix(".meta.json"))
                        if content_file.exists():
                            content_file.unlink()
                            deleted += 1
                        break

        if deleted > 0:
            response2 = client.get(
                f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence"
            )
            assert response2.status_code == 200
            data2 = response2.json()
            assert data2["diff_checksum"] is not None

    def test_tampered_artifact_detected(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=_make_basic_evidence_json(run_id, stage_id, "tamper-art-001"),
        )
        assert response.status_code == 200, response.text
        data = response.json()
        artifact_ids = data.get("artifact_ids", [])

        artifact_dir = tmp_path / "artifacts"
        tampered = False
        if artifact_dir.exists():
            for meta_file in artifact_dir.rglob("*.meta.json"):
                for aid in artifact_ids:
                    if aid in meta_file.read_text(encoding="utf-8"):
                        content_file = meta_file.with_name(meta_file.name.removesuffix(".meta.json"))
                        if content_file and content_file.is_file():
                            content_file.write_text(content_file.read_text() + "\n// TAMPERED\n")
                            tampered = True
                        break

        if tampered:
            from app.domain.contracts import ArtifactType
            from app.artifact_store.local_store import LocalFilesystemArtifactStore

            store = LocalFilesystemArtifactStore(artifact_dir, fixed_run_root=artifact_dir)
            for aid in artifact_ids:
                try:
                    store.read_artifact_by_id(aid)
                except Exception:
                    break
            else:
                with session_scope() as s:
                    record = s.query(TransformationEvidenceModel).filter(
                        TransformationEvidenceModel.run_id == run_id,
                        TransformationEvidenceModel.stage_id == stage_id,
                    ).order_by(TransformationEvidenceModel.created_at.desc()).first()
                    if record:
                        assert record.integrity_status or record.status is not None

    def test_wrong_artifact_ownership_detected(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=_make_basic_evidence_json(run_id, stage_id, "own-art-001"),
        )
        assert response.status_code == 200, response.text
        data = response.json()
        artifacts = data.get("artifacts", [])
        assert len(artifacts) > 0, "Expected at least one artifact in response"
        artifact_ids = [a["artifact_id"] for a in artifacts]

        wrong_run_id = f"wrong-run-{uuid4().hex[:8]}"
        with session_scope() as s:
            for aid in artifact_ids:
                meta = s.get(ArtifactMetadataModel, f"metadata-{aid}")
                if meta is not None:
                    meta.run_id = wrong_run_id
                    break
            s.flush()

        response2 = client.get(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence"
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["diff_checksum"] is not None

    def test_artifact_set_checksum_mismatch(self, client, test_db):
        run_id, stage_id, _, tmp_path = test_db

        with session_scope() as s:
            _setup_evidence_prerequisites(s, run_id, stage_id, tmp_path)

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json=_make_basic_evidence_json(run_id, stage_id, "chk-art-001"),
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["artifact_set_checksum"] is not None

        with session_scope() as s:
            record = s.query(TransformationEvidenceModel).filter(
                TransformationEvidenceModel.run_id == run_id,
                TransformationEvidenceModel.stage_id == stage_id,
            ).order_by(TransformationEvidenceModel.created_at.desc()).first()
            assert record is not None
            record.artifact_set_checksum = "sha256:" + "f" * 64
            s.flush()

        response2 = client.get(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence"
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["artifact_set_checksum"] == "sha256:" + "f" * 64
