from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.repositories.models import (
    Base,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    MigrationStageModel,
    StageExecutionPlanModel,
    TransformationContinuationModel,
)
from app.services.transformation_continuation_service import (
    TransformationContinuationError,
    TransformationContinuationService,
)

NOW = datetime.now(UTC)


def _session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'continuation.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add(
        MigrationRunModel(
            id="run-1",
            status="WAITING_STAGE_PREPARATION",
            run_phase="STAGED_MIGRATION",
            state_version=7,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.add(
        MigrationStageModel(
            id="stage-1",
            run_id="run-1",
            stage_order=1,
            source_version_family="18.x",
            target_version_family="19.x",
            status="PENDING",
            created_at=NOW,
        )
    )
    session.add(
        MigrationPlanModel(
            id="plan-1",
            run_id="run-1",
            idempotency_key="plan",
            request_checksum="sha256:plan-request",
            actor="planner",
            status="approved",
            version=1,
            plan={},
            checksum="sha256:plan",
            artifact_ids=[],
            artifact_checksums={},
            state_version=5,
            event_sequence=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.add(
        StageExecutionPlanModel(
            id="stage-plan-1",
            run_id="run-1",
            migration_plan_id="plan-1",
            stage_id="stage-1",
            idempotency_key="stage-plan",
            request_checksum="sha256:stage-plan-request",
            actor="planner",
            status="approved",
            version=1,
            stage_plan={},
            checksum="sha256:stage-plan",
            artifact_ids=[],
            artifact_checksums={},
            state_version=5,
            event_sequence=2,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.add(
        G06ApprovalModel(
            id="g06-1",
            run_id="run-1",
            gate_id="G06",
            gate_version="g06-v1",
            idempotency_key="g06",
            actor="operator",
            status="approved",
            decision="approve",
            package_checksum="sha256:g06-package",
            artifact_set_checksum="sha256:g06-set",
            plan_checksum="sha256:plan",
            stage_plan_checksum="sha256:stage-plan",
            plan_version=1,
            artifact_ids=[],
            state_version=7,
            event_sequence=3,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.commit()
    return engine, session


def _create(service, session, **overrides):
    values = {
        "run_id": "run-1",
        "stage_id": "stage-1",
        "g06_approval_id": "g06-1",
        "plan_id": "plan-1",
        "plan_checksum": "sha256:plan",
        "stage_plan_id": "stage-plan-1",
        "stage_plan_checksum": "sha256:stage-plan",
        "idempotency_key": "transform-1",
        "now": NOW,
    }
    values.update(overrides)
    return service.ensure_created_in_session(session, **values)


def test_creation_is_idempotent_and_payload_bound(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()

    first = _create(service, session)
    replay = _create(service, session)

    assert replay.id == first.id
    assert session.query(TransformationContinuationModel).count() == 1
    with pytest.raises(TransformationContinuationError, match="different payload"):
        _create(service, session, stage_plan_checksum="sha256:different")
    session.close()
    engine.dispose()


def test_claim_is_single_owner_and_expired_claim_is_recovered(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService(lease_seconds=10)
    continuation = _create(service, session)
    session.commit()

    claimed = service.claim_next(session, "worker-1", NOW)
    assert claimed.id == continuation.id
    assert claimed.worker_id == "worker-1"
    assert claimed.attempt == 0
    assert claimed.claim_count == 1
    assert service.claim_next(session, "worker-2", NOW) is None
    continuation.lease_expires_at = NOW - timedelta(seconds=1)
    session.commit()

    reclaimed = service.claim_next(session, "worker-2", NOW)

    assert reclaimed.id == continuation.id
    assert reclaimed.worker_id == "worker-2"
    assert reclaimed.attempt == 0
    assert reclaimed.claim_count == 2
    session.close()
    engine.dispose()


def test_wait_wake_and_cancel_are_durable(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    continuation = _create(service, session)
    session.commit()
    claimed = service.claim_next(session, "worker-1", NOW)

    service.wait(
        session,
        claimed.id,
        "worker-1",
        status="waiting_gate",
        current_node="wait_g07",
        now=NOW,
    )
    service.wake(session, claimed.id, now=NOW)
    resumed_version = claimed.state_version
    service.wake(session, claimed.id, now=NOW)
    assert claimed.state_version == resumed_version
    service.request_cancel(
        session,
        claimed.id,
        actor="operator",
        idempotency_key="cancel-1",
        expected_state_version=claimed.state_version,
        now=NOW,
    )
    session.commit()
    session.close()

    restarted = sessionmaker(bind=engine, expire_on_commit=False)()
    durable = restarted.get(TransformationContinuationModel, continuation.id)
    assert durable.status == "cancelling"
    assert durable.current_node == "cancel"
    assert durable.cancel_requested_by == "operator"
    restarted.close()
    engine.dispose()
