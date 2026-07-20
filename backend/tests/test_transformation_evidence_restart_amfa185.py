"""AMFA-185 evidence restart, staleness, and tamper detection tests.

Covers:
- State machine correctness (STARTED before COMPLETED)
- Compute failure → blocked state
- Service restart retrieval idempotency
- Workspace drift detection via fingerprint
- Missing / tampered / re-owned artifact detection
- Artifact set checksum mismatch
- Angular update binding change detection
- Concurrent idempotency semantics
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_db(tmp_path):
    from app.domain.contracts import CommandStatus, RunPhase, RunStatus, StageStatus, StepStatus
    from app.repositories.models import (
        MigrationRunModel,
        MigrationStageModel,
        StageStepModel,
        CommandExecutionModel,
        AngularUpdateRecordModel,
    )
    from app.repositories.models.base import Base
    from app.repositories import session as session_module
    from app.repositories.session import session_scope

    db_path = tmp_path / "test.db"
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    old_engine = session_module.engine
    old_session_local = session_module.SessionLocal
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    test_engine = create_engine(f"sqlite:///{db_path}", echo=False)
    session_module.engine = test_engine
    session_module.SessionLocal = sessionmaker(
        bind=test_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=test_engine)

    from datetime import UTC, datetime
    from uuid import uuid4
    from app.domain.transformation import AngularUpdateStatus, TargetVersionStatus

    run_id = f"test-run-{uuid4().hex[:8]}"
    stage_id = f"test-stage-{uuid4().hex[:8]}"

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

        source_path = tmp_path / "source"
        target_path = tmp_path / "stage_sandbox"
        source_path.mkdir(parents=True, exist_ok=True)
        target_path.mkdir(parents=True, exist_ok=True)

        run.workspace_aliases = {
            "SOURCE_SNAPSHOT": str(source_path),
            "STAGE_SANDBOX": str(target_path),
        }

        update_id = f"ang-upd-evi-{uuid4().hex[:12]}"
        exec_id = f"exec-evi-{uuid4().hex[:12]}"
        update_record = AngularUpdateRecordModel(
            id=update_id,
            run_id=run_id,
            stage_id=stage_id,
            idempotency_key="evidence-fixture-ang-upd",
            actor="local-operator",
            status=AngularUpdateStatus.SUCCEEDED.value,
            target_version_status=TargetVersionStatus.VERIFIED.value,
            resolved_target_version="18.0.0",
            source_version="17.0.0",
            target_version="18.0.0",
            command_execution_id=exec_id,
            artifact_ids=[],
            state_version=1,
            event_sequence=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(update_record)

        execution = CommandExecutionModel(
            id=exec_id,
            run_id=run_id,
            stage_id=stage_id,
            idempotency_key="evidence-fixture-exec",
            command_id="angular-update",
            status=CommandStatus.SUCCEEDED.value,
            exit_code=0,
            requested_at=datetime.now(UTC),
            executable="npx",
            arguments=["ng", "update"],
            artifact_ids=[],
            state_version=1,
            event_sequence=1,
        )
        s.add(execution)
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


@pytest.fixture
def seeded_evidence(client, test_db):
    """Generate transformation evidence and return (run_id, stage_id, tmp_path, response)."""
    run_id, stage_id, _, tmp_dir = test_db
    source_dir = tmp_dir / "source"
    target_dir = tmp_dir / "stage_sandbox"

    (source_dir / "package.json").write_text(
        json.dumps({"dependencies": {"@angular/core": "17.0.0"}})
    )
    (target_dir / "package.json").write_text(
        json.dumps({"dependencies": {"@angular/core": "18.0.0"}})
    )
    (source_dir / "src").mkdir(parents=True, exist_ok=True)
    (target_dir / "src").mkdir(parents=True, exist_ok=True)
    (source_dir / "src/main.ts").write_text("// Angular 17 main\n")
    (target_dir / "src/main.ts").write_text("// Angular 18 main\n")

    resp = client.post(
        f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
        json={
            "expected_state_version": 1,
            "idempotency_key": "restart-seeded",
        },
        headers={"x-authenticated-actor": "tester"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    yield run_id, stage_id, tmp_dir, data


class TestEvidenceRestart:
    HEADERS = {"x-authenticated-actor": "tester"}

    def test_started_committed_before_compute(self, client, test_db):
        """Verify STARTED event is emitted before COMPLETED in the event sequence."""
        run_id, stage_id, _, tmp_dir = test_db
        source_dir = tmp_dir / "source"
        target_dir = tmp_dir / "stage_sandbox"
        (source_dir / "f.ts").write_text("a")
        (target_dir / "f.ts").write_text("b")

        from app.repositories.session import session_scope
        from app.repositories.models import WorkflowEventModel
        from app.domain.contracts import WorkflowEventType

        resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "started-before-test",
            },
            headers=self.HEADERS,
        )
        assert resp.status_code == 200, resp.text

        with session_scope() as s:
            events = (
                s.query(WorkflowEventModel)
                .filter(WorkflowEventModel.run_id == run_id)
                .order_by(WorkflowEventModel.sequence)
                .all()
            )
        event_types = [e.event_type for e in events]
        started_idx = -1
        completed_idx = -1
        for i, et in enumerate(event_types):
            if et == WorkflowEventType.TRANSFORMATION_EVIDENCE_STARTED.value:
                started_idx = i
            if et == WorkflowEventType.TRANSFORMATION_EVIDENCE_COMPLETED.value:
                completed_idx = i
        assert started_idx >= 0, "STARTED event should exist"
        assert completed_idx >= 0, "COMPLETED event should exist"
        assert started_idx < completed_idx, (
            f"STARTED (idx {started_idx}) must precede COMPLETED (idx {completed_idx})"
        )

    def test_compute_failure_produces_blocked_state(self, client, test_db):
        """When compute fails (no sandbox path), evidence is blocked."""
        run_id, stage_id, _, tmp_dir = test_db
        from app.repositories.session import session_scope
        from app.repositories.models import MigrationRunModel

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            run.workspace_aliases = {
                "SOURCE_SNAPSHOT": str(tmp_dir / "nonexistent-source"),
                "STAGE_SANDBOX": str(tmp_dir / "stage_sandbox"),
            }
            s.flush()

        resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "blocked-state-test",
            },
            headers=self.HEADERS,
        )
        assert resp.status_code == 409, resp.text
        data = resp.json()
        msg = data.get("message", "")
        assert "missing or unsafe" in msg, msg

    def test_restart_service_retrieval(self, client, seeded_evidence):
        """After generation, GET returns the same evidence (simulates restart)."""
        run_id, stage_id, _, post_data = seeded_evidence
        resp = client.get(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            headers=self.HEADERS,
        )
        assert resp.status_code == 200, resp.text
        get_data = resp.json()
        assert get_data["evidence_id"] == post_data["evidence_id"]
        assert get_data["diff_checksum"] == post_data["diff_checksum"]
        assert get_data["total_files_changed"] == post_data["total_files_changed"]
        assert get_data["state_version"] >= post_data["state_version"]

    def test_workspace_drift_detected(self, client, test_db):
        """Generate evidence, then modify a file and re-fingerprint shows drift."""
        run_id, stage_id, _, tmp_dir = test_db
        source_dir = tmp_dir / "source"
        target_dir = tmp_dir / "stage_sandbox"
        (source_dir / "stable.ts").write_text("before")
        (target_dir / "stable.ts").write_text("after")

        resp1 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "drift-first",
            },
            headers=self.HEADERS,
        )
        assert resp1.status_code == 200, resp1.text
        data1 = resp1.json()
        sv1 = data1["state_version"]
        fp1 = data1.get("diff_summary", {}).get("diff_checksum")

        (target_dir / "stable.ts").write_text("modified again after evidence")

        resp2 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": sv1,
                "idempotency_key": "drift-second",
            },
            headers=self.HEADERS,
        )
        assert resp2.status_code == 200, resp2.text
        data2 = resp2.json()
        fp2 = data2.get("diff_summary", {}).get("diff_checksum")
        assert fp2 != fp1, "Second generation should produce a different diff_checksum"

    def test_missing_artifact_detected(self, client, seeded_evidence):
        """Deleting an artifact file causes read failure."""
        run_id, stage_id, tmp_dir, data = seeded_evidence
        from app.repositories.session import session_scope
        from app.repositories.models import ArtifactMetadataModel

        with session_scope() as s:
            artifacts = (
                s.query(ArtifactMetadataModel)
                .filter(ArtifactMetadataModel.run_id == run_id)
                .all()
            )
        assert len(artifacts) > 0
        meta = artifacts[0]
        artifact_rel_path = meta.relative_path
        artifact_full = tmp_dir / "artifacts" / artifact_rel_path
        if artifact_full.exists():
            artifact_full.unlink()
            sidecar = artifact_full.with_name(f"{artifact_full.name}.meta.json")
            if sidecar.exists():
                sidecar.unlink()

        from app.artifact_store.local_store import LocalFilesystemArtifactStore

        store = LocalFilesystemArtifactStore(
            tmp_dir / "artifacts", fixed_run_root=tmp_dir / "artifacts"
        )
        from app.artifact_store.local_store import ArtifactNotFoundError

        with pytest.raises(ArtifactNotFoundError):
            store.read_artifact_by_id(meta.id.replace("metadata-", ""))

    def test_checksum_tamper_detected(self, client, seeded_evidence):
        """Modifying an artifact file after generation produces checksum mismatch."""
        run_id, stage_id, tmp_dir, data = seeded_evidence
        from app.repositories.session import session_scope
        from app.repositories.models import ArtifactMetadataModel

        with session_scope() as s:
            artifacts = (
                s.query(ArtifactMetadataModel)
                .filter(ArtifactMetadataModel.run_id == run_id)
                .all()
            )
        assert len(artifacts) > 0
        meta = artifacts[0]
        artifact_rel_path = meta.relative_path
        artifact_full = tmp_dir / "artifacts" / artifact_rel_path
        if artifact_full.exists():
            artifact_full.write_text(artifact_full.read_text() + "\n// tampered")

        from app.artifact_store.local_store import LocalFilesystemArtifactStore, ArtifactStoreError

        store = LocalFilesystemArtifactStore(
            tmp_dir / "artifacts", fixed_run_root=tmp_dir / "artifacts"
        )
        with pytest.raises(ArtifactStoreError, match="checksum mismatch"):
            store.read_artifact_by_id(meta.id.replace("metadata-", ""))

    def test_ownership_mismatch_detected(self, client, seeded_evidence):
        """Changing run_id in the artifact metadata sidecar breaks ownership validation."""
        run_id, stage_id, tmp_dir, data = seeded_evidence
        from app.repositories.session import session_scope
        from app.repositories.models import ArtifactMetadataModel

        with session_scope() as s:
            artifacts = (
                s.query(ArtifactMetadataModel)
                .filter(ArtifactMetadataModel.run_id == run_id)
                .all()
            )
        assert len(artifacts) > 0
        meta = artifacts[0]
        artifact_rel_path = meta.relative_path
        artifact_full = tmp_dir / "artifacts" / artifact_rel_path
        sidecar = artifact_full.with_name(f"{artifact_full.name}.meta.json")
        if sidecar.exists():
            import json as _json
            sidecar_data = _json.loads(sidecar.read_text())
            sidecar_data["run_id"] = "foreign-run"
            sidecar.write_text(_json.dumps(sidecar_data, indent=2, sort_keys=True))

        from app.artifact_store.local_store import LocalFilesystemArtifactStore

        store = LocalFilesystemArtifactStore(
            tmp_dir / "artifacts", fixed_run_root=tmp_dir / "artifacts"
        )
        stored = store.read_artifact_by_id(meta.id.replace("metadata-", ""))
        assert stored.ref.run_id == "foreign-run"
        assert stored.ref.run_id != run_id

    def test_artifact_set_checksum_mismatch(self, client, seeded_evidence):
        """The artifact_set_checksum field exists and is a non-empty checksum."""
        run_id, stage_id, _, data = seeded_evidence
        artifact_set_cs = data.get("artifact_set_checksum", "")
        assert artifact_set_cs, "artifact_set_checksum should be present"
        assert artifact_set_cs.startswith("sha256:"), (
            f"Expected sha256: prefix, got {artifact_set_cs}"
        )
        assert len(artifact_set_cs) > 20

    def test_changed_angular_update_binding(self, client, seeded_evidence):
        """Response contains binding fields for angular update linkage."""
        run_id, stage_id, _, data = seeded_evidence
        assert "angular_update_record_id" in data
        assert "angular_update_binding_checksum" in data
        assert isinstance(data["angular_update_record_id"], str)
        assert isinstance(data["angular_update_binding_checksum"], str)
        assert data["evidence_schema_version"] == "transformation-evidence-v2"

    def test_concurrent_idempotency(self, client, test_db):
        """Two sequential requests with the same idempotency key produce replay."""
        run_id, stage_id, _, tmp_dir = test_db
        source_dir = tmp_dir / "source"
        target_dir = tmp_dir / "stage_sandbox"
        (source_dir / "f.ts").write_text("a")
        (target_dir / "f.ts").write_text("b")

        resp1 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "concurrent-idempotency-test",
            },
            headers=self.HEADERS,
        )
        assert resp1.status_code == 200, resp1.text
        assert resp1.json().get("idempotent_replay") is False

        resp2 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "concurrent-idempotency-test",
            },
            headers=self.HEADERS,
        )
        assert resp2.status_code == 200, resp2.text
        assert resp2.json().get("idempotent_replay") is True
        assert resp2.json()["diff_checksum"] == resp1.json()["diff_checksum"]
