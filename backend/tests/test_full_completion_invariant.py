from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.orchestration.transformer_sealing_flow import TransformerSealingFlow
from app.repositories.models import (
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    RepairAttemptModel,
    StageGatePackageModel,
    TransformationContinuationModel,
)
from app.services.transformation_continuation_service import TransformationContinuationService
from tests.test_transformation_continuation import _create, _session


NOW = datetime(2026, 7, 30, tzinfo=UTC)


def _add_approved_gate(seed, gate_id: str, index: int) -> None:
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


def _completion_scope(engine):
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

    return scope


def _prepare_repair_completion(seed, *, validation_checksum: str | None):
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
    for index, gate_id in enumerate(("G07", "G08", "G10", "G11"), start=1):
        _add_approved_gate(seed, gate_id, index)
    older = RepairAttemptModel(
        id="repair-old",
        run_id="run-1",
        stage_id="stage-1",
        attempt_number=3,
        state_version=1,
        status="revalidating_affected",
        risk_level="medium",
        failure_evidence_artifact_id="artifact-old-failure-evidence",
        failure_evidence_checksum="sha256:old-failure-evidence",
        failure_route_artifact_id="artifact-old-failure-route",
        failure_route_checksum="sha256:old-failure-route",
        context_pack_artifact_id="artifact-old-context",
        context_pack_checksum="sha256:old-context",
        proposal_artifact_id="artifact-old-proposal",
        proposal_checksum="sha256:old-proposal",
        review_artifact_id="artifact-old-review",
        review_checksum="sha256:old-review",
        apply_ledger_artifact_id="artifact-old-ledger",
        apply_ledger_checksum="sha256:old-ledger",
        validation_summary_artifact_id="artifact-old-validation",
        validation_summary_checksum="sha256:old-validation",
        created_at=NOW,
        updated_at=NOW,
    )
    replacement = RepairAttemptModel(
        id="repair-replacement",
        run_id="run-1",
        stage_id="stage-1",
        attempt_number=6,
        state_version=1,
        status="validation_passed",
        risk_level="medium",
        proposal_artifact_id="artifact-replacement-proposal",
        proposal_checksum="sha256:replacement-proposal",
        review_artifact_id="artifact-replacement-review",
        review_checksum="sha256:replacement-review",
        g10_gate_package_id="gate-G10",
        apply_ledger_artifact_id="artifact-replacement-ledger",
        apply_ledger_checksum="sha256:replacement-ledger",
        pre_fingerprint="sha256:pre",
        post_fingerprint="sha256:post",
        validation_summary_artifact_id="artifact-replacement-validation",
        validation_summary_checksum=validation_checksum,
        created_at=NOW,
        updated_at=NOW,
        completed_at=NOW,
    )
    seed.add_all((older, replacement))
    seed.commit()
    return continuation.id, older, replacement


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


def test_completion_supersedes_older_active_repair_with_complete_replacement_evidence(
    tmp_path: Path,
):
    engine, seed = _session(tmp_path)
    continuation_id, older, replacement = _prepare_repair_completion(
        seed, validation_checksum="sha256:replacement-validation"
    )
    historical_bindings = (
        older.failure_evidence_artifact_id,
        older.failure_evidence_checksum,
        older.failure_route_artifact_id,
        older.failure_route_checksum,
        older.context_pack_artifact_id,
        older.context_pack_checksum,
        older.proposal_artifact_id,
        older.proposal_checksum,
        older.review_artifact_id,
        older.review_checksum,
        older.apply_ledger_artifact_id,
        older.apply_ledger_checksum,
        older.validation_summary_artifact_id,
        older.validation_summary_checksum,
    )
    replacement_bindings = (
        replacement.status,
        replacement.proposal_artifact_id,
        replacement.proposal_checksum,
        replacement.review_artifact_id,
        replacement.review_checksum,
        replacement.g10_gate_package_id,
        replacement.apply_ledger_artifact_id,
        replacement.apply_ledger_checksum,
        replacement.validation_summary_artifact_id,
        replacement.validation_summary_checksum,
        replacement.post_fingerprint,
    )
    seed.close()
    scope = _completion_scope(engine)

    TransformerSealingFlow(
        scope=scope, stage_service=None, gate_service=None
    ).complete(continuation_id, "worker-1")

    with scope() as session:
        durable = session.get(TransformationContinuationModel, continuation_id)
        durable_older = session.get(RepairAttemptModel, "repair-old")
        durable_replacement = session.get(RepairAttemptModel, "repair-replacement")
        assert durable.status == "completed"
        assert durable.current_node == "terminal"
        assert durable_older.status == "superseded"
        assert durable_older.completed_at is not None
        assert (
            durable_older.failure_evidence_artifact_id,
            durable_older.failure_evidence_checksum,
            durable_older.failure_route_artifact_id,
            durable_older.failure_route_checksum,
            durable_older.context_pack_artifact_id,
            durable_older.context_pack_checksum,
            durable_older.proposal_artifact_id,
            durable_older.proposal_checksum,
            durable_older.review_artifact_id,
            durable_older.review_checksum,
            durable_older.apply_ledger_artifact_id,
            durable_older.apply_ledger_checksum,
            durable_older.validation_summary_artifact_id,
            durable_older.validation_summary_checksum,
        ) == historical_bindings
        assert (
            durable_replacement.status,
            durable_replacement.proposal_artifact_id,
            durable_replacement.proposal_checksum,
            durable_replacement.review_artifact_id,
            durable_replacement.review_checksum,
            durable_replacement.g10_gate_package_id,
            durable_replacement.apply_ledger_artifact_id,
            durable_replacement.apply_ledger_checksum,
            durable_replacement.validation_summary_artifact_id,
            durable_replacement.validation_summary_checksum,
            durable_replacement.post_fingerprint,
        ) == replacement_bindings
    engine.dispose()


def test_completion_keeps_older_repair_active_when_replacement_evidence_is_incomplete(
    tmp_path: Path,
):
    engine, seed = _session(tmp_path)
    continuation_id, _, _ = _prepare_repair_completion(
        seed, validation_checksum=None
    )
    seed.close()
    scope = _completion_scope(engine)

    TransformerSealingFlow(
        scope=scope, stage_service=None, gate_service=None
    ).complete(continuation_id, "worker-1")

    with scope() as session:
        durable = session.get(TransformationContinuationModel, continuation_id)
        durable_older = session.get(RepairAttemptModel, "repair-old")
        assert durable.status == "blocked"
        assert durable.last_error_code == "COMPLETION_WORK_REMAINS"
        assert durable_older.status == "revalidating_affected"
        assert durable_older.completed_at is None
    engine.dispose()
