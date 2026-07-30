from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.orchestration.transformer_sealing_flow import TransformerSealingFlow
from app.repositories.models import (
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    StageGatePackageModel,
    TransformationContinuationModel,
)
from app.services.transformation_continuation_service import TransformationContinuationService
from tests.test_transformation_continuation import _create, _session


NOW = datetime(2026, 7, 30, tzinfo=UTC)


def test_completion_requires_every_route_stage_and_governance_gate(tmp_path: Path):
    engine, seed = _session(tmp_path)
    seed.get(MigrationPlanModel, "plan-1").plan = {
        "route": ["stage-1"],
        "target_family": "angular-19.x",
        "catalogue_version": "catalog-v1",
    }
    seed.get(MigrationStageModel, "stage-1").status = "sealed"
    continuation = _create(TransformationContinuationService(), seed)
    continuation.status = "running"
    continuation.current_node = "complete_run"
    continuation.worker_id = "worker-1"
    for index, gate_id in enumerate(("G07", "G08", "G09", "G12"), start=1):
        seed.add(
            StageGatePackageModel(
                id=f"gate-{gate_id}",
                run_id="run-1",
                stage_id="stage-1",
                gate_id=gate_id,
                gate_version=1,
                status="approved",
                package_artifact_id=f"artifact-{gate_id}",
                package_checksum=f"sha256:{gate_id}",
                artifact_set_checksum=f"sha256:set-{gate_id}",
                plan_id="plan-1",
                plan_version=1,
                stage_plan_id="stage-plan-1",
                stage_plan_checksum="sha256:stage-plan",
                workspace_fingerprint="sha256:workspace",
                expected_state_version=index,
                created_at=NOW,
            )
        )
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

    TransformerSealingFlow(
        scope=scope, stage_service=None, gate_service=None
    ).complete(continuation_id, "worker-1")

    with scope() as session:
        durable = session.get(TransformationContinuationModel, continuation_id)
        run = session.get(MigrationRunModel, "run-1")
        assert durable.status == "completed"
        assert durable.current_node == "terminal"
        assert run.status == "COMPLETED"
    engine.dispose()
