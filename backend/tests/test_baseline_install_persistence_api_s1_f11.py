"""S1-F11-I02 durable install service coverage."""

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.baseline_contracts import BaselineInstallRequest
from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution import CommandLogWriter, CommandPolicy, CommandRegistry, ExecutionWorker, WorkerSupervisor
from app.command_execution.worker import SupervisedProcessResult
from app.domain.contracts import CommandStatus
from app.repositories.models import Base, BaselineQualificationModel, CommandExecutionModel, ExecutionProfileModel, MigrationRunModel, WorkflowEventModel
from app.services.baseline_install_application_service import BaselineInstallApplicationService


NOW = datetime(2026, 7, 16, tzinfo=UTC)


class SuccessfulNpmSupervisor(WorkerSupervisor):
    def run(self, request):
        return SupervisedProcessResult(CommandStatus.SUCCEEDED, 0, "npm ci completed", "")


def _fixture(tmp_path: Path):
    sandbox = tmp_path / "baseline"
    (sandbox / "node_modules").mkdir(parents=True)
    (sandbox / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    (sandbox / "package-lock.json").write_text('{"lockfileVersion":3}', encoding="utf-8")
    (sandbox / "node_modules" / ".package-lock.json").write_text(json.dumps({"packages": {"": {}}}), encoding="utf-8")
    artifact_root = tmp_path / "artifacts"
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-1", status="CREATED", run_phase="BASELINE", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, artifact_root=str(artifact_root), workspace_aliases={"BASELINE_SANDBOX": str(sandbox)}, created_at=NOW, updated_at=NOW))
        session.add(BaselineQualificationModel(id="baseline-1", run_id="run-1", idempotency_key="baseline", actor="operator", status="qualified", snapshot_id="snapshot-1", sandbox_path=str(sandbox), input_fingerprint="sha256:input", sandbox_fingerprint="sha256:sandbox", package={}, lockfile={"status": "valid", "lockfile_checksum": "sha256:lock"}, sources=[], scripts=[], registry={}, blockers=[], warnings=[], authorization_status="authorized", checksum="sha256:baseline", artifact_ids=[], state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW))
        session.add(ExecutionProfileModel(id="profile-1", run_id="run-1", idempotency_key="profile", request_checksum="sha256:req", policy_version="execution-profile-v1", status="selected", source_angular_exact="18.2.3", selected_profile_id="profile-1", selected_checksum="sha256:runtime", profiles=[], blockers=[], guidance=[], artifact_ids=[], state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW))
        session.commit()

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    def worker_factory(run):
        root = Path(run.artifact_root)
        store = LocalFilesystemArtifactStore(root, fixed_run_root=root)
        policy = CommandPolicy(sandbox_root=sandbox, registry=CommandRegistry(), working_directory_aliases={"BASELINE_SANDBOX": sandbox}, runtime_profiles=frozenset({"profile-1"}), network_profiles=frozenset({"approved-registries-only"}))
        return ExecutionWorker(policy, CommandLogWriter(store), supervisor=SuccessfulNpmSupervisor())

    return scope, sessions, engine, BaselineInstallApplicationService(session_scope_factory=scope, worker_factory=worker_factory, now_provider=lambda: NOW)


def _request(key="install-1", state=1):
    return BaselineInstallRequest(expected_state_version=state, idempotency_key=key, actor="operator", runtime_profile_id="profile-1", runtime_checksum="sha256:runtime", timeout_seconds=60)


def test_install_persists_execution_events_artifacts_and_idempotent_replay(tmp_path):
    scope, sessions, engine, service = _fixture(tmp_path)

    first = service.install("run-1", _request())
    replay = service.install("run-1", _request())

    assert first.status == "SUCCEEDED"
    assert replay.idempotent_replay is True
    assert replay.execution_id == first.execution_id
    assert len(first.artifact_ids) >= 5
    with sessions() as session:
        command = session.get(CommandExecutionModel, first.execution_id)
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == "run-1").order_by(WorkflowEventModel.sequence)))
        assert command is not None
        assert command.command_id == "npm-ci-bootstrap"
        assert command.status == "SUCCEEDED"
        assert [event.event_type for event in events] == ["COMMAND_QUEUED", "COMMAND_STARTED", "COMMAND_OUTPUT_AVAILABLE", "BASELINE_INSTALL_SUCCEEDED"]
        metadata = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == "run-1")))
        assert len(metadata) == 4
    assert service.get("run-1", first.execution_id).artifact_ids == first.artifact_ids
    engine.dispose()
