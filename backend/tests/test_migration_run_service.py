from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.preflight import PreflightSnapshot
from app.repositories.models import ArtifactMetadataModel, Base, MigrationRunModel, WorkflowEventModel
from app.repositories.preflight_models import ApprovalGateModel, PreflightModel
from app.services.migration_run_service import CreateRunRequest, MigrationRunError, MigrationRunService
from app.core.config import Settings


class RecordingGraph:
    def __init__(self):
        self.calls = []

    def start(self, *, run_id: str, thread_id: str) -> None:
        self.calls.append((run_id, thread_id))


class FailingGraph:
    def start(self, *, run_id: str, thread_id: str) -> None:
        raise RuntimeError("test handoff failure")


def _service(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'runs.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    now = datetime.now(UTC)
    snapshot = PreflightSnapshot(
        preflight_id="preflight-1", gate_id="G01", gate_version="g01-v1", state_version=1,
        status="passed", created_at=now, expires_at=now + timedelta(minutes=5),
        input_checksum="sha256:input", artifact_set_checksum="sha256:artifacts",
        target_angular_family="21.x", migration_mode="strict-functional-parity",
        source_path="C:/source", target_output_path="C:/target",
    )
    with scope() as session:
        session.add(PreflightModel(id="preflight-1", idempotency_key="pf-1", actor="reviewer", gate_id="G01", gate_version="g01-v1", state_version=1, status="passed", input_checksum="sha256:input", artifact_set_checksum="sha256:artifacts", expires_at=snapshot.expires_at, binding={}, snapshot=snapshot.model_dump(mode="json"), created_at=now))
        session.add(ApprovalGateModel(id="gate-1", preflight_id="preflight-1", gate_id="G01", gate_version="g01-v1", status="approved", state_version=2, input_checksum="sha256:input", artifact_set_checksum="sha256:artifacts", expires_at=snapshot.expires_at, created_at=now))
    graph = RecordingGraph()
    settings = Settings(_env_file=None, artifact_root=tmp_path / "artifacts", workspace_root=tmp_path / "workspaces", snapshot_root=tmp_path / "snapshots", delivery_root=tmp_path / "delivery", sandbox_root=tmp_path / "sandboxes")
    return MigrationRunService(settings, session_scope_factory=scope, graph=graph, now_provider=lambda: now), scope, graph


def _request(key="create-1"):
    return CreateRunRequest("preflight-1", "sha256:input", "sha256:artifacts", key, "reviewer", {"preserve_ui": True})


def test_create_and_start_use_authoritative_transitions(tmp_path: Path):
    service, scope, graph = _service(tmp_path)
    created = service.create(_request())
    assert created.status == "CREATED"
    started = service.start(run_id=created.run_id, expected_state_version=created.state_version, idempotency_key="start-1", actor="operator")
    assert started.status == "SOURCE_VALIDATION_RUNNING"
    assert graph.calls == [(created.run_id, created.graph_thread_id)]
    replay = service.create(_request())
    assert replay.idempotent_replay is True


def test_second_active_run_is_rejected(tmp_path: Path):
    service, _, _ = _service(tmp_path)
    service.create(_request())
    with pytest.raises(MigrationRunError, match="Only one mutating"):
        service.create(_request("create-2"))


def test_rejected_stale_preflight_does_not_create_run_or_artifacts(tmp_path: Path):
    service, scope, _ = _service(tmp_path)

    with pytest.raises(MigrationRunError, match="stale"):
        service.create(CreateRunRequest("preflight-1", "sha256:old", "sha256:artifacts", "stale-1", "reviewer", {}))

    with scope() as session:
        assert session.scalar(select(MigrationRunModel)) is None
        assert session.scalar(select(WorkflowEventModel)) is None
    assert not (tmp_path / "artifacts").exists()


def test_graph_handoff_failure_rolls_back_accepted_transition(tmp_path: Path):
    service, scope, _ = _service(tmp_path)
    failing = MigrationRunService(
        Settings(_env_file=None, artifact_root=tmp_path / "artifacts", workspace_root=tmp_path / "workspaces", snapshot_root=tmp_path / "snapshots", delivery_root=tmp_path / "delivery", sandbox_root=tmp_path / "sandboxes"),
        session_scope_factory=scope, graph=FailingGraph(), now_provider=lambda: datetime.now(UTC),
    )
    created = service.create(_request("handoff-create"))

    with pytest.raises(MigrationRunError, match="handoff failed safely"):
        failing.start(run_id=created.run_id, expected_state_version=created.state_version, idempotency_key="handoff-start", actor="operator")

    with scope() as session:
        run = session.get(MigrationRunModel, created.run_id)
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == created.run_id).order_by(WorkflowEventModel.sequence)))
        assert run is not None and run.status == "CREATED" and run.state_version == created.state_version
        assert [event.event_type for event in events] == ["RUN_CREATED"]


def test_run_evidence_is_recorded_with_checksums_and_confined_paths(tmp_path: Path):
    service, scope, _ = _service(tmp_path)
    created = service.create(_request("evidence-1"))

    assert len(created.artifacts) == 5
    assert all(artifact.relative_path.startswith("00_job_setup/") for artifact in created.artifacts)
    assert all(".." not in Path(artifact.relative_path).parts for artifact in created.artifacts)
    with scope() as session:
        metadata = list(session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == created.run_id)))
        assert len(metadata) == 5
        assert {row.checksum for row in metadata} == {artifact.checksum for artifact in created.artifacts}
