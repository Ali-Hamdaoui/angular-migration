from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.domain.contracts import WorkflowEventType
from app.repositories.models import (
    Base,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    RuntimeCertificationModel,
    StageExecutionPlanModel,
    StageRuntimeBindingModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.repositories.session import create_database_engine
from app.services.ng_update_governance_service import NgUpdateGovernanceService
from app.services.runtime_certification_service import RuntimeCertificationService
from app.services.transformer_stage_service import TransformerStageService


NOW = datetime(2026, 8, 23, tzinfo=UTC)
RUN_ID = "run-cert-test"
STAGE_ID = "angular-11-to-12--teststage"


def _seed(tmp_path: Path, run_mode: str):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'cert.db'}", sqlite_wal_enabled=False)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    artifact_root = tmp_path / "artifacts" / RUN_ID
    artifact_root.mkdir(parents=True, exist_ok=True)

    def scope():
        from contextlib import contextmanager

        @contextmanager
        def managed():
            session = sessions()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        return managed()

    plan_checksum = "sha256:" + "1" * 64
    stage_plan_checksum = "sha256:" + "2" * 64
    workspace_fingerprint = "sha256:" + "f" * 64
    with sessions.begin() as session:
        session.add_all(
            [
                MigrationRunModel(
                    id=RUN_ID,
                    status="STAGE_CREATED",
                    run_phase="TRANSFORMATION",
                    phase_status="running",
                    approval_status="approved",
                    repair_status="not_required",
                    state_version=10,
                    actor="control-tower",
                    artifact_root=str(artifact_root),
                    run_policy_snapshot={"run_mode": run_mode},
                    created_at=NOW,
                    updated_at=NOW,
                ),
                MigrationStageModel(
                    id=STAGE_ID,
                    run_id=RUN_ID,
                    stage_order=1,
                    source_version_family="angular-11.x",
                    target_version_family="angular-12.x",
                    source_angular_version="11.0.4",
                    target_angular_version="12.2.17",
                    status="prepared",
                    created_at=NOW,
                ),
                MigrationPlanModel(
                    id="plan-1",
                    run_id=RUN_ID,
                    idempotency_key="plan-1",
                    request_checksum=plan_checksum,
                    actor="control-tower",
                    status="approved_for_execution",
                    version=1,
                    plan={},
                    checksum=plan_checksum,
                    state_version=5,
                    event_sequence=5,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                StageExecutionPlanModel(
                    id="stage-plan-1",
                    run_id=RUN_ID,
                    migration_plan_id="plan-1",
                    stage_id=STAGE_ID,
                    idempotency_key="plan-1",
                    request_checksum=plan_checksum,
                    actor="control-tower",
                    status="approved_for_execution",
                    version=1,
                    stage_plan={},
                    checksum=stage_plan_checksum,
                    state_version=6,
                    event_sequence=6,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                G06ApprovalModel(
                    id="g06-1",
                    run_id=RUN_ID,
                    gate_id="G06",
                    gate_version="g06-v1",
                    idempotency_key="g06-1",
                    actor="control-tower",
                    status="approved",
                    decision="approve",
                    package_checksum="sha256:" + "3" * 64,
                    artifact_set_checksum="sha256:" + "4" * 64,
                    plan_checksum=plan_checksum,
                    stage_plan_checksum=stage_plan_checksum,
                    workspace_fingerprint=workspace_fingerprint,
                    plan_version=1,
                    state_version=9,
                    event_sequence=9,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                TransformationContinuationModel(
                    id="continuation-1",
                    run_id=RUN_ID,
                    current_stage_id=STAGE_ID,
                    thread_id="thread-1",
                    status="waiting_gate",
                    current_node="wait_g07",
                    g06_approval_id="g06-1",
                    plan_id="plan-1",
                    plan_checksum=plan_checksum,
                    stage_plan_id="stage-plan-1",
                    stage_plan_checksum=stage_plan_checksum,
                    attempt=0,
                    max_attempts=3,
                    wake_sequence=0,
                    idempotency_key="continuation-1",
                    request_checksum=plan_checksum,
                    state_version=10,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                StageWorkspaceBindingModel(
                    id="binding-1",
                    run_id=RUN_ID,
                    stage_id=STAGE_ID,
                    alias="STAGE_WORKSPACE_" + STAGE_ID.upper().replace("-", "_"),
                    workspace_path=str(tmp_path / "workspace"),
                    workspace_fingerprint=workspace_fingerprint,
                    active=True,
                    created_at=NOW,
                ),
                *[
                    StageRuntimeBindingModel(
                        id=f"binding-{kind}",
                        run_id=RUN_ID,
                        stage_id=STAGE_ID,
                        kind=kind,
                        runtime_id="node12",
                        version_exact=version,
                        sha256=char * 64,
                        resolved_path=f"C:/runtimes/node12/{kind}.cmd",
                        source="synthetic",
                        status="bound",
                        created_at=NOW,
                    )
                    for kind, version, char in (
                        ("node", "12.22.12", "a"),
                        ("npm", "8.19.4", "b"),
                        ("npx", "8.19.4", "c"),
                    )
                ],
            ]
        )
    return sessions, scope, artifact_root


def _service(scope):
    return TransformerStageService(scope=scope, now_provider=lambda: NOW)


def test_qualification_stage_preparation_creates_promoted_certification(tmp_path):
    sessions, scope, _ = _seed(tmp_path, "QUALIFICATION")

    result = _service(scope).ensure_qualification_certification(RUN_ID, STAGE_ID)

    assert result is not None
    with sessions() as session:
        rows = session.query(RuntimeCertificationModel).filter_by(stage_id=STAGE_ID).all()
        assert len(rows) == 1
        assert rows[0].certified is True
        assert rows[0].allowed is True
        assert rows[0].classification == "EXACT_CERTIFIED"
        assert rows[0].certified_against == "catalog-v4"
        assert rows[0].node_version == "12.22.12"
        assert rows[0].npm_version == "8.19.4"
        events = {e.event_type for e in session.query(WorkflowEventModel).all()}
        assert {
            WorkflowEventType.RUNTIME_CERTIFICATION_REQUESTED.value,
            WorkflowEventType.RUNTIME_QUALIFICATION_COMPLETED.value,
            WorkflowEventType.RUNTIME_CERTIFICATION_PROMOTED.value,
        } <= events


def test_production_stage_preparation_creates_no_certification(tmp_path):
    sessions, scope, _ = _seed(tmp_path, "PRODUCTION")

    result = _service(scope).ensure_qualification_certification(RUN_ID, STAGE_ID)

    assert result is None
    with sessions() as session:
        assert session.query(RuntimeCertificationModel).filter_by(stage_id=STAGE_ID).count() == 0
        events = {e.event_type for e in session.query(WorkflowEventModel).all()}
        assert WorkflowEventType.RUNTIME_CERTIFICATION_REQUESTED.value not in events


def test_f14_authorization_passes_after_promotion(tmp_path):
    sessions, scope, _ = _seed(tmp_path, "QUALIFICATION")
    _service(scope).ensure_qualification_certification(RUN_ID, STAGE_ID)

    class _FakeStageRuntime:
        def stage_version_families(self, stage_id):
            return ("angular-11.x", "angular-12.x")

    certification = RuntimeCertificationService(
        stage_runtime_service=_FakeStageRuntime(),
        session_scope_factory=scope,
        now_provider=lambda: NOW,
    )
    governance = NgUpdateGovernanceService(certification_service=certification)

    decision = certification.enforce_stage_certification(STAGE_ID)
    assert decision.certified is True

    authorization = governance.authorize_update(11, 12, stage_id=STAGE_ID)
    assert authorization.allowed is True
    assert authorization.certified is True