"""S1-F11-I02 durable install service coverage."""

import asyncio
import hashlib
import json
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.baseline_contracts import BaselineInstallCancelRequest, BaselineInstallRequest, BaselineInstallResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution import CommandLogWriter, CommandPolicy, CommandRegistry, ExecutionWorker, WorkerSupervisor
from app.command_execution.worker import SupervisedProcessResult
from app.domain.contracts import CommandStatus
from app.repositories.models import ArtifactMetadataModel, Base, BaselineQualificationModel, CommandExecutionModel, ExecutionProfileModel, MigrationRunModel, WorkerLeaseModel, WorkflowEventModel
from app.repositories.g02_models import G02ApprovalModel
from app.services.baseline_install_application_service import BaselineInstallApplicationError, BaselineInstallApplicationService
from app.api.routes.baseline import get_baseline_install_service
from app.api.routes import runs as runs_routes
from app.main import app
from fastapi.testclient import TestClient


NOW = datetime(2026, 7, 16, tzinfo=UTC)


class SuccessfulNpmSupervisor(WorkerSupervisor):
    def run(self, request, *, cancel_event=None, output_callback=None):
        return SupervisedProcessResult(CommandStatus.SUCCEEDED, 0, "npm ci completed", "")


class CancelledNpmSupervisor(WorkerSupervisor):
    def run(self, request, *, cancel_event=None, output_callback=None):
        if output_callback:
            output_callback("stdout", "partial npm output\n")
        return SupervisedProcessResult(CommandStatus.CANCELLED, None, "partial npm output\n", "cancelled\n")


class VerboseNpmSupervisor(WorkerSupervisor):
    def run(self, request, *, cancel_event=None, output_callback=None):
        output = "x" * 70_000
        if output_callback:
            output_callback("stdout", output)
        return SupervisedProcessResult(CommandStatus.SUCCEEDED, 0, output, "")

def _fixture(tmp_path: Path, supervisor=None):
    sandbox = tmp_path / "baseline"
    (sandbox / "node_modules").mkdir(parents=True)
    (sandbox / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    lockfile_content = '{"lockfileVersion":3}'
    (sandbox / "package-lock.json").write_text(lockfile_content, encoding="utf-8")
    (sandbox / "node_modules" / ".package-lock.json").write_text(json.dumps({"packages": {"": {}}}), encoding="utf-8")
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "snapshot-fingerprint.json").write_text(json.dumps({"fingerprint": "sha256:input"}), encoding="utf-8")
    (snapshot / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    (snapshot / "package-lock.json").write_text(lockfile_content, encoding="utf-8")
    artifact_root = tmp_path / "artifacts"
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-1", run_root=str(tmp_path), status="CREATED", run_phase="BASELINE", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, artifact_root=str(artifact_root), workspace_aliases={"BASELINE_SANDBOX": str(sandbox), "SOURCE_SNAPSHOT": str(snapshot)}, created_at=NOW, updated_at=NOW))
        session.add(BaselineQualificationModel(id="baseline-1", run_id="run-1", idempotency_key="baseline", actor="operator", status="qualified", snapshot_id="snapshot-1", sandbox_path=str(sandbox), input_fingerprint="sha256:input", sandbox_fingerprint="sha256:sandbox", package={}, lockfile={"status": "valid", "lockfile_checksum": "sha256:" + hashlib.sha256(lockfile_content.encode()).hexdigest()}, sources=[], scripts=[], registry={}, blockers=[], warnings=[], authorization_status="authorized", checksum="sha256:baseline", artifact_ids=[], state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW))
        session.add(ExecutionProfileModel(id="profile-1", run_id="run-1", idempotency_key="profile", request_checksum="sha256:req", policy_version="execution-profile-v1", status="selected", source_angular_exact="18.2.3", selected_profile_id="profile-1", selected_checksum="sha256:runtime", profiles=[], blockers=[], guidance=[], artifact_ids=[], state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW))
        session.add(G02ApprovalModel(id="g02-1", run_id="run-1", gate_id="G02", gate_version="g02-v1", idempotency_key="g02", actor="operator", status="approved", decision="approved", package_checksum="sha256:g02", artifact_set_checksum="sha256:artifacts", snapshot_id="snapshot-1", state_version=1, event_sequence=1, baseline_input_boundary="snapshot-1", package={}, artifact_ids=[], stale_reason=None, comment=None, created_at=NOW, updated_at=NOW))
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
        return ExecutionWorker(policy, CommandLogWriter(store), supervisor=supervisor or SuccessfulNpmSupervisor())

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
        lease = session.scalar(select(WorkerLeaseModel).where(WorkerLeaseModel.execution_id == first.execution_id))
        assert lease is not None
        assert lease.backend_instance_id and lease.heartbeat_at is not None
        assert [event.event_type for event in events] == ["COMMAND_QUEUED", "COMMAND_STARTED", "COMMAND_OUTPUT_AVAILABLE", "BASELINE_INSTALL_SUCCEEDED"]
        metadata = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == "run-1")))
        assert len(metadata) == 4
    assert service.get("run-1", first.execution_id).artifact_ids == first.artifact_ids
    engine.dispose()


