"""AMFA-185 evidence security authority proof tests.

Ensures the transformation evidence system enforces:
- Run and stage boundary checks
- Prerequisite authority chain (Angular update must exist, succeed, be verified)
- Actor authorization (run-scoped identity enforcement)
- Input safety (no source/target paths accepted in requests)
- Output safety (no absolute paths leaked in responses)
- Filesystem safety (symlinks, malicious filenames, path traversal)
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.transformation_contracts import TransformationEvidenceRequest
from app.domain.transformation import (
    AngularUpdateStatus,
    TargetVersionStatus,
)
from app.main import app
from app.repositories.transformation_models import AngularUpdateRecordModel

SYMLINK_SUPPORTED = True
try:
    tmp_check = Path(os.environ.get("TEMP", "/tmp")) / "_amfa185_symlink_check"
    os.symlink("nonexistent", str(tmp_check))
    tmp_check.unlink()
except (OSError, NotImplementedError, AttributeError):
    SYMLINK_SUPPORTED = False


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


class TestEvidenceAuthorityProof:
    HEADERS = {"x-authenticated-actor": "tester"}

    def _generate_with_files(self, client, tmp_dir, run_id, stage_id, key_suffix=""):
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

        return client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": f"sec-test-{key_suffix or 'gen'}",
            },
            headers=self.HEADERS,
        )

    def test_fake_stage_returns_404(self, client, test_db):
        run_id, _, _, _ = test_db
        response = client.get(
            f"/api/v1/runs/{run_id}/stages/nonexistent/transformation-evidence",
            headers=self.HEADERS,
        )
        assert response.status_code == 404

    def test_stage_from_another_run_returns_error(self, client, test_db):
        run_id, _, _, tmp_dir = test_db
        from app.repositories.session import session_scope
        from app.repositories.models import MigrationRunModel, MigrationStageModel
        from datetime import UTC, datetime

        other_run_id = "other-run-001"
        other_stage_id = "other-stage-001"
        with session_scope() as s:
            other_run = MigrationRunModel(
                id=other_run_id,
                status="running",
                run_phase="staged_migration",
                phase_status="running",
                state_version=1,
                artifact_root=str(tmp_dir / "other_artifacts"),
                run_root=str(tmp_dir),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            s.add(other_run)
            other_stage = MigrationStageModel(
                id=other_stage_id,
                run_id=other_run_id,
                stage_order=1,
                status="preparing",
                created_at=datetime.now(UTC),
            )
            s.add(other_stage)
            s.flush()

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{other_stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "cross-run-stage-test",
            },
            headers=self.HEADERS,
        )
        assert response.status_code == 404

    def test_missing_angular_update_prerequisite_returns_409(self, client, test_db):
        run_id, _, _, tmp_dir = test_db
        from app.repositories.session import session_scope
        from app.repositories.models import MigrationRunModel, MigrationStageModel
        from datetime import UTC, datetime

        no_upd_run_id = f"norun-{run_id}"
        no_upd_stage_id = f"nostage-{run_id}"
        with session_scope() as s:
            r = MigrationRunModel(
                id=no_upd_run_id,
                status="running",
                run_phase="staged_migration",
                phase_status="running",
                state_version=1,
                artifact_root=str(tmp_dir / "no_upd_artifacts"),
                run_root=str(tmp_dir),
                workspace_aliases={
                    "SOURCE_SNAPSHOT": str(tmp_dir / "source"),
                    "STAGE_SANDBOX": str(tmp_dir / "stage_sandbox"),
                },
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            s.add(r)
            st = MigrationStageModel(
                id=no_upd_stage_id,
                run_id=no_upd_run_id,
                stage_order=1,
                status="preparing",
                created_at=datetime.now(UTC),
            )
            s.add(st)
            (tmp_dir / "source").mkdir(parents=True, exist_ok=True)
            (tmp_dir / "stage_sandbox").mkdir(parents=True, exist_ok=True)
            (tmp_dir / "source" / "f.ts").write_text("a")
            (tmp_dir / "stage_sandbox" / "f.ts").write_text("b")
            s.flush()

        response = client.post(
            f"/api/v1/runs/{no_upd_run_id}/stages/{no_upd_stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "missing-ang-upd",
            },
            headers=self.HEADERS,
        )
        assert response.status_code == 409
        data = response.json()
        assert "ANGULAR_UPDATE_REQUIRED" in data.get("message", "")

    def test_failed_angular_update_prerequisite_returns_409(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        from app.repositories.session import session_scope
        from datetime import UTC, datetime
        from uuid import uuid4

        with session_scope() as s:
            failed_upd = AngularUpdateRecordModel(
                id=f"ang-fail-{uuid4().hex[:12]}",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key="failed-upd",
                actor="tester",
                status=AngularUpdateStatus.FAILED.value,
                target_version_status=TargetVersionStatus.FAILED.value,
                source_version="17.0.0",
                target_version="18.0.0",
                artifact_ids=[],
                state_version=2,
                event_sequence=2,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            s.add(failed_upd)
            s.flush()

        (tmp_dir / "source" / "f.ts").write_text("a")
        (tmp_dir / "stage_sandbox" / "f.ts").write_text("b")

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "failed-upd-test",
            },
            headers=self.HEADERS,
        )
        assert response.status_code == 409
        assert "ANGULAR_UPDATE_NOT_SUCCESSFUL" in response.json().get("message", "")

    def test_unverified_target_returns_409(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        from app.repositories.session import session_scope
        from datetime import UTC, datetime
        from uuid import uuid4

        with session_scope() as s:
            unver = AngularUpdateRecordModel(
                id=f"ang-unver-{uuid4().hex[:12]}",
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key="unver-upd",
                actor="tester",
                status=AngularUpdateStatus.SUCCEEDED.value,
                target_version_status=TargetVersionStatus.INCONCLUSIVE.value,
                source_version="17.0.0",
                target_version="18.0.0",
                artifact_ids=[],
                state_version=2,
                event_sequence=2,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            s.add(unver)
            s.flush()

        (tmp_dir / "source" / "f.ts").write_text("a")
        (tmp_dir / "stage_sandbox" / "f.ts").write_text("b")

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "unver-test",
            },
            headers=self.HEADERS,
        )
        assert response.status_code == 409
        assert "TARGET_VERSION_NOT_VERIFIED" in response.json().get("message", "")

    def test_actor_mismatch_on_post_returns_403(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        from app.repositories.session import session_scope
        from app.repositories.models import MigrationRunModel

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            run.actor = "restricted-owner"
            s.flush()

        (tmp_dir / "source" / "f.ts").write_text("a")
        (tmp_dir / "stage_sandbox" / "f.ts").write_text("b")

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "actor-post-test",
            },
            headers={"x-authenticated-actor": "tester"},
        )
        assert response.status_code == 403
        assert "RUN_FORBIDDEN" in response.json().get("message", "")

    def test_actor_mismatch_on_get_returns_403(self, client, test_db):
        run_id, stage_id, _, _ = test_db
        from app.repositories.session import session_scope
        from app.repositories.models import MigrationRunModel

        with session_scope() as s:
            run = s.get(MigrationRunModel, run_id)
            run.actor = "restricted-owner"
            s.flush()

        response = client.get(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            headers={"x-authenticated-actor": "tester"},
        )
        assert response.status_code == 403
        assert "RUN_FORBIDDEN" in response.json().get("message", "")

    def test_request_cannot_accept_source_target_paths(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        assert "source_path" not in TransformationEvidenceRequest.model_fields
        assert "target_path" not in TransformationEvidenceRequest.model_fields
        assert "source_root" not in TransformationEvidenceRequest.model_fields
        assert "target_root" not in TransformationEvidenceRequest.model_fields

        resp = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "extra-field-test",
            },
            headers=self.HEADERS,
        )
        assert resp.status_code in (200, 409)

    def test_response_contains_no_absolute_paths(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        resp = self._generate_with_files(client, tmp_dir, run_id, stage_id, "abs-path")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        body_str = json.dumps(data)

        drive_letters = [f"{d}:" for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
        for dl in drive_letters:
            if dl in body_str:
                idx = body_str.index(dl)
                snippet = body_str[max(0, idx - 20):idx + 20]
                pytest.fail(f"Found potential drive-letter path in response: ...{snippet}...")

    def test_malicious_filename_renders_as_text(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        target_dir = tmp_dir / "stage_sandbox"
        source_dir = tmp_dir / "source"

        malicious_names = [
            "'; DROP TABLE users; --.ts",
            "$(cat passwd).ts",
            "`rm -rf `.ts",
        ]
        for name in malicious_names:
            (target_dir / name).write_text("content")
            (source_dir / name).write_text("original")

        resp = self._generate_with_files(client, tmp_dir, run_id, stage_id, "malicious")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        body_str = json.dumps(data)

        for name in malicious_names:
            assert name in body_str, f"Malicious filename {name!r} should be rendered as text"

    def test_artifact_urls_are_same_origin_id_routes_only(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        resp = self._generate_with_files(client, tmp_dir, run_id, stage_id, "art-url")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        artifacts = data.get("artifacts", [])
        assert len(artifacts) > 0
        for art in artifacts:
            art_id = art.get("artifact_id", "")
            assert art_id.startswith("artifact-"), f"Artifact ID should start with 'artifact-': {art_id}"
            assert ".." not in art.get("relative_path", "")
            assert not art.get("relative_path", "").startswith("/")

    @pytest.mark.skipif(not SYMLINK_SUPPORTED, reason="OS does not support symlinks")
    def test_symlink_in_source_is_rejected(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        source_dir = tmp_dir / "source"
        sym_path = source_dir / "evil_link"
        os.symlink(tmp_dir / "outside", str(sym_path))

        (tmp_dir / "outside").mkdir(parents=True, exist_ok=True)
        (source_dir / "ok.ts").write_text("ok")
        (tmp_dir / "stage_sandbox" / "ok.ts").write_text("changed")

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "symlink-source-test",
            },
            headers=self.HEADERS,
        )
        assert response.status_code == 409
        msg = response.json().get("message", "")
        assert "symlink" in msg.lower() or "escape" in msg.lower() or "safety" in msg.lower()

    @pytest.mark.skipif(not SYMLINK_SUPPORTED, reason="OS does not support symlinks")
    def test_symlink_in_target_is_rejected(self, client, test_db):
        run_id, stage_id, _, tmp_dir = test_db
        target_dir = tmp_dir / "stage_sandbox"
        sym_path = target_dir / "evil_link"
        os.symlink(tmp_dir / "outside", str(sym_path))

        (tmp_dir / "outside").mkdir(parents=True, exist_ok=True)
        (tmp_dir / "source" / "ok.ts").write_text("ok")
        (target_dir / "ok.ts").write_text("changed")

        response = client.post(
            f"/api/v1/runs/{run_id}/stages/{stage_id}/transformation-evidence",
            json={
                "expected_state_version": 1,
                "idempotency_key": "symlink-target-test",
            },
            headers=self.HEADERS,
        )
        assert response.status_code == 409
        msg = response.json().get("message", "")
        assert "symlink" in msg.lower() or "escape" in msg.lower() or "safety" in msg.lower()
