from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.repositories.models import (
    ActivePlanVersionModel,
    Base,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    StageExecutionPlanModel,
    MigrationStageModel,
    StageStepModel,
    StageWorkspaceBindingModel,
    ArtifactMetadataModel,
    CommandAuthorizationAuditModel,
    CommandExecutionModel,
    ExecutionProfileModel,
    WorkflowEventModel,
    TransformationContinuationModel,
)
from app.services.stage_execution_application_service import StageExecutionApplicationService
from app.services.stage_preparation_application_service import StagePreparationApplicationService


def test_start_prepares_and_persists_the_stage_before_returning(tmp_path: Path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)
    run_root = tmp_path / "run"
    baseline = run_root / "baseline"
    stage_root = run_root / "stage-sandbox"
    artifact_root = run_root / "artifacts"
    baseline.mkdir(parents=True)
    (baseline / "package.json").write_text("{}", encoding="utf-8")
    artifact_set_checksum = StageExecutionApplicationService.aggregate_artifact_checksum({})
    stage_plan_checksum = "sha256:" + "2" * 64
    plan_checksum = "sha256:" + "3" * 64
    stage_id = "stage-18-to-19"
    plan_id = "plan-run-1-v1"
    stage_plan_id = "stage-plan-run-1-stage-18-to-19-v1"
    command_ref = {
        "command_id": "npm-ci-bootstrap",
        "template_id": "tpl-npm-ci",
        "template_version": 1,
        "executable": "npm",
        "arguments": ["ci"],
        "working_directory_alias": "STAGE_WORKSPACE_STAGE_18_TO_19",
        "timeout_seconds": 3600,
        "network_profile": "approved-registries-only",
    }
    stage_plan = {
        "stage_plan_id": stage_plan_id,
        "stage_id": stage_id,
        "plan_version": 1,
        "execution_profile_id": "profile-1",
        "commands": {name: [command_ref] for name in (
            "bootstrap_install", "angular_update", "target_version_check", "final_install", "builds", "tests", "lint"
        )},
    }

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
        session.add(MigrationRunModel(
            id="run-1", status="WAITING_STAGE_PREPARATION", run_phase="STAGED_MIGRATION",
            phase_status="waiting_approval", approval_status="approved", repair_status="not_required",
            state_version=4, actor="operator", run_root=str(run_root), artifact_root=str(artifact_root),
            workspace_aliases={"BASELINE_SANDBOX": str(baseline), "STAGE_SANDBOX": str(stage_root)},
            created_at=now, updated_at=now,
        ))
        session.add(MigrationPlanModel(
            id=plan_id, run_id="run-1", idempotency_key="plan-1", request_checksum="sha256:" + "4" * 64,
            actor="operator", status="approved", version=1, plan={}, checksum=plan_checksum,
            artifact_ids=[], artifact_checksums={}, state_version=4, event_sequence=1,
            created_at=now, updated_at=now,
        ))
        session.add(StageExecutionPlanModel(
            id=stage_plan_id, run_id="run-1", migration_plan_id=plan_id, stage_id=stage_id,
            idempotency_key="stage-plan-1", request_checksum="sha256:" + "5" * 64, actor="operator",
            status="approved", version=1, stage_plan=stage_plan, checksum=stage_plan_checksum,
            artifact_ids=[], artifact_checksums={}, state_version=4, event_sequence=1,
            created_at=now, updated_at=now,
        ))
        session.add(ActivePlanVersionModel(
            id="active-run-1-stage", run_id="run-1", scope=stage_id, migration_plan_id=plan_id,
            stage_plan_id=stage_plan_id, version=1, state_version=4, updated_at=now,
        ))
        session.add(G06ApprovalModel(
            id="g06-run-1", run_id="run-1", gate_id="G06", gate_version="g06-v1",
            idempotency_key="gate:g06", actor="operator", status="approved", decision="approve",
            package_checksum="sha256:" + "6" * 64, artifact_set_checksum=artifact_set_checksum,
            plan_checksum=plan_checksum, stage_plan_checksum=stage_plan_checksum, plan_version=1,
            workspace_fingerprint=None, artifact_ids=[], state_version=4, event_sequence=2,
            created_at=now, updated_at=now,
        ))
        session.add(ExecutionProfileModel(
            id="execution-profile-1", run_id="run-1", idempotency_key="profile-1",
            request_checksum="sha256:" + "7" * 64, policy_version="profile-v1", status="selected",
            source_angular_exact="18.2.0", selected_profile_id="profile-1",
            selected_checksum="sha256:" + "8" * 64, profiles=[], blockers=[], guidance=[], artifact_ids=[],
            state_version=4, event_sequence=1, created_at=now, updated_at=now,
        ))
        session.add(MigrationStageModel(
            id=stage_id,
            run_id="run-1",
            stage_order=1,
            source_version_family="angular-18.x",
            target_version_family="angular-19.x",
            source_version_detected="18.2.0",
            target_version_resolved="19.2.0",
            source_angular_version="18.2.0",
            target_angular_version="19.2.0",
            status="planned",
            created_at=now,
        ))
        session.add(TransformationContinuationModel(
            id="transform-run-1",
            run_id="run-1",
            current_stage_id=stage_id,
            thread_id="transform:run-1",
            status="waiting_gate",
            current_node="wait_g07",
            g06_approval_id="g06-run-1",
            plan_id=plan_id,
            plan_checksum=plan_checksum,
            stage_plan_id=stage_plan_id,
            stage_plan_checksum=stage_plan_checksum,
            attempt=0,
            max_attempts=3,
            wake_sequence=0,
            idempotency_key="transform-1",
            request_checksum="sha256:transform",
            state_version=1,
            created_at=now,
            updated_at=now,
        ))
        session.commit()
        planned_created_at = session.get(MigrationStageModel, stage_id).created_at
    service = StageExecutionApplicationService(scope=scope, preparation=StagePreparationApplicationService())

    request = type("Request", (), {
        "expected_state_version": 4,
        "idempotency_key": "stage-start-1",
        "artifact_set_checksum": artifact_set_checksum,
        "plan_checksum": plan_checksum,
        "stage_plan_checksum": stage_plan_checksum,
        "workspace_fingerprint": None,
    })()
    result = service.start("run-1", stage_id, request, "operator")
    replay = service.start("run-1", stage_id, request, "operator")

    assert result["status"] == "STAGE_CREATED"
    assert replay["idempotent_replay"] is True
    with factory() as session:
        stage = session.get(MigrationStageModel, stage_id)
        assert stage is not None
        assert stage.status == "planned"
        assert stage.stage_order == 1
        assert stage.created_at == planned_created_at
        assert session.query(StageStepModel).filter(StageStepModel.stage_id == stage_id).count() == 0
        run = session.get(MigrationRunModel, "run-1")
        assert "STAGE_WORKSPACE_STAGE_18_TO_19" not in run.workspace_aliases
        assert session.query(StageWorkspaceBindingModel).count() == 0
        assert session.query(ArtifactMetadataModel).filter_by(stage_id=stage_id).count() == 0
        assert session.query(CommandAuthorizationAuditModel).count() == 0
        assert session.query(CommandExecutionModel).count() == 0
        continuation = session.get(TransformationContinuationModel, "transform-run-1")
        assert continuation.status == "queued"
        assert continuation.wake_sequence == 1
        event_types = [event.event_type for event in session.query(WorkflowEventModel).filter_by(run_id="run-1").order_by(WorkflowEventModel.sequence)]
        assert event_types[-1:] == ["TRANSFORMATION_CONTINUATION_RESUMED"]