def test_install_rejects_stale_state_before_execution(tmp_path):
    scope, sessions, engine, service = _fixture(tmp_path)
    with pytest.raises(BaselineInstallApplicationError) as error:
        service.install("run-1", _request(state=2))
    assert error.value.code == "STALE_STATE_VERSION"
    with sessions() as session:
        assert session.scalar(select(CommandExecutionModel).where(CommandExecutionModel.run_id == "run-1")) is None
    engine.dispose()


def test_install_rejects_runtime_checksum_authority_bypass(tmp_path):
    scope, sessions, engine, service = _fixture(tmp_path)
    with pytest.raises(BaselineInstallApplicationError) as error:
        service.install("run-1", BaselineInstallRequest(expected_state_version=1, idempotency_key="install-bad-runtime", actor="operator", runtime_profile_id="profile-1", runtime_checksum="sha256:not-selected", timeout_seconds=60))
    assert error.value.code == "EXECUTION_PROFILE_REQUIRED"
    with sessions() as session:
        assert session.scalar(select(CommandExecutionModel).where(CommandExecutionModel.run_id == "run-1")) is None
    engine.dispose()


def test_install_fails_closed_when_authorization_is_removed(tmp_path):
    scope, sessions, engine, service = _fixture(tmp_path)
    with sessions() as session:
        baseline = session.get(BaselineQualificationModel, "baseline-1")
        assert baseline is not None
        baseline.authorization_status = "not_authorized"
        session.commit()
    with pytest.raises(BaselineInstallApplicationError) as error:
        service.install("run-1", _request())
    assert error.value.code == "BASELINE_INSTALL_AUTHORIZATION_REQUIRED"
    engine.dispose()
class ApiInstallServiceStub:
    def __init__(self):
        self.response = BaselineInstallResponse(run_id="run-1", execution_id="execution-1", command_id="npm-ci-bootstrap", status="PENDING", state_version=2, event_sequence=2)

    def accept(self, run_id, request):
        return self.response

    def cancel(self, run_id, execution_id, request):
        self.response = self.response.model_copy(update={"status": "CANCELLED", "cancelled": True})
        return self.response

    def get(self, run_id, execution_id):
        return self.response


def test_install_and_cancel_routes_accept_and_return_durable_command_state():
    stub = ApiInstallServiceStub()
    app.dependency_overrides[get_baseline_install_service] = lambda: stub
    try:
        with TestClient(app) as client:
            install = client.post("/api/v1/runs/run-1/baseline/install", json={"expected_state_version": 1, "idempotency_key": "install-api", "actor": "operator", "runtime_profile_id": "profile-1", "runtime_checksum": "sha256:runtime"})
            assert install.status_code == 200
            assert install.json()["status"] == "PENDING"
            cancel = client.post("/api/v1/runs/run-1/commands/execution-1/cancel", json={"expected_state_version": 2, "idempotency_key": "cancel-api", "actor": "operator"})
            assert cancel.status_code == 200
            assert cancel.json()["cancelled"] is True
    finally:
        app.dependency_overrides.pop(get_baseline_install_service, None)


def test_run_events_replays_authoritative_sse_chunk(monkeypatch):
    event = SimpleNamespace(id="event-1", run_id="run-1", stage_id=None, event_type="COMMAND_OUTPUT_CHUNK", occurred_at=NOW, sequence=7, payload={"stream": "stdout", "chunk": "npm ci\
"})

    class FakeSession:
        def scalars(self, statement):
            return [event]

    @contextmanager
    def fake_scope():
        yield FakeSession()

    class FakeRequest:
        headers = {}
        query_params = {}

        async def is_disconnected(self):
            return False

    monkeypatch.setattr(runs_routes, "session_scope", fake_scope)
    response = runs_routes.stream_run_events("run-1", FakeRequest())
    chunk = asyncio.run(response.body_iterator.__anext__())
    assert "id: 7" in chunk
    assert "event: COMMAND_OUTPUT_CHUNK" in chunk
    assert '"sequence": 7' in chunk


