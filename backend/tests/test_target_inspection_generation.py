from contextlib import contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
from unittest.mock import MagicMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.orchestration.transformer_graph import TransformerOrchestrator, TransformerWorkflow
from app.repositories.models import (
    Base,
    CommandAuthorizationAuditModel,
    CommandExecutionModel,
    CommandLogChunkModel,
    ExecutionProfileModel,
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    RepairAttemptModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService


NOW = datetime(2026, 8, 10, tzinfo=UTC)


def _orchestrator():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    with factory() as session:
        session.add(
            TransformationContinuationModel(
                id="continuation-1",
                run_id="run-1",
                current_stage_id="stage-1",
                thread_id="thread-1",
                status="running",
                current_node="target_inspection",
                g06_approval_id="g06-1",
                plan_id="plan-1",
                plan_checksum="sha256:plan",
                stage_plan_id="stage-plan-1",
                stage_plan_checksum="sha256:stage-plan",
                worker_id="worker-1",
                idempotency_key="continuation-1",
                request_checksum="sha256:continuation",
                state_version=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.commit()

    orchestrator = TransformerOrchestrator.__new__(TransformerOrchestrator)
    orchestrator._scope = scope
    orchestrator._stage = MagicMock()
    return orchestrator, factory, engine


def _repair(attempt_id, attempt_number):
    return RepairAttemptModel(
        id=attempt_id,
        run_id="run-1",
        stage_id="stage-1",
        attempt_number=attempt_number,
        status="migration_retried",
        risk_level="medium",
        created_at=NOW,
    )


def test_initial_target_inspection_replay_uses_one_initial_generation_key():
    orchestrator, _factory, engine = _orchestrator()

    orchestrator.advance("continuation-1", "worker-1")
    orchestrator.advance("continuation-1", "worker-1")

    assert [call.kwargs["attempt_key"] for call in orchestrator._stage.queue_version_check.call_args_list] == [
        "target:initial",
        "target:initial",
    ]
    engine.dispose()


def test_repair_generation_replays_itself_and_changes_for_the_next_repair():
    orchestrator, factory, engine = _orchestrator()
    with factory() as session:
        session.add(_repair("repair-1", 1))
        session.commit()

    orchestrator.advance("continuation-1", "worker-1")
    orchestrator.advance("continuation-1", "worker-1")
    with factory() as session:
        session.add(_repair("repair-2", 2))
        session.commit()
    orchestrator.advance("continuation-1", "worker-1")

    keys = [
        call.kwargs["attempt_key"]
        for call in orchestrator._stage.queue_version_check.call_args_list
    ]
    assert keys == ["target:repair-1", "target:repair-1", "target:repair-2"]
    assert "target:initial" not in keys
    engine.dispose()


def test_transformer_workflow_can_route_translated_stage_error_to_durable_failure():
    workflow = TransformerWorkflow.__new__(TransformerWorkflow)
    workflow.orchestrator = MagicMock()
    workflow.graph = MagicMock()
    error = TransformerStageError("IDEMPOTENCY_KEY_REUSED", "generation key collision")
    workflow.graph.invoke.side_effect = error

    workflow.invoke("continuation-1", "worker-1")

    workflow.orchestrator.fail.assert_called_once_with(
        "continuation-1", "worker-1", error
    )


def _target_recovery_fixture(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'target-recovery.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    workspace = tmp_path / "stage"
    artifacts = tmp_path / "artifacts"
    checkpoint = tmp_path / "checkpoint"
    (workspace / "node_modules" / "@angular" / "core").mkdir(parents=True)
    (workspace / "node_modules" / "@angular" / "cli").mkdir(parents=True)
    artifacts.mkdir()
    checkpoint.mkdir()
    (workspace / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"@angular/core": "19.2.0"},
                "devDependencies": {"@angular/cli": "19.2.0"},
            }
        ),
        encoding="utf-8",
    )
    (workspace / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/@angular/core": {"version": "19.2.0"},
                    "node_modules/@angular/cli": {"version": "19.2.0"},
                }
            }
        ),
        encoding="utf-8",
    )
    for package in ("core", "cli"):
        (workspace / "node_modules" / "@angular" / package / "package.json").write_text(
            json.dumps({"version": "19.2.0"}), encoding="utf-8"
        )

    @contextmanager
    def scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    command = {
        "command_id": "angular-version-verify",
        "template_id": "tpl-angular-version-verify",
        "template_version": 1,
        "executable": "npx",
        "arguments": ["ng", "version"],
        "working_directory_alias": "STAGE_WORKSPACE_STAGE_1",
        "timeout_seconds": 300,
        "network_profile": "approved-registries-only",
    }
    with factory() as session:
        session.add_all(
            [
                MigrationRunModel(
                    id="run-recovery",
                    status="STAGE_CREATED",
                    run_phase="STAGED_MIGRATION",
                    state_version=10,
                    actor="operator",
                    run_root=str(tmp_path),
                    artifact_root=str(artifacts),
                    workspace_aliases={"STAGE_WORKSPACE_STAGE_1": str(workspace)},
                    created_at=NOW,
                    updated_at=NOW,
                ),
                MigrationStageModel(
                    id="stage-1",
                    run_id="run-recovery",
                    stage_order=1,
                    source_version_family="angular-18.x",
                    target_version_family="angular-19.x",
                    status="planned",
                    created_at=NOW,
                ),
                MigrationPlanModel(
                    id="plan-recovery",
                    run_id="run-recovery",
                    idempotency_key="plan-recovery",
                    request_checksum="sha256:plan-request",
                    actor="operator",
                    status="approved",
                    version=1,
                    plan={},
                    checksum="sha256:plan",
                    artifact_ids=[],
                    artifact_checksums={},
                    state_version=10,
                    event_sequence=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                StageExecutionPlanModel(
                    id="stage-plan-recovery",
                    run_id="run-recovery",
                    migration_plan_id="plan-recovery",
                    stage_id="stage-1",
                    idempotency_key="stage-plan-recovery",
                    request_checksum="sha256:stage-plan-request",
                    actor="operator",
                    status="approved",
                    version=1,
                    stage_plan={
                        "stage_id": "stage-1",
                        "plan_version": 1,
                        "target_exact": "19.2.0",
                        "target_cli_exact": "19.2.0",
                        "execution_profile_id": "profile-1",
                        "commands": {"target_version_check": [command]},
                    },
                    checksum="sha256:stage-plan",
                    artifact_ids=[],
                    artifact_checksums={},
                    state_version=10,
                    event_sequence=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                ExecutionProfileModel(
                    id="profile-row",
                    run_id="run-recovery",
                    idempotency_key="profile-row",
                    request_checksum="sha256:profile",
                    policy_version="profile-v1",
                    status="selected",
                    source_angular_exact="18.2.0",
                    selected_profile_id="profile-1",
                    selected_checksum="sha256:runtime",
                    profiles=[],
                    blockers=[],
                    guidance=[],
                    artifact_ids=[],
                    state_version=10,
                    event_sequence=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                StageWorkspaceBindingModel(
                    id="binding-recovery",
                    run_id="run-recovery",
                    stage_id="stage-1",
                    alias="STAGE_WORKSPACE_STAGE_1",
                    workspace_path=str(workspace),
                    workspace_fingerprint=StageSandboxCopier.fingerprint(workspace),
                    active=True,
                    created_at=NOW,
                ),
                TransformationContinuationModel(
                    id="continuation-recovery",
                    run_id="run-recovery",
                    current_stage_id="stage-1",
                    thread_id="thread-recovery",
                    status="running",
                    current_node="version_verify",
                    g06_approval_id="g06-recovery",
                    plan_id="plan-recovery",
                    plan_checksum="sha256:plan",
                    stage_plan_id="stage-plan-recovery",
                    stage_plan_checksum="sha256:stage-plan",
                    worker_id="worker-1",
                    idempotency_key="continuation-recovery",
                    request_checksum="sha256:continuation",
                    state_version=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                RepairAttemptModel(
                    id="repair-1",
                    run_id="run-recovery",
                    stage_id="stage-1",
                    attempt_number=1,
                    status="migration_retried",
                    risk_level="medium",
                    created_at=NOW,
                ),
                StageCheckpointModel(
                    id="checkpoint-angular",
                    run_id="run-recovery",
                    stage_id="stage-1",
                    kind="pre_angular_update",
                    sequence=1,
                    workspace_alias="STAGE_WORKSPACE_STAGE_1",
                    workspace_path=str(checkpoint),
                    workspace_fingerprint="sha256:checkpoint",
                    state_version=1,
                    created_at=NOW,
                ),
                CommandExecutionModel(
                    id="exec-angular",
                    run_id="run-recovery",
                    stage_id="stage-1",
                    idempotency_key="exec-angular",
                    request_payload_hash="sha256:angular",
                    executable="npx",
                    arguments=[],
                    status="succeeded",
                    requested_at=NOW,
                    started_at=NOW,
                    finished_at=NOW,
                    exit_code=0,
                    command_id="angular-update-exact",
                    checkpoint_id="checkpoint-angular",
                    runtime_checksum="sha256:runtime",
                ),
                CommandExecutionModel(
                    id="exec-corrupted",
                    run_id="run-recovery",
                    stage_id="stage-1",
                    idempotency_key="target:repair-1",
                    request_payload_hash="sha256:corrupted",
                    executable="npx",
                    arguments=["ng", "version"],
                    status="failed",
                    requested_at=NOW,
                    started_at=NOW,
                    finished_at=NOW,
                    command_id="angular-version-verify",
                    operation_kind="read_only",
                    reconstruction_required=True,
                    blockers=["BASELINE_RECONSTRUCTION_FAILED"],
                ),
                StageStepModel(
                    id="step-angular",
                    run_id="run-recovery",
                    stage_id="stage-1",
                    name="angular_update-0",
                    status="PASSED",
                    component_type="command",
                    execution_id="exec-angular",
                    state_version=1,
                    updated_at=NOW,
                ),
                StageStepModel(
                    id="step-version",
                    run_id="run-recovery",
                    stage_id="stage-1",
                    name="target_version_check-0",
                    status="RUNNING",
                    component_type="command",
                    execution_id="exec-corrupted",
                    state_version=1,
                    updated_at=NOW,
                ),
            ]
        )
        session.commit()

    service = TransformerStageService(scope=scope, now_provider=lambda: NOW)
    workflow = TransformerWorkflow(
        TransformerOrchestrator(scope=scope, stage_service=service)
    )
    return engine, factory, workflow


def _invoke_target_recovery(workflow):
    workflow.invoke("continuation-recovery", "worker-1")


def test_corrupted_target_check_gets_one_deterministic_fresh_successor(tmp_path):
    engine, factory, workflow = _target_recovery_fixture(tmp_path)

    _invoke_target_recovery(workflow)
    with factory() as session:
        executions = session.scalars(
            select(CommandExecutionModel).order_by(CommandExecutionModel.requested_at)
        ).all()
        successor = next(row for row in executions if row.command_id == "angular-version-verify" and row.id != "exec-corrupted")
        assert successor.id != "exec-corrupted"
        assert successor.idempotency_key == (
            "continuation-recovery:stage-1:command:target:repair-1:recovery-1:target_version_check"
        )
        assert successor.parent_execution_id == "exec-corrupted"
        assert successor.status == "queued"
        assert session.query(CommandAuthorizationAuditModel).count() == 1
        continuation = session.get(TransformationContinuationModel, "continuation-recovery")
        assert continuation.waiting_execution_id == successor.id

        step = session.get(StageStepModel, "step-version")
        step.execution_id = "exec-corrupted"
        continuation.status = "running"
        continuation.worker_id = "worker-1"
        continuation.waiting_execution_id = None
        session.commit()

    _invoke_target_recovery(workflow)
    with factory() as session:
        successors = session.scalars(
            select(CommandExecutionModel).where(
                CommandExecutionModel.command_id == "angular-version-verify",
                CommandExecutionModel.id != "exec-corrupted",
            )
        ).all()
        assert len(successors) == 1
        assert session.query(CommandAuthorizationAuditModel).count() == 1
        assert session.get(StageStepModel, "step-version").execution_id == successors[0].id
    engine.dispose()


def test_successful_target_recovery_successor_advances_version_verification(tmp_path):
    engine, factory, workflow = _target_recovery_fixture(tmp_path)
    _invoke_target_recovery(workflow)
    with factory() as session:
        successor = session.scalar(
            select(CommandExecutionModel).where(
                CommandExecutionModel.command_id == "angular-version-verify",
                CommandExecutionModel.id != "exec-corrupted",
            )
        )
        successor.status = "succeeded"
        successor.exit_code = 0
        successor.finished_at = NOW
        successor.runtime_checksum = "sha256:runtime"
        successor.artifact_ids = []
        session.add(
            CommandLogChunkModel(
                id="chunk-recovery",
                execution_id=successor.id,
                run_id="run-recovery",
                sequence=1,
                stream="stdout",
                text="Angular: 19.2.0\nAngular CLI: 19.2.0\n",
                byte_count=40,
                character_count=40,
                created_at=NOW,
            )
        )
        continuation = session.get(TransformationContinuationModel, "continuation-recovery")
        continuation.status = "running"
        continuation.worker_id = "worker-1"
        continuation.waiting_execution_id = None
        session.commit()

    _invoke_target_recovery(workflow)
    with factory() as session:
        continuation = session.get(TransformationContinuationModel, "continuation-recovery")
        assert continuation.status == "waiting_gate"
        assert continuation.current_node == "wait_g08"
    engine.dispose()


def test_failed_target_recovery_successor_remains_fail_closed(tmp_path):
    engine, factory, workflow = _target_recovery_fixture(tmp_path)
    _invoke_target_recovery(workflow)
    with factory() as session:
        successor = session.scalar(
            select(CommandExecutionModel).where(
                CommandExecutionModel.command_id == "angular-version-verify",
                CommandExecutionModel.id != "exec-corrupted",
            )
        )
        successor.status = "failed"
        successor.failure_code = "COMMAND_EXIT_NONZERO"
        successor.failure_message = "version command failed"
        successor.finished_at = NOW
        continuation = session.get(TransformationContinuationModel, "continuation-recovery")
        continuation.status = "running"
        continuation.worker_id = "worker-1"
        continuation.waiting_execution_id = None
        session.commit()

    _invoke_target_recovery(workflow)
    with factory() as session:
        continuation = session.get(TransformationContinuationModel, "continuation-recovery")
        assert continuation.status == "blocked"
        assert continuation.last_error_code == "COMMAND_EXIT_NONZERO"
        assert continuation.last_error_message == "version command failed"
        assert session.query(CommandExecutionModel).filter_by(
            command_id="angular-version-verify"
        ).count() == 2
    engine.dispose()
