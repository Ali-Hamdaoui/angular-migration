from __future__ import annotations

import sys
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.command_execution.worker import (
    CommandDefinition,
    CommandLogWriter,
    CommandPolicy,
    CommandRegistry,
    ExecutionWorker,
    SupervisedProcessResult,
    WorkerSupervisor,
)
from app.domain.contracts import (
    CancellationPolicy,
    CommandRequestDto,
    CommandStatus,
)
from app.orchestration.transformer_graph import TransformerOrchestrator
from app.repositories.models import (
    CommandAuthorizationAuditModel,
    CommandExecutionModel,
    CommandLogChunkModel,
    CommandLogSummaryModel,
    MigrationRunModel,
    StageCheckpointModel,
    StagePromptRequestModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.models.base import Base
from app.services.command_executor_service import (
    CommandExecutorError,
    CommandExecutorService,
)
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformer_stage_service import TransformerStageService


NOW = datetime(2026, 7, 30, tzinfo=UTC)


def _database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _request(*, runtime_profile_id: str = "profile-1") -> CommandRequestDto:
    return CommandRequestDto(
        command_id="test-command",
        run_id="run-1",
        stage_id="stage-1",
        requested_by="operator",
        requester="operator",
        executable="python",
        arguments=["--version"],
        shell=False,
        working_directory_alias="run_workspace",
        runtime_profile_id=runtime_profile_id,
        timeout_seconds=30,
        network_profile="none",
        cancellation_policy=CancellationPolicy.TERMINATE_PROCESS_TREE,
        idempotency_key="logical-command",
        requested_at=NOW,
    )


def _worker(
    tmp_path: Path,
    supervisor,
    *,
    runtime_profiles: frozenset[str] = frozenset({"profile-1"}),
) -> ExecutionWorker:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(exist_ok=True)
    policy = CommandPolicy(
        sandbox_root=tmp_path,
        registry=CommandRegistry(
            definitions=(
                CommandDefinition(
                    "test-command",
                    "python",
                    ("--version",),
                    ("python.exe", sys.executable),
                ),
            )
        ),
        working_directory_aliases={"run_workspace": tmp_path},
        runtime_profiles=runtime_profiles,
        network_profiles=frozenset({"none"}),
    )
    store = LocalFilesystemArtifactStore(artifacts, fixed_run_root=artifacts)
    return ExecutionWorker(policy, CommandLogWriter(store), supervisor=supervisor)


def _result(
    tmp_path: Path,
    *,
    status: CommandStatus,
    exit_code: int | None,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
    cancelled: bool = False,
):
    supervisor = MagicMock()
    supervisor.run.return_value = SupervisedProcessResult(
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        cancelled=cancelled,
    )
    return _worker(tmp_path, supervisor).run(_request())


def _seed_execution(factory, tmp_path: Path, *, status: str = "running"):
    session = factory()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(exist_ok=True)
    run = MigrationRunModel(
        id="run-1",
        status="STAGE_CREATED",
        run_phase="FEASIBILITY_PLANNING",
        phase_status="completed",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(artifacts),
        workspace_aliases={"run_workspace": str(tmp_path)},
        created_at=NOW,
        updated_at=NOW,
    )
    authorization = CommandAuthorizationAuditModel(
        id="auth-1",
        run_id=run.id,
        stage_id="stage-1",
        command_id="test-command",
        executable="python",
        arguments=["--version"],
        decision="accepted",
        reasons=[],
        policy_version="policy-v1",
        idempotency_key="logical-command",
        request_payload_hash="sha256:request",
        expected_state_version=7,
        execution_profile_id="profile-1",
        workspace_alias="run_workspace",
        network_profile="none",
        correlation_id="correlation-1",
        actor="operator",
        artifact_ids=[],
        state_version=7,
        created_at=NOW,
    )
    execution = CommandExecutionModel(
        id="exec-original",
        run_id=run.id,
        stage_id="stage-1",
        authorization_id=authorization.id,
        idempotency_key="logical-command",
        executable="python",
        arguments=["--version"],
        working_directory_alias="run_workspace",
        safe_relative_working_directory="run_workspace",
        runtime_profile_id="profile-1",
        network_profile="none",
        command_id="test-command",
        status=status,
        requested_at=NOW,
        started_at=NOW if status == "running" else None,
        finished_at=NOW if status == "failed" else None,
        operation_kind="mutating",
        state_version=2,
        attempt_number=1,
    )
    session.add_all([run, authorization, execution])
    session.commit()
    return session, run, authorization, execution


def _finish(session, run, authorization, execution, result) -> None:
    CommandExecutorService()._finish_execution(
        session,
        execution,
        result,
        run=run,
        authorization=authorization,
        profile={"checksum": "sha256:runtime"},
    )
    session.commit()


def test_pre_spawn_policy_exception_is_failed_with_causal_evidence(tmp_path: Path):
    raw = _worker(tmp_path, MagicMock(), runtime_profiles=frozenset()).run(
        _request(runtime_profile_id="unregistered")
    )
    engine, factory = _database(tmp_path)
    session, run, authorization, execution = _seed_execution(factory, tmp_path)

    _finish(session, run, authorization, execution, raw)

    assert execution.status == "failed"
    assert execution.failure_code == "COMMAND_PRESPAWN_FAILED"
    assert execution.failure_message == "Runtime profile is not registered"
    assert execution.process_id is None
    assert execution.exit_code is None
    assert execution.stderr_artifact_id
    session.close()
    engine.dispose()


def test_real_process_spawn_captures_stdout_and_stderr(tmp_path: Path):
    command = (
        "-c",
        "import sys; print('spawned-out'); print('spawned-err', file=sys.stderr)",
    )
    policy = CommandPolicy(
        sandbox_root=tmp_path,
        registry=CommandRegistry(
            definitions=(
                CommandDefinition("spawn-proof", sys.executable, command),
            )
        ),
        working_directory_aliases={"run_workspace": tmp_path},
        runtime_profiles=frozenset({"profile-1"}),
        network_profiles=frozenset({"none"}),
        environment_allowlist=("PATH",),
    )
    artifacts = tmp_path / "spawn-artifacts"
    artifacts.mkdir()
    worker = ExecutionWorker(
        policy,
        CommandLogWriter(
            LocalFilesystemArtifactStore(artifacts, fixed_run_root=artifacts)
        ),
    )
    request = _request().model_copy(
        update={
            "command_id": "spawn-proof",
            "executable": sys.executable,
            "arguments": list(command),
        }
    )

    result = worker.run(request)

    assert result.result.status == CommandStatus.SUCCEEDED
    assert result.result.exit_code == 0
    assert result.stdout_artifact.content.strip() == "spawned-out"
    assert result.stderr_artifact.content.strip() == "spawned-err"


@pytest.mark.skipif(os.name != "nt", reason="Windows process environment contract")
def test_windows_safe_environment_keeps_systemroot_for_npm_cmd():
    environment = WorkerSupervisor._build_safe_environment(("PATH",))

    assert environment["SYSTEMROOT"] == os.environ["SYSTEMROOT"]


def test_nonzero_exit_persists_exit_code_logs_and_duration(tmp_path: Path):
    engine, factory = _database(tmp_path)
    session, run, authorization, execution = _seed_execution(factory, tmp_path)
    result = _result(
        tmp_path,
        status=CommandStatus.FAILED,
        exit_code=17,
        stdout="npm stdout",
        stderr="npm error",
    )

    _finish(session, run, authorization, execution, result)

    summary = session.get(CommandLogSummaryModel, execution.id)
    assert (execution.status, execution.exit_code) == ("failed", 17)
    assert execution.duration_ms is not None
    assert execution.failure_code == "COMMAND_EXIT_NONZERO"
    assert execution.failure_message == "npm error"
    assert execution.stdout_artifact_id and execution.stderr_artifact_id
    assert summary.finalized is True
    session.close()
    engine.dispose()


def test_running_command_uses_registered_failed_terminal_transition(tmp_path: Path):
    engine, factory = _database(tmp_path)
    session, run, authorization, execution = _seed_execution(factory, tmp_path)

    _finish(
        session,
        run,
        authorization,
        execution,
        _result(tmp_path, status=CommandStatus.FAILED, exit_code=1),
    )

    assert execution.status == "failed"
    assert execution.state_version == 3
    session.close()
    engine.dispose()


def test_worker_internal_exception_after_running_persists_traceback(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    session, _run, _authorization, execution = _seed_execution(factory, tmp_path)
    service = CommandExecutorService()
    error = RuntimeError("capture pipeline broke")

    service._persist_internal_failure(
        session,
        execution,
        error,
        "Traceback (most recent call last):\n  File \"worker.py\", line 1\nRuntimeError: capture pipeline broke",
    )
    session.commit()
    service._fail_execution(session, execution, "EXECUTION_FAILED", str(error))
    session.commit()

    chunk = session.scalar(
        select(CommandLogChunkModel).where(
            CommandLogChunkModel.execution_id == execution.id,
            CommandLogChunkModel.stream == "system",
        )
    )
    assert execution.status == "failed"
    assert execution.failure_message == "capture pipeline broke"
    assert execution.duration_ms is not None
    assert 'File "worker.py", line 1' in chunk.text
    session.close()
    engine.dispose()


def test_duplicate_identical_terminal_callback_is_a_noop(tmp_path: Path):
    engine, factory = _database(tmp_path)
    session, run, authorization, execution = _seed_execution(factory, tmp_path)
    result = _result(tmp_path, status=CommandStatus.SUCCEEDED, exit_code=0)
    _finish(session, run, authorization, execution, result)
    version = execution.state_version
    artifact_ids = list(execution.artifact_ids)

    _finish(session, run, authorization, execution, result)

    assert execution.state_version == version
    assert execution.artifact_ids == artifact_ids
    session.close()
    engine.dispose()


def test_conflicting_terminal_callback_fails_closed(tmp_path: Path):
    engine, factory = _database(tmp_path)
    session, run, authorization, execution = _seed_execution(factory, tmp_path)
    _finish(
        session,
        run,
        authorization,
        execution,
        _result(tmp_path, status=CommandStatus.SUCCEEDED, exit_code=0),
    )

    with pytest.raises(CommandExecutorError) as raised:
        _finish(
            session,
            run,
            authorization,
            execution,
            _result(tmp_path, status=CommandStatus.FAILED, exit_code=1),
        )

    assert raised.value.code == "TERMINAL_RESULT_CONFLICT"
    assert execution.status == "succeeded"
    assert execution.exit_code == 0
    session.close()
    engine.dispose()


def test_terminal_transition_rollback_does_not_erase_evidence(
    tmp_path: Path,
    monkeypatch,
):
    engine, factory = _database(tmp_path)
    session, run, authorization, execution = _seed_execution(factory, tmp_path)
    service = CommandExecutorService()
    result = _result(
        tmp_path,
        status=CommandStatus.FAILED,
        exit_code=9,
        stderr="durable npm failure",
    )

    def reject_transition(*_args, **_kwargs):
        raise CommandExecutorError("TEST_TRANSITION_FAILED", "terminal CAS failed")

    monkeypatch.setattr(service, "transition_execution", reject_transition)
    with pytest.raises(CommandExecutorError, match="terminal CAS failed"):
        service._finish_execution(
            session,
            execution,
            result,
            run=run,
            authorization=authorization,
            profile={"checksum": "sha256:runtime"},
        )
    session.rollback()
    session.close()

    proof = factory()
    durable = proof.get(CommandExecutionModel, execution.id)
    assert durable.status == "running"
    assert durable.exit_code == 9
    assert durable.duration_ms is not None
    assert durable.failure_message == "durable npm failure"
    assert durable.stdout_artifact_id and durable.stderr_artifact_id
    assert proof.get(CommandLogSummaryModel, execution.id).finalized is True
    proof.close()
    engine.dispose()


def test_retry_is_parent_bound_idempotent_and_preserves_failed_attempt(tmp_path: Path):
    engine, factory = _database(tmp_path)
    session, _run, _authorization, failed = _seed_execution(
        factory,
        tmp_path,
        status="failed",
    )
    failed.failure_code = "COMMAND_PRESPAWN_FAILED"
    session.commit()
    service = CommandExecutorService()

    created = service.queue_retry_execution(
        session,
        failed.id,
        idempotency_key=f"{failed.id}:retry:1",
    )
    replay = service.queue_retry_execution(
        session,
        failed.id,
        idempotency_key=f"{failed.id}:retry:1",
    )
    session.commit()

    successor = session.get(CommandExecutionModel, created.execution_id)
    active = session.scalars(
        select(CommandExecutionModel).where(
            CommandExecutionModel.status.in_(("pending", "queued", "running"))
        )
    ).all()
    assert replay.idempotent_replay is True
    assert replay.execution_id == successor.id
    assert successor.parent_execution_id == failed.id
    assert successor.attempt_number == 2
    assert len(active) == 1
    assert (failed.status, failed.failure_code, failed.attempt_number) == (
        "failed",
        "COMMAND_PRESPAWN_FAILED",
        1,
    )
    session.close()
    engine.dispose()


def test_recovered_retry_creates_one_idempotent_successor_attempt(tmp_path: Path):
    engine, factory = _database(tmp_path)
    session, _run, _authorization, failed = _seed_execution(
        factory,
        tmp_path,
        status="failed",
    )
    service = CommandExecutorService()
    retry = service.queue_retry_execution(
        session,
        failed.id,
        idempotency_key=f"{failed.id}:retry:1",
    )
    successor = session.get(CommandExecutionModel, retry.execution_id)
    successor.status = "failed"
    successor.finished_at = NOW
    session.commit()

    created = service.queue_retry_execution(
        session,
        successor.id,
        idempotency_key=f"{successor.id}:retry:1",
        workspace_recovered=True,
    )
    replay = service.queue_retry_execution(
        session,
        successor.id,
        idempotency_key=f"{successor.id}:retry:1",
        workspace_recovered=True,
    )

    assert replay.execution_id == created.execution_id
    assert replay.idempotent_replay is True
    assert session.query(CommandExecutionModel).count() == 3
    session.close()
    engine.dispose()


def test_transformer_restart_queues_one_retry_then_success_advances(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    session, _run, _authorization, failed = _seed_execution(
        factory,
        tmp_path,
        status="failed",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "package-lock.json").write_text("before", encoding="utf-8")
    initial_fingerprint = StageSandboxCopier.fingerprint(workspace)
    continuation = TransformationContinuationModel(
        id="continuation-1",
        run_id="run-1",
        current_stage_id="stage-1",
        thread_id="thread-1",
        status="queued",
        current_node="verify_bootstrap",
        g06_approval_id="g06-1",
        plan_id="plan-1",
        plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-1",
        stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation",
        request_checksum="sha256:continuation",
        state_version=3,
        created_at=NOW,
        updated_at=NOW,
    )
    step = StageStepModel(
        id="step-1",
        run_id="run-1",
        stage_id="stage-1",
        name="bootstrap_install-0",
        status="FAILED",
        component_type="command",
        execution_id=failed.id,
        state_version=1,
        updated_at=NOW,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id="run-1",
        stage_id="stage-1",
        alias="STAGE_WORKSPACE_STAGE_1",
        workspace_path=str(workspace),
        workspace_fingerprint=initial_fingerprint,
        active=True,
        created_at=NOW,
    )
    session.add_all([continuation, step, binding])
    session.commit()
    service = TransformerStageService(now_provider=lambda: NOW)

    successor_id = service.verify_bootstrap(session, continuation)
    service.verify_bootstrap(session, continuation)
    session.commit()

    assert session.query(CommandExecutionModel).count() == 2
    successor = session.get(CommandExecutionModel, successor_id)
    successor.status = "succeeded"
    successor.exit_code = 0
    successor.finished_at = NOW
    successor.duration_ms = 10
    successor.runtime_checksum = "sha256:runtime"
    successor.result_artifact_id = "artifact-result"
    continuation.status = "queued"
    (workspace / "package-lock.json").write_text("after", encoding="utf-8")
    session.commit()

    service.verify_bootstrap(session, continuation)
    session.commit()

    assert continuation.current_node == "angular_update"
    assert continuation.status == "queued"
    assert session.query(StageCheckpointModel).count() == 1
    assert failed.status == "failed"
    session.close()
    engine.dispose()


@pytest.mark.parametrize(
    ("status", "timed_out", "cancelled", "expected"),
    (
        (CommandStatus.CANCELLED, False, True, "cancelled"),
        (CommandStatus.CANCELLED, True, True, "timed_out"),
    ),
)
def _test_scope(factory):
    """Return a context manager factory that yields sessions from the given factory, mirroring session_scope commit semantics."""

    from contextlib import contextmanager

    @contextmanager
    def scope():
        s = factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    return scope


def test_angular_update_handle_prompt_marks_step_failed(tmp_path: Path):
    engine, factory = _database(tmp_path)
    NOW = datetime(2026, 7, 30, tzinfo=UTC)

    session = factory()
    run = MigrationRunModel(
        id="run-1",
        status="STAGE_CREATED",
        run_phase="FEASIBILITY_PLANNING",
        phase_status="completed",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(tmp_path / "artifacts"),
        workspace_aliases={"STAGE_SANDBOX": str(tmp_path)},
        created_at=NOW,
        updated_at=NOW,
    )
    _exec_base = dict(
        executable="npx",
        arguments=[],
        requested_at=NOW,
        state_version=1,
        attempt_number=1,
        operation_kind="mutating",
    )

    execution = CommandExecutionModel(
        id="exec-au",
        run_id="run-1",
        stage_id="stage-1",
        command_id="angular-update-exact",
        status="failed",
        failure_code="NG_UPDATE_FAILED",
        failure_message="ng update failed with exit code 1",
        **_exec_base,
    )
    step = StageStepModel(
        id="step-au",
        run_id="run-1",
        stage_id="stage-1",
        name="angular_update-0",
        status="RUNNING",
        component_type="command",
        execution_id=execution.id,
        state_version=1,
        updated_at=NOW,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id="run-1",
        stage_id="stage-1",
        alias="STAGE_WORKSPACE_STAGE_1",
        workspace_path=str(tmp_path / "workspace"),
        workspace_fingerprint="fingerprint-1",
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id="run-1",
        current_stage_id="stage-1",
        thread_id="thread-1",
        status="running",
        current_node="handle_prompt",
        worker_id="worker-1",
        g06_approval_id="g06-1",
        plan_id="plan-1",
        plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-1",
        stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation",
        request_checksum="sha256:continuation",
        state_version=3,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([run, execution, step, binding, continuation])
    session.commit()
    session.close()

    orchestrator = TransformerOrchestrator(
        scope=lambda: _test_scope(factory)(),
        stage_service=MagicMock(),
        gate_service=MagicMock(),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=MagicMock(),
        repair_service=MagicMock(),
        patch_service=MagicMock(),
        sealing_flow=MagicMock(),
    )

    orchestrator._handle_prompt("cont-1", "worker-1")

    session = factory()
    step = session.get(StageStepModel, "step-au")
    cont = session.get(TransformationContinuationModel, "cont-1")
    assert step.status == "FAILED"
    assert step.completed_at is not None
    assert cont.current_node == "classify_failure"
    assert cont.last_error_code == "NG_UPDATE_FAILED"
    assert cont.last_error_message == "ng update failed with exit code 1"
    session.close()
    engine.dispose()


def test_angular_update_handle_prompt_routes_to_classify_failure(tmp_path: Path):
    engine, factory = _database(tmp_path)
    NOW = datetime(2026, 7, 30, tzinfo=UTC)

    _exec_base = dict(
        executable="npx",
        arguments=[],
        requested_at=NOW,
        state_version=1,
        attempt_number=1,
        operation_kind="mutating",
    )

    session = factory()
    run = MigrationRunModel(
        id="run-2",
        status="STAGE_CREATED",
        run_phase="FEASIBILITY_PLANNING",
        phase_status="completed",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(tmp_path / "artifacts"),
        workspace_aliases={"STAGE_SANDBOX": str(tmp_path)},
        created_at=NOW,
        updated_at=NOW,
    )
    execution = CommandExecutionModel(
        id="exec-au-2",
        run_id="run-2",
        stage_id="stage-2",
        command_id="angular-update-exact",
        status="failed",
        failure_code="COMMAND_EXIT_NONZERO",
        failure_message="Angular update failed",
        **_exec_base,
    )
    step = StageStepModel(
        id="step-au-2",
        run_id="run-2",
        stage_id="stage-2",
        name="angular_update-0",
        status="RUNNING",
        component_type="command",
        execution_id=execution.id,
        state_version=1,
        updated_at=NOW,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-2",
        run_id="run-2",
        stage_id="stage-2",
        alias="STAGE_WORKSPACE_STAGE_2",
        workspace_path=str(tmp_path / "workspace2"),
        workspace_fingerprint="fingerprint-2",
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-2",
        run_id="run-2",
        current_stage_id="stage-2",
        thread_id="thread-2",
        status="running",
        current_node="handle_prompt",
        worker_id="worker-2",
        g06_approval_id="g06-2",
        plan_id="plan-2",
        plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-2",
        stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation-2",
        request_checksum="sha256:continuation-2",
        state_version=3,
        created_at=NOW,
        updated_at=NOW,
        last_error_code=None,
        last_error_message=None,
    )
    session.add_all([run, execution, step, binding, continuation])
    session.commit()
    session.close()

    orchestrator = TransformerOrchestrator(
        scope=lambda: _test_scope(factory)(),
        stage_service=MagicMock(),
        gate_service=MagicMock(),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=MagicMock(),
        repair_service=MagicMock(),
        patch_service=MagicMock(),
        sealing_flow=MagicMock(),
    )

    orchestrator._handle_prompt("cont-2", "worker-2")

    session = factory()
    cont = session.get(TransformationContinuationModel, "cont-2")
    assert cont.current_node == "classify_failure"
    assert cont.status == "queued"
    assert cont.last_error_code == "COMMAND_EXIT_NONZERO"
    assert cont.last_error_message == "Angular update failed"
    session.close()
    engine.dispose()


def test_angular_update_handle_prompt_success_without_prompt_unchanged(tmp_path: Path):
    engine, factory = _database(tmp_path)
    NOW = datetime(2026, 7, 30, tzinfo=UTC)

    _exec_base = dict(
        executable="npx",
        arguments=[],
        requested_at=NOW,
        state_version=1,
        attempt_number=1,
        operation_kind="mutating",
    )

    session = factory()
    run = MigrationRunModel(
        id="run-3",
        status="STAGE_CREATED",
        run_phase="FEASIBILITY_PLANNING",
        phase_status="completed",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(tmp_path / "artifacts"),
        workspace_aliases={"STAGE_SANDBOX": str(tmp_path)},
        created_at=NOW,
        updated_at=NOW,
    )
    execution = CommandExecutionModel(
        id="exec-au-3",
        run_id="run-3",
        stage_id="stage-3",
        command_id="angular-update-exact",
        status="succeeded",
        **_exec_base,
    )
    step = StageStepModel(
        id="step-au-3",
        run_id="run-3",
        stage_id="stage-3",
        name="angular_update-0",
        status="RUNNING",
        component_type="command",
        execution_id=execution.id,
        state_version=1,
        updated_at=NOW,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-3",
        run_id="run-3",
        stage_id="stage-3",
        alias="STAGE_WORKSPACE_STAGE_3",
        workspace_path=str(tmp_path / "workspace3"),
        workspace_fingerprint="fingerprint-3",
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-3",
        run_id="run-3",
        current_stage_id="stage-3",
        thread_id="thread-3",
        status="running",
        current_node="handle_prompt",
        worker_id="worker-3",
        g06_approval_id="g06-3",
        plan_id="plan-3",
        plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-3",
        stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation-3",
        request_checksum="sha256:continuation-3",
        state_version=3,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([run, execution, step, binding, continuation])
    session.commit()
    session.close()

    orchestrator = TransformerOrchestrator(
        scope=lambda: _test_scope(factory)(),
        stage_service=MagicMock(),
        gate_service=MagicMock(),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=MagicMock(),
        repair_service=MagicMock(),
        patch_service=MagicMock(),
        sealing_flow=MagicMock(),
    )

    orchestrator._handle_prompt("cont-3", "worker-3")

    session = factory()
    step = session.get(StageStepModel, "step-au-3")
    cont = session.get(TransformationContinuationModel, "cont-3")
    assert step.status == "PASSED"
    assert step.completed_at is not None
    assert cont.current_node == "target_inspection"
    assert cont.status == "queued"
    session.close()
    engine.dispose()


def test_angular_update_handle_prompt_prompt_path_unchanged(tmp_path: Path):
    engine, factory = _database(tmp_path)
    NOW = datetime(2026, 7, 30, tzinfo=UTC)

    _exec_base = dict(
        executable="npx",
        arguments=[],
        requested_at=NOW,
        state_version=1,
        attempt_number=1,
        operation_kind="mutating",
    )

    session = factory()

    run = MigrationRunModel(
        id="run-4",
        status="STAGE_CREATED",
        run_phase="FEASIBILITY_PLANNING",
        phase_status="completed",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(tmp_path / "artifacts"),
        workspace_aliases={"STAGE_SANDBOX": str(tmp_path)},
        created_at=NOW,
        updated_at=NOW,
    )
    execution = CommandExecutionModel(
        id="exec-au-4",
        run_id="run-4",
        stage_id="stage-4",
        command_id="angular-update-exact",
        status="succeeded",
        prompt_request_id="prompt-4",
        checkpoint_id="checkpoint-4",
        **_exec_base,
    )
    step = StageStepModel(
        id="step-au-4",
        run_id="run-4",
        stage_id="stage-4",
        name="angular_update-0",
        status="RUNNING",
        component_type="command",
        execution_id=execution.id,
        state_version=1,
        updated_at=NOW,
    )
    snapshot = tmp_path / ".checkpoints" / "snapshot-4"
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / "package.json").write_text("{}", encoding="utf-8")
    checkpoint_fingerprint = StageSandboxCopier.fingerprint(snapshot)

    checkpoint = StageCheckpointModel(
        id="checkpoint-4",
        run_id="run-4",
        stage_id="stage-4",
        kind="pre_angular_update",
        sequence=1,
        workspace_alias="STAGE_WORKSPACE_STAGE_4",
        workspace_path=str(snapshot),
        workspace_fingerprint=checkpoint_fingerprint,
        safe_for_resume=True,
        sealed=False,
        state_version=1,
        created_at=NOW,
    )
    prompt = StagePromptRequestModel(
        id="prompt-4",
        run_id="run-4",
        stage_id="stage-4",
        execution_id=execution.id,
        kind="angular_update",
        detector_version="v1",
        normalized_prompt="some prompt",
        context_artifact_ids=[],
        pre_command_fingerprint="fp-before",
        status="decided",
        reconstruction_checkpoint_id=checkpoint.id,
        prompt_checksum="sha256:prompt",
        decided_at=NOW,
        created_at=NOW,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-4",
        run_id="run-4",
        stage_id="stage-4",
        alias="STAGE_WORKSPACE_STAGE_4",
        workspace_path=str(tmp_path / "workspace4"),
        workspace_fingerprint="fingerprint-4",
        active=True,
        created_at=NOW,
    )
    (tmp_path / "workspace4").mkdir(parents=True, exist_ok=True)
    continuation = TransformationContinuationModel(
        id="cont-4",
        run_id="run-4",
        current_stage_id="stage-4",
        thread_id="thread-4",
        status="running",
        current_node="handle_prompt",
        worker_id="worker-4",
        g06_approval_id="g06-4",
        plan_id="plan-4",
        plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-4",
        stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation-4",
        request_checksum="sha256:continuation-4",
        state_version=3,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([run, execution, step, checkpoint, prompt, binding, continuation])
    session.commit()
    session.close()

    mock_stage = MagicMock(spec=TransformerStageService)
    mock_stage._binding.return_value = binding
    mock_stage.reconstruct_workspace.return_value = "observed-fingerprint-4"
    mock_explainer = MagicMock()

    orchestrator = TransformerOrchestrator(
        scope=lambda: _test_scope(factory)(),
        stage_service=mock_stage,
        gate_service=MagicMock(),
        transformation_evidence=MagicMock(),
        prompt_explainer=mock_explainer,
        validation_runner=MagicMock(),
        failure_evidence=MagicMock(),
        repair_service=MagicMock(),
        patch_service=MagicMock(),
        sealing_flow=MagicMock(),
    )

    orchestrator._handle_prompt("cont-4", "worker-4")

    session = factory()
    cont = session.get(TransformationContinuationModel, "cont-4")
    prompt = session.get(StagePromptRequestModel, "prompt-4")
    assert cont.status == "waiting_prompt"
    assert cont.current_node == "wait_prompt_decision"
    assert prompt.status == "waiting_human"
    assert prompt.observed_fingerprint == "observed-fingerprint-4"
    session.close()
    engine.dispose()


def test_angular_update_checkpoint_restoration_success(tmp_path: Path):
    """_classify_failure restores checkpoint and routes to angular_update for environment_transient."""
    engine, factory = _database(tmp_path)
    NOW = datetime(2026, 7, 30, tzinfo=UTC)
    _exec_base = dict(
        executable="npx", arguments=[], requested_at=NOW,
        state_version=1, attempt_number=1, operation_kind="mutating",
    )
    session = factory()
    run = MigrationRunModel(
        id="run-cr", status="STAGE_CREATED", run_phase="FEASIBILITY_PLANNING",
        phase_status="completed", state_version=7,
        run_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"),
        workspace_aliases={"STAGE_SANDBOX": str(tmp_path)},
        created_at=NOW, updated_at=NOW,
    )
    # Create a checkpoint directory with a file (simulating pre-update workspace)
    checkpoint_dir = tmp_path / ".checkpoints" / "snapshot-cr"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    (checkpoint_dir / "package.json").write_text('{"name":"test"}', encoding="utf-8")
    checkpoint_fp = StageSandboxCopier.fingerprint(checkpoint_dir)
    checkpoint = StageCheckpointModel(
        id="checkpoint-cr", run_id="run-cr", stage_id="stage-cr",
        kind="pre_angular_update", sequence=1,
        workspace_alias="STAGE_WORKSPACE_STAGE_CR",
        workspace_path=str(checkpoint_dir),
        workspace_fingerprint=checkpoint_fp,
        safe_for_resume=True, sealed=False, state_version=1, created_at=NOW,
    )
    execution = CommandExecutionModel(
        id="exec-cr", run_id="run-cr", stage_id="stage-cr",
        command_id="angular-update-exact", status="failed",
        failure_code="COMMAND_EXIT_NONZERO",
        failure_message="ng update failed", **_exec_base,
    )
    step = StageStepModel(
        id="step-cr", run_id="run-cr", stage_id="stage-cr",
        name="angular_update-0", status="FAILED",
        component_type="command", execution_id=execution.id,
        state_version=1, updated_at=NOW,
    )
    workspace = tmp_path / "workspace-cr"
    workspace.mkdir(parents=True, exist_ok=True)
    binding = StageWorkspaceBindingModel(
        id="binding-cr", run_id="run-cr", stage_id="stage-cr",
        alias="STAGE_WORKSPACE_STAGE_CR",
        workspace_path=str(workspace), workspace_fingerprint="old-fp",
        active=True, created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-cr", run_id="run-cr", current_stage_id="stage-cr",
        thread_id="thread-cr", status="running", current_node="classify_failure",
        worker_id="worker-cr", g06_approval_id="g06-cr",
        plan_id="plan-cr", plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-cr", stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation-cr", request_checksum="sha256:continuation-cr",
        state_version=3, attempt=1, max_attempts=3, created_at=NOW, updated_at=NOW,
    )
    session.add_all([run, checkpoint, execution, step, binding, continuation])
    session.commit()
    session.close()

    mock_failures = MagicMock()
    mock_route = MagicMock()
    mock_route.value = "environment_transient"
    mock_failures.collect.return_value = {
        "workspace_path": str(workspace),
        "stage_id": "stage-cr",
        "failure_fingerprint": "fp-1",
    }
    mock_failures.classify.return_value = mock_route
    mock_artifact = MagicMock()
    mock_artifact.ref.checksum = "sha256:artifact"
    mock_failures.write.return_value = (mock_artifact, mock_artifact)

    orchestrator = TransformerOrchestrator(
        scope=lambda: _test_scope(factory)(),
        stage_service=MagicMock(spec=TransformerStageService),
        gate_service=MagicMock(),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=mock_failures,
        repair_service=MagicMock(),
        patch_service=MagicMock(),
        sealing_flow=MagicMock(),
    )
    mock_stage = orchestrator._stage
    mock_stage._binding.return_value = binding
    mock_stage.reconstruct_workspace.return_value = checkpoint_fp
    mock_stage.snapshot_workspace.return_value = MagicMock(fingerprint="fp")

    orchestrator._classify_failure("cont-cr", "worker-cr")

    session = factory()
    cont = session.get(TransformationContinuationModel, "cont-cr")
    assert cont.current_node == "angular_update"
    assert cont.status == "queued"
    mock_stage.reconstruct_workspace.assert_called_once()
    session.close()
    engine.dispose()


def test_angular_update_failure_routes_to_classify_vertical(tmp_path: Path):
    """Full vertical: _handle_prompt failure routes through classify_failure to angular_update on transient."""
    engine, factory = _database(tmp_path)
    NOW = datetime(2026, 7, 30, tzinfo=UTC)
    _exec_base = dict(
        executable="npx", arguments=[], requested_at=NOW,
        state_version=1, attempt_number=1, operation_kind="mutating",
    )
    session = factory()
    run = MigrationRunModel(
        id="run-vr", status="STAGE_CREATED", run_phase="FEASIBILITY_PLANNING",
        phase_status="completed", state_version=7,
        run_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"),
        workspace_aliases={"STAGE_SANDBOX": str(tmp_path)},
        created_at=NOW, updated_at=NOW,
    )
    checkpoint_dir = tmp_path / ".checkpoints" / "snapshot-vr"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    (checkpoint_dir / "package.json").write_text('{"name":"test"}', encoding="utf-8")
    checkpoint_fp = StageSandboxCopier.fingerprint(checkpoint_dir)
    checkpoint = StageCheckpointModel(
        id="checkpoint-vr", run_id="run-vr", stage_id="stage-vr",
        kind="pre_angular_update", sequence=1,
        workspace_alias="STAGE_WORKSPACE_STAGE_VR",
        workspace_path=str(checkpoint_dir),
        workspace_fingerprint=checkpoint_fp,
        safe_for_resume=True, sealed=False, state_version=1, created_at=NOW,
    )
    execution = CommandExecutionModel(
        id="exec-vr", run_id="run-vr", stage_id="stage-vr",
        command_id="angular-update-exact", status="failed",
        failure_code="COMMAND_EXIT_NONZERO",
        failure_message="ng update failed", **_exec_base,
    )
    step = StageStepModel(
        id="step-vr", run_id="run-vr", stage_id="stage-vr",
        name="angular_update-0", status="RUNNING",
        component_type="command", execution_id=execution.id,
        state_version=1, updated_at=NOW,
    )
    workspace = tmp_path / "workspace-vr"
    workspace.mkdir(parents=True, exist_ok=True)
    binding = StageWorkspaceBindingModel(
        id="binding-vr", run_id="run-vr", stage_id="stage-vr",
        alias="STAGE_WORKSPACE_STAGE_VR",
        workspace_path=str(workspace), workspace_fingerprint="fp-before",
        active=True, created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-vr", run_id="run-vr", current_stage_id="stage-vr",
        thread_id="thread-vr", status="running", current_node="handle_prompt",
        worker_id="worker-vr", g06_approval_id="g06-vr",
        plan_id="plan-vr", plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-vr", stage_plan_checksum="sha256:stage-plan",
        idempotency_key="continuation-vr", request_checksum="sha256:continuation-vr",
        state_version=3, attempt=1, max_attempts=3, created_at=NOW, updated_at=NOW,
    )
    session.add_all([run, checkpoint, execution, step, binding, continuation])
    session.commit()
    session.close()

    mock_failures = MagicMock()
    mock_route = MagicMock()
    mock_route.value = "environment_transient"
    mock_failures.collect.return_value = {
        "workspace_path": str(workspace),
        "stage_id": "stage-vr",
        "failure_fingerprint": "fp-1",
    }
    mock_failures.classify.return_value = mock_route
    mock_artifact = MagicMock()
    mock_artifact.ref.checksum = "sha256:artifact"
    mock_failures.write.return_value = (mock_artifact, mock_artifact)

    mock_stage = MagicMock(spec=TransformerStageService)
    mock_stage._binding.return_value = binding
    mock_stage.reconstruct_workspace.return_value = checkpoint_fp
    mock_stage.snapshot_workspace.return_value = MagicMock(fingerprint="fp")

    orchestrator = TransformerOrchestrator(
        scope=lambda: _test_scope(factory)(),
        stage_service=mock_stage,
        gate_service=MagicMock(),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=mock_failures,
        repair_service=MagicMock(),
        patch_service=MagicMock(),
        sealing_flow=MagicMock(),
    )

    # Step 1: handle_prompt should terminalize and route to classify_failure
    orchestrator._handle_prompt("cont-vr", "worker-vr")
    session = factory()
    step = session.get(StageStepModel, "step-vr")
    cont = session.get(TransformationContinuationModel, "cont-vr")
    assert step.status == "FAILED", f"Expected FAILED, got {step.status}"
    assert cont.current_node == "classify_failure", f"Expected classify_failure, got {cont.current_node}"
    assert cont.status == "queued"
    session.close()

    # Step 2: classify_failure should detect it, restore checkpoint, route to angular_update
    # Reclaim continuation (worker claims it again)
    session = factory()
    cont = session.get(TransformationContinuationModel, "cont-vr")
    cont.status = "running"
    cont.worker_id = "worker-vr-v2"
    cont.state_version += 1
    session.commit()
    session.close()

    orchestrator._classify_failure("cont-vr", "worker-vr-v2")

    session = factory()
    cont = session.get(TransformationContinuationModel, "cont-vr")
    assert cont.current_node == "angular_update", f"Expected angular_update, got {cont.current_node}"
    assert cont.status == "queued"
    assert cont.attempt == 2
    mock_stage.reconstruct_workspace.assert_called()
    session.close()
    engine.dispose()


def test_cancellation_and_timeout_keep_distinct_terminal_states(
    tmp_path: Path,
    status: CommandStatus,
    timed_out: bool,
    cancelled: bool,
    expected: str,
):
    engine, factory = _database(tmp_path)
    session, run, authorization, execution = _seed_execution(factory, tmp_path)

    _finish(
        session,
        run,
        authorization,
        execution,
        _result(
            tmp_path,
            status=status,
            exit_code=-1,
            timed_out=timed_out,
            cancelled=cancelled,
        ),
    )

    assert execution.status == expected
    assert execution.failure_code == (
        "COMMAND_TIMED_OUT" if timed_out else "COMMAND_CANCELLED"
    )
    session.close()
    engine.dispose()
