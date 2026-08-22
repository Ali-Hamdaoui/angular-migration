import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.domain.transformation import StageGateDecisionRequest
from app.orchestration.transformer_graph import TransformerOrchestrator, TransformerWorkflow
from app.orchestration.transformer_sealing_flow import TransformerSealingFlow
from app.repositories.models import (
    ActivePlanVersionModel,
    CommandExecutionModel,
    CommandLogChunkModel,
    ExecutionProfileModel,
    MigrationRunModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageGatePackageModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.services.stage_gate_service import StageGateService
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.transformation_continuation_service import TransformationContinuationService
from app.services.transformer_stage_service import TransformerStageError, TransformerStageService
from tests.test_transformation_continuation import _create, _session


NOW = datetime(2026, 7, 30, tzinfo=UTC)


def _runtime_session(*, expected_id="profile-1", expected_checksum="sha256:runtime",
                     actual_id="profile-1", actual_checksum="sha256:runtime",
                     status="resolved"):
    stage_plan = SimpleNamespace(stage_plan={
        "execution_profile_id": expected_id,
        "commands": {"bootstrap_install": [{
            "runtime_profile_checksum": expected_checksum,
        }]},
    })
    profile = SimpleNamespace(
        status=status,
        selected_profile_id=actual_id,
        selected_checksum=actual_checksum,
        profiles=[{
            "profile_id": actual_id,
            "checksum": actual_checksum,
            "node_executable": "node",
            "package_manager_executable": "npm",
        }],
    )

    class Session:
        def get(self, _model, _identifier):
            return stage_plan

        def scalar(self, _query):
            return profile

    return Session(), SimpleNamespace(stage_plan_id="stage-plan-1", run_id="run-1")


def test_runtime_binding_blocks_changed_profile_with_exact_evidence():
    session, continuation = _runtime_session(actual_id="profile-2")

    with pytest.raises(TransformerStageError) as raised:
        TransformerStageService().runtime_binding(session, continuation)

    assert raised.value.code == "EXECUTION_PROFILE_STALE"
    assert '"profile_id":"profile-1"' in raised.value.message
    assert '"profile_id":"profile-2"' in raised.value.message


def test_runtime_binding_blocks_frozen_command_checksum_mismatch():
    session, continuation = _runtime_session(expected_checksum="sha256:catalogue-bound")

    with pytest.raises(TransformerStageError) as raised:
        TransformerStageService().runtime_binding(session, continuation)

    assert raised.value.code == "EXECUTION_PROFILE_STALE"
    assert '"checksums":["sha256:catalogue-bound"]' in raised.value.message
    assert '"checksum":"sha256:runtime"' in raised.value.message


def test_stage_runtime_binding_payload_is_json_serializable():
    rows = [
        SimpleNamespace(
            kind=kind,
            resolved_path=f"C:/nvm/{kind}.exe",
            version_exact="12.22.12" if kind == "node" else "6.14.16",
            sha256="a" * 64,
            source="nvm",
            runtime_id="node-12.22.12",
            status="bound",
            created_at=NOW,
        )
        for kind in ("node", "npm", "npx")
    ]

    class Result:
        def all(self):
            return rows

    class Session:
        def scalars(self, _query):
            return Result()

    payload = TransformerStageService._stage_runtime_rows(
        Session(), SimpleNamespace(current_stage_id="stage-1")
    )

    json.dumps(payload)
    assert payload["runtime_bindings"]["node"]["version_exact"] == "12.22.12"


def test_angular_update_checkpoint_is_immutable_copy(tmp_path: Path):
    engine, session = _session(tmp_path)
    artifacts = tmp_path / "artifacts" / "run-1"
    artifacts.mkdir(parents=True)
    run = session.get(MigrationRunModel, "run-1")
    run.artifact_root = str(artifacts)
    continuation = _create(TransformationContinuationService(), session)
    workspace = tmp_path / "stage-workspace"
    workspace.mkdir()
    package = workspace / "package.json"
    package.write_text('{"angular":"11"}', encoding="utf-8")

    service = TransformerStageService()
    snapshot = service.snapshot_workspace(str(workspace), str(tmp_path), "stage-1")
    checkpoint = service.persist_snapshot_checkpoint(
        session, continuation, snapshot, "pre_angular_update"
    )
    session.commit()

    assert Path(checkpoint.workspace_path) != workspace.resolve()
    assert Path(checkpoint.workspace_path).is_relative_to(artifacts.resolve())
    package.write_text('{"angular":"12"}', encoding="utf-8")
    assert (Path(checkpoint.workspace_path) / "package.json").read_text(encoding="utf-8") == '{"angular":"11"}'
    session.close()
    engine.dispose()


def test_approved_g06_reaches_g07_then_bootstrap_checkpoint_without_angular_update(tmp_path: Path):
    engine, seed = _session(tmp_path)
    baseline = tmp_path / "baseline"
    stages = tmp_path / "stages"
    artifacts = tmp_path / "artifacts" / "run-1"
    baseline.mkdir()
    stages.mkdir()
    artifacts.mkdir(parents=True)
    (baseline / "package.json").write_text('{"dependencies":{"@angular/core":"18.2.0"}}', encoding="utf-8")
    (baseline / "package-lock.json").write_text('{"lockfileVersion":3}', encoding="utf-8")
    run = seed.get(MigrationRunModel, "run-1")
    run.actor = "operator"
    run.run_root = str(tmp_path)
    run.artifact_root = str(artifacts)
    run.workspace_aliases = {
        "BASELINE_SANDBOX": str(baseline),
        "STAGE_SANDBOX": str(stages),
    }
    stage_plan = seed.get(StageExecutionPlanModel, "stage-plan-1")
    command = {
        "command_id": "npm-ci-bootstrap",
        "template_id": "tpl-npm-ci",
        "template_version": 1,
        "executable": "npm",
        "arguments": ["ci"],
        "working_directory_alias": "STAGE_WORKSPACE_STAGE_1",
        "timeout_seconds": 3600,
        "network_profile": "approved-registries-only",
    }
    stage_plan.stage_plan = {
        "stage_id": "stage-1",
        "plan_version": 1,
        "source_family": "angular-18.x",
        "source_exact": "18.2.0",
        "target_family": "angular-19.x",
        "target_exact": "19.2.0",
        "execution_profile_id": "profile-1",
        "commands": {
            "bootstrap_install": [
                {**command, "runtime_profile_checksum": "sha256:runtime"}
            ]
        },
        "build_system_decision": {"action": "preserve", "builder": "application"},
        "validation_policy": {"policy_id": "validation-v1"},
        "recovery_policy": {"policy_id": "recovery-v1"},
        "repair_policy": {"policy_id": "repair-v1"},
        "forbidden_change_policy": {"policy_id": "forbidden-v1"},
    }
    seed.add_all(
        [
            ActivePlanVersionModel(
                id="active-stage",
                run_id="run-1",
                scope="stage-1",
                migration_plan_id="plan-1",
                stage_plan_id="stage-plan-1",
                version=1,
                state_version=7,
                updated_at=NOW,
            ),
            ExecutionProfileModel(
                id="profile-resolution-1",
                run_id="run-1",
                idempotency_key="profile",
                request_checksum="sha256:profile",
                policy_version="profile-v1",
                status="resolved",
                source_angular_exact="18.2.0",
                selected_profile_id="profile-1",
                selected_checksum="sha256:runtime",
                profiles=[
                    {
                        "profile_id": "profile-1",
                        "checksum": "sha256:runtime",
                        "node_executable": "node",
                        "package_manager_executable": "npm",
                    }
                ],
                blockers=[],
                guidance=[],
                artifact_ids=[],
                state_version=7,
                event_sequence=1,
                created_at=NOW,
                updated_at=NOW,
            ),
        ]
    )
    continuation = _create(TransformationContinuationService(), seed)
    seed.commit()
    continuation_id = continuation.id
    seed.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def scope():
        session = sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    continuations = TransformationContinuationService()
    stage_service = TransformerStageService(scope=scope, now_provider=lambda: NOW)
    stage_service._stage_runtime.resolve_stage = lambda *_args, **_kwargs: SimpleNamespace(
        status="bound", blocked_reason=None
    )
    stage_service._stage_runtime.record_binding = lambda *_args, **_kwargs: None
    workflow = TransformerWorkflow(
        TransformerOrchestrator(scope=scope, stage_service=stage_service)
    )

    def tick():
        with scope() as session:
            claimed = continuations.claim_next(session, "worker-1", NOW)
            assert claimed is not None
        workflow.invoke(continuation_id, "worker-1")

    for _ in range(6):
        tick()

    with scope() as session:
        durable = session.get(TransformationContinuationModel, continuation_id)
        gate = session.query(StageGatePackageModel).one()
        assert durable.status == "waiting_gate"
        assert durable.current_node == "wait_g07"
        assert gate.plan_version == 1
        StageGateService().decide(
            session,
            durable,
            "G07",
            StageGateDecisionRequest(
                expected_state_version=durable.state_version,
                idempotency_key="approve-g07",
                package_checksum=gate.package_checksum,
                workspace_fingerprint=gate.workspace_fingerprint,
                decision="approve",
                correlation_id="correlation-1",
            ),
            actor="operator",
            now=NOW,
        )

    tick()
    with scope() as session:
        command_row = session.query(CommandExecutionModel).one()
        assert command_row.command_id == "npm-ci-bootstrap"
        command_row.status = "succeeded"
        command_row.exit_code = 0
        command_row.finished_at = NOW
        command_row.runtime_checksum = "sha256:bootstrap"
        workspace = Path(command_row.safe_relative_working_directory or stages / "stage-1")
        if not workspace.is_absolute():
            workspace = stages / "stage-1"
        (stages / "stage-1" / "package-lock.json").write_text(
            '{"lockfileVersion":3,"packages":{"node_modules/x":{}}}',
            encoding="utf-8",
        )
        durable = session.get(TransformationContinuationModel, continuation_id)
        durable.status = "queued"

    tick()
    with scope() as session:
        durable = session.get(TransformationContinuationModel, continuation_id)
        checkpoints = session.query(StageCheckpointModel).order_by(StageCheckpointModel.sequence).all()
        commands = session.query(CommandExecutionModel).all()
        assert [item.kind for item in checkpoints] == ["pre_bootstrap", "post_bootstrap"]
        assert durable.status == "queued"
        assert durable.current_node == "angular_update"
        assert [item.command_id for item in commands] == ["npm-ci-bootstrap"]
    g07_package = json.loads(
        (artifacts / "04_workflow_state" / "stages" / "stage-1" / "gates" / "g07-package.json").read_text(
            encoding="utf-8"
        )
    )
    assert g07_package["plan_version"] == 1
    engine.dispose()


def _scoped_sessions(tmp_path: Path, artifacts: Path, workspace: Path):
    engine, seed = _session(tmp_path)
    run = seed.get(MigrationRunModel, "run-1")
    run.run_root = str(tmp_path)
    run.artifact_root = str(artifacts)
    run.workspace_aliases = {
        "BASELINE_SANDBOX": str(tmp_path),
        "STAGE_SANDBOX": str(tmp_path),
    }
    stage_plan = seed.get(StageExecutionPlanModel, "stage-plan-1")
    stage_plan.stage_plan = {
        "stage_id": "stage-1",
        "plan_version": 1,
        "source_family": "angular-18.x",
        "source_exact": "18.2.0",
        "target_family": "angular-19.x",
        "target_exact": "19.2.0",
        "target_cli_exact": "19.2.0",
        "execution_profile_id": "profile-1",
    }
    seed.add(
        StageWorkspaceBindingModel(
            id="binding-1",
            run_id="run-1",
            stage_id="stage-1",
            alias="STAGE_WORKSPACE_1",
            workspace_path=str(workspace),
            workspace_fingerprint=StageSandboxCopier.fingerprint(workspace),
            active=True,
            created_at=NOW,
        )
    )
    continuation = _create(TransformationContinuationService(), seed)
    seed.commit()
    continuation_id = continuation.id
    seed.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def scope():
        session = sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return engine, scope, continuation_id


def test_g08_package_binds_actual_plan_version(tmp_path: Path):
    artifacts = tmp_path / "artifacts" / "run-1"
    artifacts.mkdir(parents=True)
    workspace = tmp_path / "ws08"
    (workspace / "node_modules" / "@angular" / "core").mkdir(parents=True)
    (workspace / "node_modules" / "@angular" / "cli").mkdir(parents=True)
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
    (workspace / "node_modules" / "@angular" / "core" / "package.json").write_text(
        json.dumps({"version": "19.2.0"}), encoding="utf-8"
    )
    (workspace / "node_modules" / "@angular" / "cli" / "package.json").write_text(
        json.dumps({"version": "19.2.0"}), encoding="utf-8"
    )
    checkpoint = tmp_path / "ckpt08"
    checkpoint.mkdir()
    engine, scope, continuation_id = _scoped_sessions(tmp_path, artifacts, workspace)
    with scope() as session:
        continuation = session.get(TransformationContinuationModel, continuation_id)
        angular_execution = CommandExecutionModel(
            id="exec-angular",
            run_id="run-1",
            stage_id="stage-1",
            idempotency_key="exec-angular",
            request_payload_hash="sha256:angular",
            executable="npx",
            status="succeeded",
            requested_at=NOW,
            started_at=NOW,
            finished_at=NOW,
            exit_code=0,
            command_id="x2",
            checkpoint_id="checkpoint-08",
            runtime_checksum="sha256:runtime",
        )
        version_execution = CommandExecutionModel(
            id="exec-version",
            run_id="run-1",
            stage_id="stage-1",
            idempotency_key="exec-version",
            request_payload_hash="sha256:version",
            executable="npx",
            status="succeeded",
            requested_at=NOW,
            started_at=NOW,
            finished_at=NOW,
            exit_code=0,
            command_id="x3",
            runtime_checksum="sha256:runtime",
        )
        session.add_all(
            [
                StageCheckpointModel(
                    id="checkpoint-08",
                    run_id="run-1",
                    stage_id="stage-1",
                    kind="pre_angular_update",
                    sequence=1,
                    workspace_alias="STAGE_WORKSPACE_1",
                    workspace_path=str(checkpoint),
                    workspace_fingerprint="sha256:checkpoint",
                    state_version=1,
                    created_at=NOW,
                ),
                StageStepModel(
                    id="step-angular",
                    run_id="run-1",
                    stage_id="stage-1",
                    name="angular_update-0",
                    status="PASSED",
                    component_type="command",
                    execution_id="exec-angular",
                    completed_at=NOW,
                    state_version=1,
                    updated_at=NOW,
                ),
                StageStepModel(
                    id="step-version",
                    run_id="run-1",
                    stage_id="stage-1",
                    name="target_version_check-0",
                    status="PASSED",
                    component_type="command",
                    execution_id="exec-version",
                    completed_at=NOW,
                    state_version=1,
                    updated_at=NOW,
                ),
                angular_execution,
                version_execution,
                CommandLogChunkModel(
                    id="chunk-1",
                    execution_id="exec-version",
                    run_id="run-1",
                    sequence=1,
                    stream="stdout",
                    text="Angular: 19.2.0\nAngular CLI: 19.2.0\n",
                    byte_count=32,
                    character_count=32,
                    created_at=NOW,
                ),
            ]
        )
        continuation.status = "running"
        continuation.current_node = "version_verify"
        continuation.worker_id = "worker-1"
    stage_service = TransformerStageService(scope=scope, now_provider=lambda: NOW)
    workflow = TransformerWorkflow(
        TransformerOrchestrator(scope=scope, stage_service=stage_service)
    )
    workflow.invoke(continuation_id, "worker-1")

    with scope() as session:
        durable = session.get(TransformationContinuationModel, continuation_id)
        gate = session.query(StageGatePackageModel).one()
        assert durable.status == "waiting_gate"
        assert durable.current_node == "wait_g08"
        assert gate.gate_id == "G08"
        assert gate.plan_version == 1
    g08_package = json.loads(
        (artifacts / "04_workflow_state" / "stages" / "stage-1" / "gates" / "g08-package.json").read_text(
            encoding="utf-8"
        )
    )
    assert g08_package["plan_version"] == 1
    engine.dispose()


def test_g12_package_binds_actual_plan_version_and_stage_plan_checksum(tmp_path: Path):
    artifacts = tmp_path / "artifacts" / "run-1"
    artifacts.mkdir(parents=True)
    workspace = tmp_path / "ws12"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.ts").write_text("old", encoding="utf-8")
    engine, scope, continuation_id = _scoped_sessions(tmp_path, artifacts, workspace)
    with scope() as session:
        continuation = session.get(TransformationContinuationModel, continuation_id)
        continuation.status = "running"
        continuation.current_node = "create_g12"
        continuation.worker_id = "worker-1"
        session.add(
            StageGatePackageModel(
                id="gate-g09",
                run_id="run-1",
                stage_id="stage-1",
                gate_id="G09",
                gate_version=1,
                status="approved",
                package_artifact_id="artifact-g09",
                package_checksum="sha256:g09",
                artifact_set_checksum="sha256:g09-set",
                plan_id="plan-1",
                plan_version=1,
                stage_plan_id="stage-plan-1",
                stage_plan_checksum="sha256:stage-plan",
                workspace_fingerprint=StageSandboxCopier.fingerprint(workspace),
                expected_state_version=1,
                created_at=NOW,
            )
        )
    flow = TransformerSealingFlow(
        scope=scope,
        stage_service=TransformerStageService(scope=scope, now_provider=lambda: NOW),
        gate_service=StageGateService(),
    )
    flow.create_g12(continuation_id, "worker-1")

    with scope() as session:
        durable = session.get(TransformationContinuationModel, continuation_id)
        gate = session.scalar(
            select(StageGatePackageModel)
            .where(
                StageGatePackageModel.run_id == "run-1",
                StageGatePackageModel.gate_id == "G12",
            )
            .order_by(StageGatePackageModel.gate_version.desc())
            .limit(1)
        )
        assert durable.status == "waiting_gate"
        assert durable.current_node == "wait_g12"
        assert gate.gate_id == "G12"
        assert gate.plan_version == 1
    g12_package = json.loads(
        (artifacts / "04_workflow_state" / "stages" / "stage-1" / "gates" / "g12-package.json").read_text(
            encoding="utf-8"
        )
    )
    assert g12_package["plan_version"] == 1
    assert g12_package["stage_plan_checksum"] == "sha256:stage-plan"
    engine.dispose()
