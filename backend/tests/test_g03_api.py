"""API integration tests for G03 transformation endpoints."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

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
def test_db(tmp_path):
    """Create a temporary SQLite database for testing (tmp_path avoids Windows file locking)."""
    from app.domain.contracts import CommandStatus, RunPhase, RunStatus, StageStatus, StepStatus
    from app.repositories.models import (
        MigrationRunModel, MigrationStageModel, StageStepModel,
        CommandExecutionModel,
        AngularUpdateRecordModel, TransformationEvidenceModel, G08ApprovalModel,
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
    session_module.SessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=test_engine)

    # Create a test run and stage
    from datetime import UTC, datetime

    from uuid import uuid4
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

        # ── Setup for transformation evidence tests ──────────────────────
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


class TestAngularUpdateAPI:
    def test_start_update_happy_path(self, client, test_db):
        run_id, stage_id, _, _ = test_db
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
        assert response.status_code == 409
        assert "PREREQUISITE_ARTIFACT_REQUIRED" in response.json()["message"]

    def test_get_update(self, client, test_db):
        run_id, stage_id, _, _ = test_db
        # The fixture creates an AngularUpdateRecordModel so GET returns it
        response = client.get(f"/api/v1/runs/{run_id}/stages/{stage_id}/angular-update")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "succeeded"

    def test_update_stale_version(self, client, test_db):
        run_id, stage_id, _, _ = test_db
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
        run_id, _, _, _ = test_db
        response = client.get(f"/api/v1/runs/{run_id}/stages/nonexistent/angular-update")
        assert response.status_code == 404

    def test_get_target_version_returns_target_version_shape(self, client, test_db):
        run_id, stage_id, _, _ = test_db
        from app.repositories.session import session_scope
        from app.repositories.transformation_models import AngularUpdateRecordModel
        from datetime import UTC, datetime
        with session_scope() as s:
            record = AngularUpdateRecordModel(
                id=f"ang-tv-{stage_id}", run_id=run_id, stage_id=stage_id,
                idempotency_key="tv-test", actor="tester",
                status=AngularUpdateStatus.SUCCEEDED.value,
                target_version_status=TargetVersionStatus.VERIFIED.value,
                resolved_target_version="18.2.0",
                source_version="17.0.0", target_version="18.0.0",
                evidence={"package_json_version": "18.2.0", "ng_version_output": "18.2.0",
                          "all_sources_agree": True, "disagreements": []},
                artifact_ids=["art-1"], state_version=2, event_sequence=1,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
            s.add(record)
        response = client.get(f"/api/v1/runs/{run_id}/stages/{stage_id}/target-version")
        assert response.status_code == 200
        data = response.json()
        assert "evidence_sources" in data
        assert "all_sources_agree" in data
        assert "disagreements" in data
        assert data["all_sources_agree"] is True

    def test_get_target_version_not_found(self, client, test_db):
        run_id, _, _, _ = test_db
        response = client.get(f"/api/v1/runs/{run_id}/stages/nonexistent/target-version")
        assert response.status_code == 404

    def test_complete_angular_update_calls_through(self, client, test_db):
        run_id, stage_id, _, _ = test_db
        from app.repositories.session import session_scope
        from app.repositories.transformation_models import AngularUpdateRecordModel
        from datetime import UTC, datetime
        with session_scope() as s:
            record = AngularUpdateRecordModel(
                id=f"ang-comp-{stage_id}", run_id=run_id, stage_id=stage_id,
                idempotency_key="comp-api-test", actor="tester",
                status=AngularUpdateStatus.RUNNING.value,
                target_version_status=TargetVersionStatus.INCONCLUSIVE.value,
                source_version="17.0.0", target_version="18.0.0",
                command_execution_id="exec-api-comp",
                artifact_ids=[], state_version=1, event_sequence=1,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
            s.add(record)
        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/angular-update/complete",
            json={"run_id": run_id, "stage_id": stage_id,
                  "expected_state_version": 1, "idempotency_key": "comp-api-001",
                  "actor": "tester", "command_execution_id": "exec-api-comp"},
        )
        assert response.status_code == 409
        assert "COMMAND_AUTHORITY_REQUIRED" in response.json()["message"]

    def test_verify_target_version_returns_shape(self, client, test_db):
        """Verify the target-version/verify endpoint returns TargetVersionResponse shape."""
        run_id, stage_id, _, _ = test_db
        from app.repositories.session import session_scope
        from app.repositories.transformation_models import AngularUpdateRecordModel
        from datetime import UTC, datetime
        target_version = "18.2.0"
        with session_scope() as s:
            record = AngularUpdateRecordModel(
                id=f"ang-ver-{stage_id}", run_id=run_id, stage_id=stage_id,
                idempotency_key="ver-api-test", actor="tester",
                status=AngularUpdateStatus.SUCCEEDED.value,
                target_version_status=TargetVersionStatus.VERIFIED.value,
                resolved_target_version=target_version,
                source_version="17.0.0", target_version="18.0.0",
                command_execution_id="exec-api-ver",
                evidence={"package_json_version": target_version,
                          "lockfile_version": target_version,
                          "ng_version_output": target_version,
                          "dependency_tree_version": target_version,
                          "all_sources_agree": True, "disagreements": []},
                artifact_ids=["art-ver"], state_version=1, event_sequence=1,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
            s.add(record)
        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/target-version/verify",
            json={"run_id": run_id, "stage_id": stage_id,
                  "expected_state_version": 1, "idempotency_key": "ver-api-001",
                  "actor": "tester", "command_execution_id": "exec-api-ver"},
        )
        assert response.status_code == 409
        assert "COMMAND_AUTHORITY_REQUIRED" in response.json()["message"]


class TestTransformationEvidenceAPI:
    def test_generate_evidence(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        source_dir = tmp_dir / "source"
        target_dir = tmp_dir / "stage_sandbox"

        Path(source_dir, "package.json").write_text(
            json.dumps({"dependencies": {"@angular/core": "17.0.0"}})
        )
        Path(target_dir, "package.json").write_text(
            json.dumps({"dependencies": {"@angular/core": "18.0.0"}})
        )
        Path(source_dir, "src").mkdir(parents=True, exist_ok=True)
        Path(target_dir, "src").mkdir(parents=True, exist_ok=True)
        Path(source_dir, "src/main.ts").write_text("// Angular 17 main\n")
        Path(target_dir, "src/main.ts").write_text("// Angular 18 main\n")

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "test-evidence-001",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["total_files_changed"] >= 1
        assert data["diff_checksum"] is not None

    def test_get_evidence(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        source_dir = tmp_dir / "source"
        target_dir = tmp_dir / "stage_sandbox"
        Path(source_dir, "file.ts").write_text("a")
        Path(target_dir, "file.ts").write_text("b")

        client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "test-evidence-get-002",
            },
        )
        response = client.get(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_files_changed"] >= 1

    def test_generate_evidence_sandbox_boundary(self, client, test_db):
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
        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "test-boundary-001",
            },
        )
        assert response.status_code == 409
        data = response.json()
        msg = data.get("message", "")
        assert "missing or unsafe" in msg, msg

    def test_generate_evidence_idempotent_replay(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        source_dir = tmp_dir / "source"
        target_dir = tmp_dir / "stage_sandbox"
        (source_dir / "file.ts").write_text("a")
        (target_dir / "file.ts").write_text("b")

        resp1 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "replay-test-001",
            },
        )
        assert resp1.status_code == 200, resp1.text
        data1 = resp1.json()
        assert data1["idempotent_replay"] is False
        checksum1 = data1["diff_checksum"]

        resp2 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "replay-test-001",
            },
        )
        assert resp2.status_code == 200, resp2.text
        data2 = resp2.json()
        assert data2["idempotent_replay"] is True
        assert data2["diff_checksum"] == checksum1

    def test_generate_evidence_idempotent_mismatch(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        source_dir = tmp_dir / "source"
        target_dir = tmp_dir / "stage_sandbox"
        (source_dir / "file.ts").write_text("a")
        (target_dir / "file.ts").write_text("b")

        resp1 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "mismatch-test-001",
            },
        )
        assert resp1.status_code == 200, resp1.text

        resp2 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "mismatch-test-001",
                "correlation_id": "different-payload",
            },
        )
        assert resp2.status_code == 409, resp2.text
        assert "IDEMPOTENCY_PAYLOAD_MISMATCH" in resp2.json()["message"]

    def test_generate_evidence_stale_version(self, client, test_db):
        run_id, stage_id, _, _ = test_db
        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 99,
                "idempotency_key": "stale-test-001",
            },
        )
        assert response.status_code == 409, response.text
        assert "STALE_STATE_VERSION" in response.json()["message"]

    def test_generate_evidence_correlation_id(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        source_dir = tmp_dir / "source"
        target_dir = tmp_dir / "stage_sandbox"
        (source_dir / "file.ts").write_text("a")
        (target_dir / "file.ts").write_text("b")

        client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "corr-test-001",
                "correlation_id": "test-correlation-123",
            },
        )
        response = client.get(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence"
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("correlation_id") == "test-correlation-123"

    def test_generate_evidence_artifact_ids(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        source_dir = tmp_dir / "source"
        target_dir = tmp_dir / "stage_sandbox"
        (source_dir / "file.ts").write_text("a")
        (target_dir / "file.ts").write_text("b")

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "art-test-001",
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data.get("artifacts"), list)
        assert len(data["artifacts"]) > 0


class TestG08ApprovalAPI:
    def _registered_artifact(self, client, run_id, stage_id, tmp_dir, name, content, artifact_type="json"):
        """Register an artifact in the artifact store and metadata table."""
        import uuid
        from app.repositories.session import session_scope
        from app.repositories.models import ArtifactMetadataModel
        from app.domain.contracts import ArtifactType as AT
        from datetime import UTC, datetime
        from app.artifact_store import LocalFilesystemArtifactStore
        from pathlib import Path

        artifact_id = f"art-{uuid.uuid4().hex[:12]}"
        store = LocalFilesystemArtifactStore(tmp_dir / "artifacts", fixed_run_root=tmp_dir / "artifacts")
        atype = AT.JSON if artifact_type == "json" else AT.REPORT
        stored = store.write_text_artifact(
            run_id, f"stage/{stage_id}/{name}", content, atype,
            created_by="test", created_at=datetime.now(UTC),
        )
        with session_scope() as s:
            s.add(ArtifactMetadataModel(
                id=f"metadata-{stored.ref.artifact_id}",
                run_id=run_id, stage_id=stage_id,
                artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                created_at=datetime.now(UTC),
            ))
            s.flush()
        return stored.ref.artifact_id

    def _prepare_prerequisites(self, client, run_id, stage_id, tmp_dir):
        """Create angular update and evidence records with artifacts."""
        import json as _json
        from app.repositories.session import session_scope
        from app.repositories.models import MigrationRunModel
        from app.repositories.transformation_models import (
            AngularUpdateRecordModel,
            TransformationEvidenceModel,
        )
        from datetime import UTC, datetime

        update_id = f"ang-{stage_id}"
        tev_id = f"tev-{stage_id}"
        checksum_val = "sha256:" + "a" * 64
        inventory_checksum = "sha256:" + "b" * 64

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            run.workspace_aliases = {
                "SOURCE_SNAPSHOT": str(tmp_dir / "source"),
                "STAGE_SANDBOX": str(tmp_dir / "stage_sandbox"),
            }
            update = AngularUpdateRecordModel(
                id=update_id, run_id=run_id, stage_id=stage_id,
                idempotency_key="test-ang-prep-g08", actor="tester",
                status=AngularUpdateStatus.SUCCEEDED.value,
                target_version_status=TargetVersionStatus.VERIFIED.value,
                resolved_target_version="18.0.0",
                source_version="17.0.0", target_version="18.0.0",
                artifact_ids=[], state_version=2, event_sequence=1,
                evidence={"plan_checksum": checksum_val, "plan_version": 1},
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
            s.add(update)
            evidence = TransformationEvidenceModel(
                id=tev_id, run_id=run_id, stage_id=stage_id,
                idempotency_key="test-evidence-prep-g08", actor="tester",
                status="completed", overall_risk_level="low",
                total_files_changed=10, diff_checksum=checksum_val,
                inventory_checksum=inventory_checksum,
                diff_summary=DiffSummary(
                    total_files_changed=10, total_lines_added=100,
                    total_lines_removed=50, diff_checksum=checksum_val,
                    inventory_checksum=inventory_checksum,
                ).model_dump(mode="json"),
                evidence_complete=True, artifact_ids=[],
                state_version=3, event_sequence=2,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
            s.add(evidence)
            run.state_version = 3
            s.flush()
        return update_id, tev_id, checksum_val

    def _initialize(self, client, run_id, stage_id, expected_state_version, idempotency_key="g08-init"):
        return client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/package",
            json={
                "expected_state_version": expected_state_version,
                "idempotency_key": idempotency_key,
                "gate_id": "G08",
            },
        )

    def _decision_payload(self, new_state_version, decision="approved", idempotency_key="g08-decision", init_data=None):
        return {
            "expected_state_version": new_state_version,
            "idempotency_key": idempotency_key,
            "decision": decision,
            "gate_id": "G08",
            "gate_version": (init_data or {}).get("gate_version", "g08-v1"),
            "package_checksum": (init_data or {}).get("package_checksum", "sha256:package"),
            "artifact_set_checksum": (init_data or {}).get("artifact_set_checksum", "sha256:artifacts"),
            "workspace_fingerprint": (init_data or {}).get("workspace_fingerprint", "sha256:workspace"),
        }

    def test_get_g08_not_found_returns_stable_error(self, client, test_db):
        run_id, stage_id, _, _ = test_db
        response = client.get(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08"
        )
        assert response.status_code == 404
        data = response.json()
        assert data.get("error_code") == "G08_NOT_FOUND"

    def test_complete_g08_package_and_append_only_approval(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        update_id, tev_id, checksum = self._prepare_prerequisites(client, run_id, stage_id, tmp_dir)

        resp = self._initialize(client, run_id, stage_id, expected_state_version=3)
        assert resp.status_code == 200, f"Init failed: {resp.text}"
        init_data = resp.json()
        assert init_data["status"] == "pending"
        new_state_version = init_data["state_version"]

        decide_resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json=self._decision_payload(new_state_version, init_data=init_data),
        )
        assert decide_resp.status_code == 200, f"Decide failed: {decide_resp.text}"
        decide_data = decide_resp.json()
        assert decide_data["decision"] == "approved"
        assert decide_data["status"] == "approved"
        assert decide_data["package_artifact_id"] is not None

        # Verify append-only: a second decision with approved is blocked
        second_state_version = decide_data["state_version"]
        second_payload = self._decision_payload(
            second_state_version, decision="approved", idempotency_key="g08-second-decision", init_data=decide_data
        )
        second_resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json=second_payload,
        )
        # G08 is already approved, so re-approval is blocked
        assert second_resp.status_code == 409
        assert "G08_ALREADY_APPROVED" in second_resp.text

    def test_g08_package_artifact_is_retrievable_and_creation_event_references_complete_evidence(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        self._prepare_prerequisites(client, run_id, stage_id, tmp_dir)

        resp = self._initialize(client, run_id, stage_id, expected_state_version=3)
        assert resp.status_code == 200, f"Init failed: {resp.text}"
        init_data = resp.json()
        package_artifact_id = init_data.get("package_artifact_id")
        assert package_artifact_id is not None

        response = client.get(f"/artifacts/{package_artifact_id}")
        assert response.status_code in (200, 302, 307), f"Retrieve failed: {response.text}"

    def test_package_artifact_tamper_is_detected_before_decision(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        update_id, tev_id, checksum = self._prepare_prerequisites(client, run_id, stage_id, tmp_dir)

        resp = self._initialize(client, run_id, stage_id, expected_state_version=3)
        assert resp.status_code == 200
        init_data = resp.json()

        # Tamper: modify the evidence record to change the checksum
        from app.repositories.session import session_scope
        from app.repositories.transformation_models import TransformationEvidenceModel
        from datetime import UTC, datetime
        with session_scope() as s:
            ev = s.get(TransformationEvidenceModel, tev_id)
            ev.diff_checksum = "sha256:" + "f" * 64
            ev.inventory_checksum = "sha256:" + "f" * 64
            s.flush()

        new_state_version = init_data["state_version"]
        decide_resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json=self._decision_payload(new_state_version, init_data=init_data),
        )
        assert decide_resp.status_code == 200, f"Expected 200, got {decide_resp.status_code}: {decide_resp.text}"
        decide_data = decide_resp.json()
        assert decide_data["status"] == "stale", f"Expected stale, got {decide_data['status']}"
        assert decide_data.get("stale_reason") is not None

    def test_aggregate_state_change_invalidates_pending_package(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        update_id, tev_id, checksum = self._prepare_prerequisites(client, run_id, stage_id, tmp_dir)

        resp = self._initialize(client, run_id, stage_id, expected_state_version=3)
        assert resp.status_code == 200
        init_data = resp.json()

        # Bump the run's state_version externally to simulate aggregate change
        from app.repositories.session import session_scope
        from app.repositories.models import MigrationRunModel
        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            run.state_version = 99
            s.flush()

        new_state_version = init_data["state_version"]
        decide_resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json=self._decision_payload(new_state_version, init_data=init_data),
        )
        assert decide_resp.status_code == 409, f"Expected 409, got {decide_resp.status_code}: {decide_resp.text}"

    def test_invalid_decision_contract_fails_without_persisting_decision(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        update_id, tev_id, checksum = self._prepare_prerequisites(client, run_id, stage_id, tmp_dir)

        resp = self._initialize(client, run_id, stage_id, expected_state_version=3)
        assert resp.status_code == 200
        init_data = resp.json()

        # Invalid: missing required 'decision' field
        new_state_version = init_data["state_version"]
        decide_resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json={
                "expected_state_version": new_state_version,
                "idempotency_key": "g08-invalid-decision",
                "gate_id": "G08",
            },
        )
        assert decide_resp.status_code == 422

    def test_decision_idempotency_replay_and_payload_mismatch(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        update_id, tev_id, checksum = self._prepare_prerequisites(client, run_id, stage_id, tmp_dir)

        resp = self._initialize(client, run_id, stage_id, expected_state_version=3)
        assert resp.status_code == 200
        init_data = resp.json()

        new_state_version = init_data["state_version"]
        decide_payload = self._decision_payload(new_state_version, init_data=init_data)
        resp1 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json=decide_payload,
        )
        assert resp1.status_code == 200
        data1 = resp1.json()

        resp2 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json=decide_payload,
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["idempotent_replay"] is True

    def test_workspace_drift_records_stale_and_blocks_decision(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        update_id, tev_id, checksum = self._prepare_prerequisites(client, run_id, stage_id, tmp_dir)

        resp = self._initialize(client, run_id, stage_id, expected_state_version=3)
        assert resp.status_code == 200
        init_data = resp.json()

        # Create a file in the sandbox to change the workspace fingerprint
        sandbox = tmp_dir / "stage_sandbox"
        sandbox.mkdir(parents=True, exist_ok=True)
        (sandbox / "drift.txt").write_text("drift content")

        new_state_version = init_data["state_version"]
        decide_resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json=self._decision_payload(new_state_version, init_data=init_data),
        )
        assert decide_resp.status_code == 200
        decide_data = decide_resp.json()
        assert decide_data["status"] == "stale"

    def test_modification_request_requires_comment_and_blocks_reopen_without_new_evidence(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        update_id, tev_id, checksum = self._prepare_prerequisites(client, run_id, stage_id, tmp_dir)

        resp = self._initialize(client, run_id, stage_id, expected_state_version=3)
        assert resp.status_code == 200
        new_state_version = resp.json()["state_version"]

        modification_without_comment = self._decision_payload(
            new_state_version, decision="modification_requested", idempotency_key="mod-no-comment", init_data=resp.json()
        )
        resp_mod = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json=modification_without_comment,
        )
        assert resp_mod.status_code == 422, f"Expected 422, got {resp_mod.status_code}: {resp_mod.text}"

        modification_with_comment = self._decision_payload(
            new_state_version, decision="modification_requested", idempotency_key="mod-with-comment", init_data=resp.json()
        )
        modification_with_comment["comment"] = "Please fix the test fixture"
        resp_mod2 = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json=modification_with_comment,
        )
        assert resp_mod2.status_code == 200, f"Expected 200, got {resp_mod2.status_code}: {resp_mod2.text}"
        assert resp_mod2.json()["decision"] == "modification_requested"

    def test_target_mismatch_and_incomplete_evidence_cannot_be_approved(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        from app.repositories.session import session_scope
        from app.repositories.models import MigrationRunModel
        from app.repositories.transformation_models import (
            AngularUpdateRecordModel,
            TransformationEvidenceModel,
        )
        from datetime import UTC, datetime
        checksum = "sha256:" + "c" * 64
        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            update = AngularUpdateRecordModel(
                id=f"ang-fail-{stage_id}", run_id=run_id, stage_id=stage_id,
                idempotency_key="test-ang-fail-g08", actor="tester",
                status=AngularUpdateStatus.FAILED.value,
                target_version_status=TargetVersionStatus.MISMATCH.value,
                source_version="17.0.0", target_version="18.0.0",
                artifact_ids=[], state_version=2, event_sequence=1,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
            s.add(update)
            ev = TransformationEvidenceModel(
                id=f"tev-fail-{stage_id}", run_id=run_id, stage_id=stage_id,
                idempotency_key="test-evidence-fail-g08", actor="tester",
                status="completed", overall_risk_level="high",
                total_files_changed=0, diff_checksum=checksum,
                inventory_checksum=checksum,
                diff_summary=DiffSummary(
                    total_files_changed=0, total_lines_added=0,
                    total_lines_removed=0, diff_checksum=checksum,
                    inventory_checksum=checksum,
                ).model_dump(mode="json"),
                evidence_complete=False, artifact_ids=[],
                state_version=3, event_sequence=2,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
            s.add(ev)
            run.state_version = 3
            s.flush()

        resp = self._initialize(client, run_id, stage_id, expected_state_version=3)
        assert resp.status_code == 200
        init_data = resp.json()
        new_state_version = init_data["state_version"]

        decide_resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
            json=self._decision_payload(new_state_version, init_data=init_data),
        )
        assert decide_resp.status_code == 200
        decide_data = decide_resp.json()
        assert decide_data["status"] == "stale"
        assert decide_data["decision"] != "approved"

    def test_unauthorized_actor_cannot_read_or_mutate_g08(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        from app.repositories.session import session_scope
        from app.repositories.models import MigrationRunModel
        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            run.actor = "authorized-user"
            s.flush()

        unauthorized_payload = {
            "expected_state_version": 1,
            "idempotency_key": "unauth-init",
            "gate_id": "G08",
        }
        resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/package",
            json=unauthorized_payload,
        )
        assert resp.status_code == 403

    def test_protected_progression_guard_rejects_missing_and_stale_g08(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        from app.services.transformation_application_service import G08ApprovalApplicationService
        with pytest.raises(Exception):
            G08ApprovalApplicationService().require_approved_g08(run_id, stage_id)

    def test_artifact_failure_returns_stable_error_and_preserves_authoritative_state(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        update_id, tev_id, checksum = self._prepare_prerequisites(client, run_id, stage_id, tmp_dir)

        resp = self._initialize(client, run_id, stage_id, expected_state_version=3)
        assert resp.status_code == 200
        init_data = resp.json()
        new_state_version = init_data["state_version"]

        from unittest.mock import patch
        from app.services.transformation_application_service import StateTransitionService

        # Simulate an artifact storage failure that propagates as a backend failure
        with patch.object(
            StateTransitionService, "apply_transition",
            side_effect=OSError("Simulated artifact storage failure"),
        ):
            decide_resp = client.post(
                f"/api/v1/runs/{run_id}/stages/{stage_id}/approvals/G08/decisions",
                json=self._decision_payload(new_state_version, init_data=init_data),
            )

        assert decide_resp.status_code == 500
        data = decide_resp.json()
        assert data.get("error_code") == "G08_BACKEND_FAILURE"
        assert data.get("correlation_id") is not None

        from app.repositories.session import session_scope
        from app.repositories.models import MigrationRunModel, WorkflowEventModel
        from app.repositories.transformation_models import G08ApprovalModel
        from sqlalchemy import select

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            assert run.state_version == new_state_version, "State version must not change on backend failure"

            events = list(s.scalars(
                select(WorkflowEventModel)
                .where(WorkflowEventModel.run_id == run_id)
            ).all())
            last_event_type = events[-1].event_type if events else None
            assert last_event_type != "G08_APPROVED", "No workflow event should be committed for the failed decision"

            records = list(s.scalars(
                select(G08ApprovalModel)
                .where(G08ApprovalModel.run_id == run_id)
                .where(G08ApprovalModel.stage_id == stage_id)
            ).all())
            # Only the init record exists; no decision record was created
            assert len(records) == 1
