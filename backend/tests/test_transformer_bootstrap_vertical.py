from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from app.domain.transformation import StageGateDecisionRequest
from app.orchestration.transformer_graph import TransformerOrchestrator, TransformerWorkflow
from app.repositories.models import (
    ActivePlanVersionModel,
    CommandExecutionModel,
    ExecutionProfileModel,
    MigrationRunModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageGatePackageModel,
    TransformationContinuationModel,
)
from app.services.stage_gate_service import StageGateService
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
    engine.dispose()
