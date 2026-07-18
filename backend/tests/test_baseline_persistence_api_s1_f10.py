import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.baseline_contracts import BaselinePrequalifyRequest, BaselineWorkspaceRequest
from app.main import app  # noqa: F401 - verifies the application imports the new router
from app.repositories.models import Base, MigrationRunModel, WorkflowEventModel
from app.repositories.baseline_models import BaselineQualificationModel
from app.services.baseline_application_service import BaselineApplicationService


def _fixture(tmp_path: Path):
    source_snapshot = tmp_path / "source-snapshot"
    source_snapshot.mkdir()
    (source_snapshot / "package.json").write_text(json.dumps({"name": "fixture", "dependencies": {}}), encoding="utf-8")
    (source_snapshot / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {"": {}}}), encoding="utf-8")
    fingerprint = "sha256:approved-snapshot"
    (source_snapshot / "snapshot-fingerprint.json").write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf-8")
    output = tmp_path / "output"
    run_root = output / ".migration-factory" / "runs" / "run-1"
    artifact_root = run_root / "artifacts"
    baseline_path = run_root / "baseline-sandbox"
    now = datetime.now(UTC)
    engine = create_engine(f"sqlite:///{tmp_path / 'baseline.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-1", status="CREATED", run_phase="BASELINE", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, artifact_root=str(artifact_root), workspace_aliases={"SOURCE_SNAPSHOT": str(source_snapshot), "BASELINE_SANDBOX": str(baseline_path)}, created_at=now, updated_at=now))
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
        assert len(record.artifact_ids) == 6
        assert [event.event_type for event in events] == ["BASELINE_WORKSPACE_STARTED", "BASELINE_WORKSPACE_READY", "LOCKFILE_PREQUALIFICATION_COMPLETED"]
    assert len(list((tmp_path / "output").rglob("*.json"))) >= 6
    engine.dispose()
