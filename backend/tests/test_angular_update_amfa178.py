import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType, CommandStatus, RunPhase, RunStatus, StageStatus
from app.domain.transformation import PromptDetectionResult, TargetVersionStatus
from app.repositories.models import (
    ActivePlanVersionModel,
    ArtifactMetadataModel,
    Base,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    StageExecutionPlanModel,
    WorkflowEventModel,
)
from app.repositories.baseline_models import BaselineQualificationModel
from app.repositories.execution_profiles import ExecutionProfileModel
from app.repositories.session import session_scope
from app.repositories.transformation_models import AngularUpdateRecordModel
from app.services.transformation_application_service import (
    AngularUpdateApplicationService,
    G03ApplicationError,
    _prompt_detected,
)
from app.command_execution.worker import CommandExecutionResult
from app.command_execution.worker import CommandLogWriter
from app.domain.contracts import CommandResultDto


def _stored(store, run_id, stage_id, name, payload):
    value = store.write_text_artifact(run_id, f"stage/{stage_id}/{name}", json.dumps(payload), ArtifactType.JSON, stage_id=stage_id)
    return value


@pytest.fixture
def valid_fixture(tmp_path):
    database = tmp_path / "amfa.sqlite"
    engine = create_engine(f"sqlite:///{database}")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    import app.repositories.session as session_module

    old_engine, old_session = session_module.engine, session_module.SessionLocal
    session_module.engine, session_module.SessionLocal = engine, SessionLocal
    Base.metadata.create_all(engine)
    run_id, stage_id = "run-amfa178", "stage-amfa178"
    run_root = tmp_path / "run"
    source = run_root / "source"
    workspace = run_root / "stage"
    artifacts = run_root / "artifacts"
    source.mkdir(parents=True)
    workspace.mkdir(parents=True)
    (source / "package.json").write_text("{}", encoding="utf-8")
    (workspace / "package.json").write_text(json.dumps({"dependencies": {"@angular/core": "18.2.0", "@angular/cli": "18.2.0"}}, indent=2), encoding="utf-8")
    (workspace / "package-lock.json").write_text(json.dumps({"packages": {"": {}, "node_modules/@angular/core": {"version": "18.2.0"}, "node_modules/@angular/cli": {"version": "18.2.0"}}}), encoding="utf-8")
    (workspace / "node_modules/@angular/core").mkdir(parents=True)
    (workspace / "node_modules/@angular/cli").mkdir(parents=True)
    (workspace / "node_modules/@angular/core/package.json").write_text('{"version":"18.2.0"}', encoding="utf-8")
    (workspace / "node_modules/@angular/cli/package.json").write_text('{"version":"18.2.0"}', encoding="utf-8")
    now = datetime.now(UTC)
    plan_checksum = "sha256:" + "1" * 64
    stage_checksum = "sha256:" + "2" * 64
    stage_plan = {"stage_id": stage_id, "source_exact": "17.3.0", "target_exact": "18.2.0", "target_cli_exact": "18.2.0", "execution_profile_id": "profile-amfa178", "commands": {"angular_update": [{"command_id": "angular-update", "executable": "npx", "arguments": ["--no-install", "ng", "update", "@angular/core@18.2.0", "@angular/cli@18.2.0"], "shell": False, "timeout_seconds": 30, "network_profile": "none"}]}}
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status=RunStatus.RUNNING.value, run_phase=RunPhase.STAGED_MIGRATION.value, phase_status="running", state_version=1, source_path=str(source), run_root=str(run_root), artifact_root=str(artifacts), workspace_aliases={"STAGE_SANDBOX": str(workspace)}, created_at=now, updated_at=now))
        session.add(MigrationStageModel(id=stage_id, run_id=run_id, stage_order=1, status=StageStatus.PREPARING.value, created_at=now))
        session.add(MigrationPlanModel(id="plan-amfa178", run_id=run_id, idempotency_key="plan-key", request_checksum="sha256:" + "3" * 64, actor="test", status="approved", version=1, plan={"plan_id": "plan-amfa178"}, checksum=plan_checksum, artifact_ids=[], artifact_checksums={}, state_version=1, event_sequence=1, created_at=now, updated_at=now))
        session.add(StageExecutionPlanModel(id="stage-plan-amfa178", migration_plan_id="plan-amfa178", run_id=run_id, stage_id=stage_id, idempotency_key="stage-plan-key", request_checksum="sha256:" + "4" * 64, actor="test", status="approved", version=1, stage_plan=stage_plan, checksum=stage_checksum, artifact_ids=[], artifact_checksums={}, state_version=1, event_sequence=1, created_at=now, updated_at=now))
        session.add(ActivePlanVersionModel(id="active-amfa178", run_id=run_id, scope=stage_id, migration_plan_id="plan-amfa178", stage_plan_id="stage-plan-amfa178", version=1, state_version=1, updated_at=now))
        session.add(G06ApprovalModel(id="g06-amfa178", run_id=run_id, gate_id="G06", gate_version="g06-v1", idempotency_key="g06-key", actor="test", status="approved", decision="approve", package_checksum="sha256:package", artifact_set_checksum="sha256:artifacts", plan_checksum=plan_checksum, stage_plan_checksum=stage_checksum, plan_version=1, workspace_fingerprint=None, artifact_ids=[], state_version=1, event_sequence=1, created_at=now, updated_at=now))
        session.add(ExecutionProfileModel(id="profile-row", run_id=run_id, idempotency_key="profile-key", request_checksum="sha256:" + "5" * 64, policy_version="angular-source-runtime-v1", status="selected", source_angular_exact="17.3.0", selected_profile_id="profile-amfa178", selected_checksum="sha256:" + "6" * 64, profiles=[], blockers=[], guidance=[], artifact_ids=[], state_version=1, event_sequence=1, created_at=now, updated_at=now))
        session.add(BaselineQualificationModel(id="baseline-row", run_id=run_id, idempotency_key="baseline-key", actor="test", status="qualified", snapshot_id="snapshot", sandbox_path=str(workspace), input_fingerprint="sha256:" + "7" * 64, sandbox_fingerprint="sha256:" + "8" * 64, package={}, lockfile={"status": "valid"}, sources=[], scripts=[], registry={}, blockers=[], warnings=[], authorization_status="authorized", checksum="sha256:" + "9" * 64, artifact_ids=[], state_version=1, event_sequence=1, created_at=now, updated_at=now))
        store = LocalFilesystemArtifactStore(artifacts, fixed_run_root=artifacts)
        refs = [_stored(store, run_id, stage_id, "g07-sandbox.json", {"status": "ready"}), _stored(store, run_id, stage_id, "bootstrap-result.json", {"install_status": "passed"}), _stored(store, run_id, stage_id, "source-integrity.json", {"status": "unchanged"})]
        for ref in refs:
            session.add(ArtifactMetadataModel(id="metadata-" + ref.ref.artifact_id, run_id=run_id, stage_id=stage_id, artifact_type=ref.ref.artifact_type.value, relative_path=ref.ref.relative_path, checksum=ref.ref.checksum, created_at=now))
    yield {"run_id": run_id, "stage_id": stage_id, "root": run_root, "source": source, "workspace": workspace, "artifacts": artifacts, "prerequisites": [ref.ref.artifact_id for ref in refs], "engine": engine, "SessionLocal": SessionLocal}
    engine.dispose()
    session_module.engine, session_module.SessionLocal = old_engine, old_session


