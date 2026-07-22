"""AMFA-144 parent integration proof for the persisted stage sandbox path."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.stage_workspace import G07Decision, _artifact_set_checksum
from app.repositories.models.base import Base
from app.repositories.models.workflow import ArtifactMetadataModel, MigrationRunModel, SourceSnapshotModel, WorkflowEventModel
from app.repositories.planning_models import ActivePlanVersionModel, MigrationPlanModel, StageExecutionPlanModel
from app.repositories.planning_review_models import G06ApprovalModel as PlanningG06ApprovalModel
from app.repositories.stage_workspace_models import G07ApprovalModel, G07DecisionHistoryModel, StageWorkspaceModel
from app.services.stage_preparation_service import StageApplicationError, StagePreparationApplicationService

def _request(**values):
    defaults = {"expected_state_version": 1, "idempotency_key": "request", "actor": "owner"}
    defaults.update(values)
    return type("Request", (), defaults)()


def _database(tmp_path: Path, name: str):
    database_path = tmp_path / f"{name}.db"
    engine = create_engine(f"sqlite:///{database_path}")
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

    return engine, factory, scope


def _seed(factory):
    session = factory()
    try:
        root = Path(session.bind.url.database).with_suffix("").parent / f"{Path(session.bind.url.database).stem}-workspace-root"
        run_root = root / "run"
        run_root.mkdir(parents=True)
        snapshot_root = run_root / "snapshot"
        snapshot_root.mkdir(parents=True)
        (snapshot_root / "package.json").write_text('{"dependencies": {"@angular/core": "18.2.0"}}', encoding="utf-8")
        (snapshot_root / "snapshot-fingerprint.json").write_text('{"fingerprint": "sha256:src-fp"}', encoding="utf-8")
        (root / "artifacts").mkdir()
        now = datetime.now(UTC)
        run = MigrationRunModel(
            id="run-001", status="WAITING", run_phase="STAGED_MIGRATION", phase_status="running",
            approval_status="not_required", repair_status="not_required", state_version=1,
            source_path=str(snapshot_root), target_output_path=str(root / "output"),
            resolved_output_root=str(root / "output"), artifact_root=str(root / "artifacts"),
            run_root=str(run_root), actor="owner", created_at=now, updated_at=now,
        )
        plan = MigrationPlanModel(
            id="plan-170", run_id="run-001", idempotency_key="plan-170", request_checksum="sha256:req",
            actor="planner", status="approved", version=1, plan={"source": "18.2.0"}, checksum="sha256:plan",
            artifact_ids=[], artifact_checksums={}, state_version=1, event_sequence=1,
            created_at=now, updated_at=now,
        )
        stage_plan = StageExecutionPlanModel(
            id="stage-plan-170", run_id="run-001", migration_plan_id=plan.id, stage_id="18-to-19",
            idempotency_key="stage-plan-170", request_checksum="sha256:req", actor="planner", status="approved",
            version=1, stage_plan={"stage_id": "18-to-19", "source_family": "angular_18", "target_family": "angular_19",
                                  "source_exact": "18.2.0", "target_exact": "19.0.0", "execution_profile_id": "npm-ci",
                                  "commands": {"prepare": ["npm ci"]}}, checksum="sha256:stage-plan",
            artifact_ids=[], artifact_checksums={}, state_version=1, event_sequence=1,
            created_at=now, updated_at=now,
        )
        snapshot = SourceSnapshotModel(
            id="snapshot-170", run_id="run-001", idempotency_key="snapshot-170", actor="operator", status="created",
            source_path=str(snapshot_root), snapshot_path=str(snapshot_root), fingerprint="sha256:src-fp",
            policy_version="snapshot-v1", file_count=1, total_size_bytes=(snapshot_root / "package.json").stat().st_size,
            exclusions=[], git_metadata={}, artifact_ids=[], state_version=1, event_sequence=1,
            created_at=now, updated_at=now,
        )
        session.add_all([run, plan, stage_plan, snapshot])
        session.add_all([
            ActivePlanVersionModel(id="active-plan-170", run_id="run-001", scope="migration", migration_plan_id=plan.id,
                                   stage_plan_id=None, version=1, state_version=1, updated_at=now),
            ActivePlanVersionModel(id="active-stage-170", run_id="run-001", scope="18-to-19", migration_plan_id=plan.id,
                                   stage_plan_id=stage_plan.id, version=1, state_version=1, updated_at=now),
            PlanningG06ApprovalModel(id="g06-170", run_id="run-001", gate_id="G06", gate_version="g06-v1",
                                     idempotency_key="g06-170", actor="reviewer", status="approved", decision="approve",
                                     package_checksum="sha256:g06", artifact_set_checksum=_artifact_set_checksum([]),
                                     plan_checksum=plan.checksum, stage_plan_checksum=stage_plan.checksum, plan_version=1,
                                     workspace_fingerprint=snapshot.fingerprint, artifact_ids=[], comment=None,
                                     stale_reason=None, state_version=1, event_sequence=1, created_at=now, updated_at=now),
        ])
        session.flush()
        session.commit()
    finally:
        session.close()


def _service(scope, now):
    service = StagePreparationApplicationService(session_scope_factory=scope, now_provider=lambda: now)
    service._authoritative_snapshot_fingerprint = lambda snapshot: "sha256:src-fp"
    return service


def test_amfa144_persisted_prepare_g07_sandbox_and_restart_proof(tmp_path):
    """Exercise authority, fail-closed gates, evidence, replay, and restart boundaries."""
    now = datetime.now(UTC)

    engine, factory, scope = _database(tmp_path, "approved")
    try:
        _seed(factory)
        first = _service(scope, now)
        prepared = first.prepare_stage("run-001", _request(
            expected_state_version=1, idempotency_key="parent-prepare", stage_key="18-to-19",
            source_version_family="angular_18", target_version_family="angular_19", plan_version="v1",
        ))
        assert prepared.plan["stage_key"] == "18-to-19"
        assert prepared.plan["toolchain_profile"] == "npm-ci"
        stage_id = prepared.stage_id

        for status in ("pending", "modification_requested", "rejected", "stale"):
            with scope() as session:
                gate = session.scalar(select(G07ApprovalModel).where(G07ApprovalModel.stage_id == stage_id))
                gate.status = status
                gate.decision = status
            with pytest.raises(StageApplicationError, match="G07_APPROVAL_REQUIRED"):
                first.create_sandbox("run-001", stage_id, _request(
                    expected_state_version=prepared.state_version,
                    idempotency_key=f"blocked-{status}",
                ))

        with scope() as session:
            gate = session.scalar(select(G07ApprovalModel).where(G07ApprovalModel.stage_id == stage_id))
            gate.status = "pending"
            gate.decision = None
            gate.stale_reason = None
        decision_request = _request(
            gate_id="G07", stage_id=stage_id, expected_state_version=prepared.state_version,
            idempotency_key="parent-decision", decision=G07Decision.APPROVED, comment=None,
        )
        approved = first.decide_g07("run-001", stage_id, decision_request)
        replayed_decision = first.decide_g07("run-001", stage_id, decision_request)
        assert approved.status == "approved"
        assert replayed_decision.idempotent_replay is True
        with pytest.raises(StageApplicationError, match="IDEMPOTENCY_PAYLOAD_MISMATCH"):
            first.decide_g07("run-001", stage_id, _request(
                gate_id="G07", stage_id=stage_id, expected_state_version=prepared.state_version,
                idempotency_key="parent-decision", decision=G07Decision.REJECTED, comment="conflict",
            ))

        sandbox_request = _request(
            expected_state_version=approved.state_version, idempotency_key="parent-sandbox",
        )
        created = first.create_sandbox("run-001", stage_id, sandbox_request)
        duplicate = first.create_sandbox("run-001", stage_id, sandbox_request)
        assert created.status == "sandbox_ready"
        assert duplicate.idempotent_replay is True
        assert duplicate.sandbox_path == created.sandbox_path

        with scope() as session:
            run = session.get(MigrationRunModel, "run-001")
            assert Path(created.sandbox_path).is_relative_to(Path(run.run_root).resolve())

        with pytest.raises(StageApplicationError, match="RUN_NOT_AUTHORIZED"):
            first.create_sandbox("run-001", stage_id, _request(
                expected_state_version=approved.state_version, idempotency_key="parent-sandbox", actor="foreign",
            ))

        del first
        second = _service(scope, now)
        restarted = second.create_sandbox("run-001", stage_id, sandbox_request)
        assert restarted.idempotent_replay is True
        with scope() as session:
            workspace = session.scalar(select(StageWorkspaceModel).where(StageWorkspaceModel.stage_id == stage_id))
            gate = session.scalar(select(G07ApprovalModel).where(G07ApprovalModel.stage_id == stage_id))
            history = session.scalars(select(G07DecisionHistoryModel).where(G07DecisionHistoryModel.stage_id == stage_id)).all()
            artifacts = session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.stage_id == stage_id)).all()
            events = session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == "run-001").order_by(WorkflowEventModel.sequence)).all()
            source = session.get(MigrationRunModel, "run-001").source_path
            assert gate.status == "approved"
            assert workspace.copy_status == "verified"
            assert workspace.source_fingerprint == "sha256:src-fp"
            assert len(history) == 1
            artifact_paths = {artifact.relative_path for artifact in artifacts}
            assert any("sandbox_copy_report" in path for path in artifact_paths)
            assert any("sandbox_verification" in path for path in artifact_paths)
            event_names = [event.event_type for event in events]
            assert event_names.index("STAGE_CREATED") < event_names.index("STAGE_PLAN_LOCKED") < event_names.index("G07_APPROVED") < event_names.index("STAGE_SANDBOX_READY")
            assert event_names.count("STAGE_SANDBOX_READY") == 1
            assert Path(source, "package.json").read_text(encoding="utf-8") == '{"dependencies": {"@angular/core": "18.2.0"}}'
    finally:
        engine.dispose()

    engine, factory, scope = _database(tmp_path, "stale")
    try:
        _seed(factory)
        service = _service(scope, now)
        prepared = service.prepare_stage("run-001", _request(
            expected_state_version=1, idempotency_key="stale-prepare", stage_key="18-to-19",
            source_version_family="angular_18", target_version_family="angular_19", plan_version="v1",
        ))
        approved = service.decide_g07("run-001", prepared.stage_id, _request(
            gate_id="G07", stage_id=prepared.stage_id, expected_state_version=prepared.state_version,
            idempotency_key="stale-decision", decision=G07Decision.APPROVED, comment=None,
        ))
        with scope() as session:
            stage_plan = session.get(StageExecutionPlanModel, "stage-plan-170")
            stage_plan.stage_plan = {**stage_plan.stage_plan, "execution_profile_id": "changed-profile"}
        with pytest.raises(StageApplicationError, match="G07_STALE"):
            service.create_sandbox("run-001", prepared.stage_id, _request(
                expected_state_version=approved.state_version, idempotency_key="stale-sandbox",
            ))
        with scope() as session:
            assert session.scalar(select(StageWorkspaceModel).where(StageWorkspaceModel.stage_id == prepared.stage_id)) is None
            gate = session.scalar(select(G07ApprovalModel).where(G07ApprovalModel.stage_id == prepared.stage_id))
            assert gate.status == "stale"
    finally:
        engine.dispose()
