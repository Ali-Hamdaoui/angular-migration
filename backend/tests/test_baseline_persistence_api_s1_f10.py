import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.baseline_contracts import BaselinePrequalifyRequest, BaselineWorkspaceRequest
from app.main import app  # noqa: F401 - verifies the application imports the new router
from app.repositories.models import Base, MigrationRunModel, SourceSnapshotModel, WorkflowEventModel
from app.repositories.baseline_models import BaselineQualificationModel
from app.services.baseline_application_service import BaselineApplicationError, BaselineApplicationService


def _fixture(tmp_path: Path):
    output = tmp_path / "output"
    run_root = output / ".migration-factory" / "runs" / "run-1"
    run_root.mkdir(parents=True)
    source_snapshot = run_root / "source-snapshot"
    source_snapshot.mkdir()
    physical_snapshot = source_snapshot / "snapshot-1"
    physical_snapshot.mkdir()
    (physical_snapshot / "package.json").write_text(json.dumps({"name": "fixture", "dependencies": {}}), encoding="utf-8")
    (physical_snapshot / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {"": {}}}), encoding="utf-8")
    fingerprint = "sha256:approved-snapshot"
    (physical_snapshot / "snapshot-fingerprint.json").write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf-8")
    artifact_root = run_root / "artifacts"
    baseline_path = run_root / "baseline-sandbox"
    now = datetime.now(UTC)
    engine = create_engine(f"sqlite:///{tmp_path / 'baseline.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-1", run_root=str(run_root), status="CREATED", run_phase="BASELINE", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, artifact_root=str(artifact_root), workspace_aliases={"SOURCE_SNAPSHOT": str(source_snapshot), "BASELINE_SANDBOX": str(baseline_path)}, created_at=now, updated_at=now))
        session.add(SourceSnapshotModel(id="snapshot-1", run_id="run-1", idempotency_key="snapshot-1", actor="operator", status="created", source_path=str(tmp_path / "source"), snapshot_path=str(physical_snapshot), policy_version="source-snapshot-policy-v1", exclusions=[], git_metadata={}, artifact_ids=[], state_version=1, event_sequence=1, created_at=now, updated_at=now))
        session.commit()

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    service = BaselineApplicationService(
        session_scope_factory=scope,
        g02_service=SimpleNamespace(authorize_baseline=lambda run_id: SimpleNamespace(snapshot_id="snapshot-1", snapshot_fingerprint=fingerprint)),
        execution_profile_service=SimpleNamespace(validate_for_baseline=lambda *args, **kwargs: SimpleNamespace()),
    )
    return service, sessions, engine


def test_baseline_uses_physical_nested_snapshot_and_fingerprint(tmp_path: Path):
    service, sessions, engine = _fixture(tmp_path)
    result = service.create_workspace("run-1", BaselineWorkspaceRequest(expected_state_version=1, idempotency_key="workspace-1", actor="operator"))
    assert result.input_fingerprint == "sha256:approved-snapshot"
    assert (tmp_path / "output/.migration-factory/runs/run-1/baseline-sandbox/package.json").is_file()
    engine.dispose()


def test_baseline_rejects_snapshot_from_another_run(tmp_path: Path):
    service, sessions, engine = _fixture(tmp_path)
    with sessions() as session:
        snapshot = session.get(SourceSnapshotModel, "snapshot-1")
        snapshot.run_id = "run-2"
        session.commit()
    with pytest.raises(BaselineApplicationError, match="does not belong"):
        service.create_workspace("run-1", BaselineWorkspaceRequest(expected_state_version=1, idempotency_key="workspace-1", actor="operator"))
    engine.dispose()


def test_baseline_rejects_snapshot_outside_registered_container(tmp_path: Path):
    service, sessions, engine = _fixture(tmp_path)
    outside = tmp_path / "outside-snapshot"
    outside.mkdir()
    (outside / "snapshot-fingerprint.json").write_text(json.dumps({"fingerprint": "sha256:approved-snapshot"}), encoding="utf-8")
    with sessions() as session:
        snapshot = session.get(SourceSnapshotModel, "snapshot-1")
        snapshot.snapshot_path = str(outside)
        session.commit()
    with pytest.raises(BaselineApplicationError, match="workspace boundaries"):
        service.create_workspace("run-1", BaselineWorkspaceRequest(expected_state_version=1, idempotency_key="workspace-1", actor="operator"))
    engine.dispose()


def test_baseline_rejects_snapshot_fingerprint_mismatch(tmp_path: Path):
    service, sessions, engine = _fixture(tmp_path)
    with sessions() as session:
        snapshot = session.get(SourceSnapshotModel, "snapshot-1")
        Path(snapshot.snapshot_path, "snapshot-fingerprint.json").write_text(json.dumps({"fingerprint": "sha256:wrong"}), encoding="utf-8")
        session.commit()
    with pytest.raises(BaselineApplicationError, match="does not match"):
        service.create_workspace("run-1", BaselineWorkspaceRequest(expected_state_version=1, idempotency_key="workspace-1", actor="operator"))
    engine.dispose()


def test_workspace_and_prequalification_persist_artifacts_events_and_replay(tmp_path: Path):
    service, sessions, engine = _fixture(tmp_path)
    workspace = service.create_workspace("run-1", BaselineWorkspaceRequest(expected_state_version=1, idempotency_key="workspace-1", actor="operator"))
    result = service.prequalify("run-1", BaselinePrequalifyRequest(expected_state_version=workspace.state_version, idempotency_key="prequalify-1", actor="operator"))
    replay = service.prequalify("run-1", BaselinePrequalifyRequest(expected_state_version=workspace.state_version, idempotency_key="prequalify-1", actor="operator"))

    assert workspace.status == "workspace_ready"
    assert result.status == "blocked"
    assert "EXECUTION_PROFILE_REQUIRED" in result.blockers
    assert replay.idempotent_replay is True
    with sessions() as session:
        record = session.scalar(select(BaselineQualificationModel).where(BaselineQualificationModel.run_id == "run-1"))
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == "run-1").order_by(WorkflowEventModel.sequence)))
        assert record is not None
        assert len(record.artifact_ids) == 7
        assert [event.event_type for event in events] == ["BASELINE_WORKSPACE_STARTED", "BASELINE_WORKSPACE_READY", "LOCKFILE_PREQUALIFICATION_COMPLETED"]
    assert len(list((tmp_path / "output").rglob("*.json"))) >= 6
    engine.dispose()