class FakeWorker:
    def __init__(self, store, run_id, stage_id, workspace=None, mode="success"):
        self.store, self.run_id, self.stage_id, self.workspace, self.mode, self.calls = store, run_id, stage_id, workspace, mode, []

    def run(self, request, **kwargs):
        self.calls.append(request.command_id)
        if self.mode == "start-failure":
            raise OSError("process could not start")
        if request.command_id == "angular-update" and self.mode == "partial-mutation":
            (self.workspace / "partial-change.txt").write_text("partial", encoding="utf-8")
        now = datetime.now(UTC)
        if request.command_id == "angular-version":
            output = ("Angular CLI: 18.3.0\nAngular: 18.3.0\n" if self.mode == "wrong-target" else "Angular CLI: 18.2.0\nAngular: 18.2.0\n")
        elif request.command_id == "angular-dependency-tree":
            output = '{"dependencies":{"@angular/core":{"version":"18.2.0"},"@angular/cli":{"version":"18.2.0"}}}'
        else:
            output = "Continue? [y/n]" if self.mode == "prompt" else ""
        out = self.store.write_text_artifact(self.run_id, f"stage/{self.stage_id}/{request.command_id}.stdout.log", output, ArtifactType.TEXT_LOG, stage_id=self.stage_id) if output else None
        log = self.store.write_text_artifact(self.run_id, f"stage/{self.stage_id}/{request.command_id}.json", "{}", ArtifactType.COMMAND_LOG, stage_id=self.stage_id)
        status = CommandStatus.FAILED if self.mode in {"partial-mutation", "timeout", "cancel"} else CommandStatus.SUCCEEDED
        return CommandExecutionResult(CommandResultDto(command_id=request.command_id, run_id=self.run_id, stage_id=self.stage_id, status=status, started_at=now, finished_at=now, exit_code=1 if status is CommandStatus.FAILED else 0), log, stdout_artifact=out, timed_out=self.mode == "timeout", cancelled=self.mode in {"timeout", "cancel"})