def test_install_rejects_lockfile_checksum_mismatch_before_process(tmp_path):
    scope, sessions, engine, service = _fixture(tmp_path)
    sandbox = tmp_path / "baseline"
    (sandbox / "package-lock.json").write_text('{"lockfileVersion":3,"changed":true}', encoding="utf-8")
    with pytest.raises(BaselineInstallApplicationError) as error:
        service.install("run-1", _request(key="lock-mismatch"))
    assert error.value.code == "BASELINE_LOCKFILE_STALE"
    with sessions() as session:
        assert session.scalar(select(CommandExecutionModel).where(CommandExecutionModel.run_id == "run-1")) is None
    engine.dispose()


def test_install_rejects_registered_workspace_alias_outside_qualified_sandbox(tmp_path):
    scope, sessions, engine, service = _fixture(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    with sessions() as session:
        run = session.get(MigrationRunModel, "run-1")
        assert run is not None
        run.workspace_aliases = {"BASELINE_SANDBOX": str(external)}
        session.commit()
    with pytest.raises(BaselineInstallApplicationError) as error:
        service.install("run-1", _request(key="workspace-boundary"))
    assert error.value.code == "BASELINE_WORKSPACE_BOUNDARY"
    engine.dispose()


def test_restart_recovery_reruns_when_start_fingerprints_are_unchanged(tmp_path):
    scope, sessions, engine, service = _fixture(tmp_path)
    first = service.install("run-1", _request(key="restart-recovery"))
    with sessions() as session:
        command = session.get(CommandExecutionModel, first.execution_id)
        assert command is not None
        command.status = CommandStatus.RUNNING.value
        command.worker_id = "old-backend:pid-1"
        command.finished_at = None
        session.commit()
    assert service.reconcile_orphans() == 1
    deadline = time.time() + 5
    while time.time() < deadline:
        current = service.get("run-1", first.execution_id)
        if current is not None and current.status == CommandStatus.SUCCEEDED.value:
            break
        time.sleep(0.05)
    assert service.get("run-1", first.execution_id).status == CommandStatus.SUCCEEDED.value
    engine.dispose()

def test_cancelled_install_reconstructs_the_baseline_sandbox_and_persists_evidence(tmp_path):
    _scope, sessions, engine, service = _fixture(tmp_path, supervisor=CancelledNpmSupervisor())

    result = service.install("run-1", _request(key="cancelled-install"))

    assert result.status == CommandStatus.CANCELLED.value
    assert result.reconstruction_required is True
    assert (tmp_path / "baseline" / "package.json").is_file()
    assert not (tmp_path / "baseline" / "node_modules").exists()
    with sessions() as session:
        command = session.get(CommandExecutionModel, result.execution_id)
        assert command is not None
        assert "BASELINE_RECONSTRUCTION_FAILED" not in (command.blockers or [])
        artifacts = list(session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == "run-1")))
        assert any(item.relative_path.endswith("baseline_install_summary.json") for item in artifacts)
    engine.dispose()


def test_persisted_logs_are_complete_while_sse_chunks_are_bounded(tmp_path):
    _scope, sessions, engine, service = _fixture(tmp_path, supervisor=VerboseNpmSupervisor())

    result = service.install("run-1", _request(key="verbose-install"))

    store = LocalFilesystemArtifactStore(tmp_path / "artifacts", fixed_run_root=tmp_path / "artifacts")
    stdout = next(item for item in store.list_artifacts("run-1") if item.relative_path.endswith("npm-ci-bootstrap.stdout.log"))
    assert len(store.read_artifact("run-1", stdout.relative_path).content) == 70_000
    with sessions() as session:
        output_event = session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.event_type == "COMMAND_OUTPUT_CHUNK"))
        assert output_event is not None
        assert len(output_event.payload["chunk"].encode("utf-8")) <= 64_000
    assert result.status == CommandStatus.SUCCEEDED.value
    engine.dispose()