def _request(fixture, key="update-key"):
    return SimpleNamespace(run_id=fixture["run_id"], stage_id=fixture["stage_id"], expected_state_version=1, idempotency_key=key, actor="test", source_version="17.3.0", target_version="18.2.0", prerequisite_artifact_ids=fixture["prerequisites"], model_dump=lambda **_: {"expected_state_version": 1, "idempotency_key": key, "actor": "test", "source_version": "17.3.0", "target_version": "18.2.0", "prerequisite_artifact_ids": fixture["prerequisites"]})


def test_valid_locked_plan_executes_and_verifies(valid_fixture):
    fixture = valid_fixture
    fake = FakeWorker(LocalFilesystemArtifactStore(fixture["artifacts"], fixed_run_root=fixture["artifacts"]), fixture["run_id"], fixture["stage_id"])
    service = AngularUpdateApplicationService(worker_factory=lambda *_: fake)
    result = service.start_update(fixture["run_id"], fixture["stage_id"], _request(fixture))
    assert result.status.value == "succeeded"
    assert result.target_version_status.value == "verified"
    assert fake.calls == ["angular-update", "angular-version", "angular-dependency-tree"]


def test_idempotent_replay_and_conflict(valid_fixture):
    fixture = valid_fixture
    fake = FakeWorker(LocalFilesystemArtifactStore(fixture["artifacts"], fixed_run_root=fixture["artifacts"]), fixture["run_id"], fixture["stage_id"])
    service = AngularUpdateApplicationService(worker_factory=lambda *_: fake)
    first = service.start_update(fixture["run_id"], fixture["stage_id"], _request(fixture))
    replay = service.start_update(fixture["run_id"], fixture["stage_id"], _request(fixture))
    assert first.command_execution_id == replay.command_execution_id and replay.idempotent_replay
    with pytest.raises(G03ApplicationError, match="Idempotency"):
        conflict = _request(fixture, key="update-key")
        conflict.target_version = "18.3.0"
        conflict.model_dump = lambda **_: {**_request(fixture, key="update-key").model_dump(), "target_version": "18.3.0"}
        service.start_update(fixture["run_id"], fixture["stage_id"], conflict)


def test_prerequisite_ownership_fails_closed(valid_fixture):
    fixture = valid_fixture
    service = AngularUpdateApplicationService(worker_factory=lambda *_: None)
    bad = _request(fixture)
    bad.prerequisite_artifact_ids = ["artifact-does-not-belong"]
    with pytest.raises(G03ApplicationError) as error:
        service.start_update(fixture["run_id"], fixture["stage_id"], bad)
    assert error.value.code == "PREREQUISITE_ARTIFACT_MISSING"


def test_prompt_detector_ignores_question_mark_and_detects_confirmation():
    assert not _prompt_detected(SimpleNamespace(stdout_artifact=SimpleNamespace(content="What? happened"), stderr_artifact=None))
    assert _prompt_detected(SimpleNamespace(stdout_artifact=SimpleNamespace(content="Continue? [y/n]"), stderr_artifact=None))


def test_forbidden_locked_plan_fails_before_worker_and_state_change(valid_fixture):
    fixture = valid_fixture
    with session_scope() as session:
        plan = session.get(StageExecutionPlanModel, "stage-plan-amfa178")
        stage_plan = dict(plan.stage_plan)
        commands = {**stage_plan["commands"]}
        commands["angular_update"] = [{**commands["angular_update"][0], "arguments": [*commands["angular_update"][0]["arguments"], "--force"]}]
        plan.stage_plan = {**stage_plan, "commands": commands}
    fake = FakeWorker(LocalFilesystemArtifactStore(fixture["artifacts"], fixed_run_root=fixture["artifacts"]), fixture["run_id"], fixture["stage_id"])
    with pytest.raises(G03ApplicationError) as error:
        AngularUpdateApplicationService(worker_factory=lambda *_: fake).start_update(fixture["run_id"], fixture["stage_id"], _request(fixture))
    assert error.value.code == "INCOMPATIBLE_PLAN_COMMAND"
    assert fake.calls == []


def test_partial_mutation_blocks_retry(valid_fixture):
    fixture = valid_fixture
    fake = FakeWorker(LocalFilesystemArtifactStore(fixture["artifacts"], fixed_run_root=fixture["artifacts"]), fixture["run_id"], fixture["stage_id"], fixture["workspace"], "partial-mutation")
    service = AngularUpdateApplicationService(worker_factory=lambda *_: fake)
    first = service.start_update(fixture["run_id"], fixture["stage_id"], _request(fixture))
    assert first.status.value == "failed"
    with pytest.raises(G03ApplicationError) as error:
        service.start_update(fixture["run_id"], fixture["stage_id"], _request(fixture))
    assert error.value.code == "PARTIAL_MUTATION_RECOVERY_REQUIRED"


def test_exit_zero_wrong_target_fails_exact_verification(valid_fixture):
    fixture = valid_fixture
    fake = FakeWorker(LocalFilesystemArtifactStore(fixture["artifacts"], fixed_run_root=fixture["artifacts"]), fixture["run_id"], fixture["stage_id"], fixture["workspace"], "wrong-target")
    result = AngularUpdateApplicationService(worker_factory=lambda *_: fake).start_update(fixture["run_id"], fixture["stage_id"], _request(fixture))
    assert result.status.value == "failed"
    assert result.target_version_status.value == "mismatch"


def test_prompt_blocks_and_emits_stable_reason(valid_fixture):
    fixture = valid_fixture
    fake = FakeWorker(LocalFilesystemArtifactStore(fixture["artifacts"], fixed_run_root=fixture["artifacts"]), fixture["run_id"], fixture["stage_id"], fixture["workspace"], "prompt")
    result = AngularUpdateApplicationService(worker_factory=lambda *_: fake).start_update(fixture["run_id"], fixture["stage_id"], _request(fixture))
    assert result.status.value == "failed"
    with session_scope() as session:
        event = session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.idempotency_key == "update-key:prompt"))
        assert event.payload["reason_code"] == "INTERACTIVE_PROMPT_DETECTED"


def test_command_output_redacts_secrets():
    assert "super-secret" not in CommandLogWriter._redact("token=super-secret password:pw")


@pytest.mark.parametrize(("mode", "code"), [("timeout", "TIMEOUT"), ("cancel", "CANCELLATION")])
def test_timeout_and_cancellation_fail_closed(valid_fixture, mode, code):
    fixture = valid_fixture
    fake = FakeWorker(LocalFilesystemArtifactStore(fixture["artifacts"], fixed_run_root=fixture["artifacts"]), fixture["run_id"], fixture["stage_id"], fixture["workspace"], mode)
    result = AngularUpdateApplicationService(worker_factory=lambda *_: fake).start_update(fixture["run_id"], fixture["stage_id"], _request(fixture))
    assert result.status.value == "failed"
    assert result.error_message == code


def test_command_start_failure_is_recorded_and_does_not_progress(valid_fixture):
    fixture = valid_fixture
    fake = FakeWorker(LocalFilesystemArtifactStore(fixture["artifacts"], fixed_run_root=fixture["artifacts"]), fixture["run_id"], fixture["stage_id"], fixture["workspace"], "start-failure")
    with pytest.raises(G03ApplicationError) as error:
        AngularUpdateApplicationService(worker_factory=lambda *_: fake).start_update(fixture["run_id"], fixture["stage_id"], _request(fixture))
    assert error.value.code == "COMMAND_START_FAILED"
    with session_scope() as session:
        record = session.scalar(select(AngularUpdateRecordModel).where(AngularUpdateRecordModel.run_id == fixture["run_id"]))
        assert record.error_message == "COMMAND_START_FAILED"


def test_missing_authority_and_tampered_checksum_fail_closed(valid_fixture):
    fixture = valid_fixture
    with session_scope() as session:
        metadata = session.scalar(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == fixture["run_id"]))
        metadata.checksum = "sha256:" + "f" * 64
    with pytest.raises(G03ApplicationError) as error:
        AngularUpdateApplicationService(worker_factory=lambda *_: None).start_update(fixture["run_id"], fixture["stage_id"], _request(fixture))
    assert error.value.code == "PREREQUISITE_ARTIFACT_CHECKSUM"
