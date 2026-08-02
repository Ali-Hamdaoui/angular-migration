from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.domain.contracts import RunStatus, StageStatus, StepStatus, WorkflowEventType
from app.repositories.models import Base, MigrationRunModel, MigrationStageModel, StageStepModel, WorkflowEventModel
from app.repositories.session import create_database_engine
from app.state import (
    IllegalRunTransitionError,
    LeaseRequiredError,
    IdempotencyPayloadMismatchError,
    ResumeRejectedError,
    StaleStateVersionError,
    StateTransitionService,
    TransitionRequest,
)


def _session(tmp_path: Path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'state-transitions.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    return engine, session


def _create_run(session, *, status: str = "CREATED") -> None:
    now = datetime.now(UTC)
    session.add(
        MigrationRunModel(
            id="run-001",
            status=status,
            run_phase="FEASIBILITY_PLANNING",
            state_version=1,
            source_version_family="18.x",
            target_version_family="21.x",
            source_version_detected="18.2.x",
            target_version_resolved=None,
            source_angular_version="18.x",
            target_angular_version="21.x",
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()


def _transition_request(**overrides) -> TransitionRequest:
    data = {
        "run_id": "run-001",
        "idempotency_key": "transition-001",
        "expected_state_version": 1,
        "event_type": WorkflowEventType.RUN_STATE_CHANGED,
        "next_run_status": RunStatus.RUNNING,
        "actor": "tester",
        "reason": "start mock run",
        "occurred_at": datetime.now(UTC),
    }
    data.update(overrides)
    return TransitionRequest(**data)


def test_accepted_transition_increments_state_and_writes_ordered_event(tmp_path: Path) -> None:
    engine, session = _session(tmp_path)
    _create_run(session)
    service = StateTransitionService(session)

    result = service.apply_transition(_transition_request())
    session.commit()

    run = session.get(MigrationRunModel, "run-001")
    event = session.query(WorkflowEventModel).one()
    assert run.status == "RUNNING"
    assert run.state_version == 2
    assert result.event_sequence == 1
    assert event.sequence == 1
    assert event.idempotency_key == "transition-001"
    assert event.payload["previous_state_version"] == 1
    assert event.payload["next_state_version"] == 2
    session.close()
    engine.dispose()


def test_stale_expected_state_version_is_rejected_without_event(tmp_path: Path) -> None:
    engine, session = _session(tmp_path)
    _create_run(session)
    service = StateTransitionService(session)

    with pytest.raises(StaleStateVersionError):
        service.apply_transition(_transition_request(expected_state_version=99))

    assert session.get(MigrationRunModel, "run-001").state_version == 1
    assert session.query(WorkflowEventModel).count() == 0
    session.close()
    engine.dispose()


def test_duplicate_idempotency_key_returns_existing_result(tmp_path: Path) -> None:
    engine, session = _session(tmp_path)
    _create_run(session)
    service = StateTransitionService(session)

    request = _transition_request()
    first = service.apply_transition(request)
    second = service.apply_transition(request)

    assert second.idempotent_replay is True
    assert second.event_id == first.event_id
    assert session.query(WorkflowEventModel).count() == 1
    assert session.get(MigrationRunModel, "run-001").status == "RUNNING"
    session.close()
    engine.dispose()


def test_duplicate_idempotency_key_rejects_different_payload(tmp_path: Path) -> None:
    engine, session = _session(tmp_path)
    _create_run(session)
    service = StateTransitionService(session)

    service.apply_transition(_transition_request())

    with pytest.raises(IdempotencyPayloadMismatchError):
        service.apply_transition(_transition_request(next_run_status=RunStatus.FAILED))

    assert session.query(WorkflowEventModel).count() == 1
    assert session.get(MigrationRunModel, "run-001").status == "RUNNING"
    session.close()
    engine.dispose()


def test_stage_status_transition_mutates_authoritative_stage(tmp_path: Path) -> None:
    engine, session = _session(tmp_path)
    _create_run(session)
    now = datetime.now(UTC)
    session.add(
        MigrationStageModel(
            id="stage-001",
            run_id="run-001",
            stage_order=1,
            status="PENDING",
            created_at=now,
        )
    )
    session.flush()

    StateTransitionService(session).apply_transition(
        _transition_request(
            next_run_status=None,
            event_type=WorkflowEventType.STAGE_STATE_CHANGED,
            stage_id="stage-001",
            next_stage_status=StageStatus.PREPARING,
        )
    )

    assert session.get(MigrationStageModel, "stage-001").status == "preparing"
    session.close()
    engine.dispose()


def test_only_one_session_consumes_expected_state_version(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'concurrent-state-transitions.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    seed = factory()
    _create_run(seed)
    seed.commit()
    seed.close()
    first = factory()
    second = factory()
    first_run = first.get(MigrationRunModel, "run-001")
    second_run = second.get(MigrationRunModel, "run-001")
    assert first_run.state_version == second_run.state_version == 1

    StateTransitionService(first).apply_transition(_transition_request(idempotency_key="first"))
    first.commit()

    with pytest.raises(StaleStateVersionError):
        StateTransitionService(second).apply_transition(_transition_request(idempotency_key="second"))

    assert second.query(WorkflowEventModel).count() == 1
    first.close()
    second.close()
    engine.dispose()


def test_worker_lease_prevents_stale_step_completion(tmp_path: Path) -> None:
    engine, session = _session(tmp_path)
    now = datetime.now(UTC)
    _create_run(session, status="RUNNING")
    session.add(
        StageStepModel(
            id="step-001",
            run_id="run-001",
            stage_id=None,
            name="mock_step",
            status="RUNNING",
            component_type="deterministic_worker",
            attempt_id="attempt-001",
            idempotency_key=None,
            started_at=now,
            completed_at=None,
        )
    )
    session.flush()
    service = StateTransitionService(session, lease_seconds=60)

    with pytest.raises(LeaseRequiredError):
        service.apply_transition(
            _transition_request(
                idempotency_key="step-complete-no-lease",
                event_type=WorkflowEventType.STEP_STATE_CHANGED,
                next_run_status=None,
                next_step_status=StepStatus.PASSED,
                step_id="step-001",
                worker_id="worker-stale",
                occurred_at=now,
            )
        )

    service.acquire_lease(run_id="run-001", worker_id="worker-001", lease_owner="mock", now=now)
    result = service.apply_transition(
        _transition_request(
            idempotency_key="step-complete-with-lease",
            event_type=WorkflowEventType.STEP_STATE_CHANGED,
            next_run_status=None,
            next_step_status=StepStatus.PASSED,
            step_id="step-001",
            worker_id="worker-001",
            occurred_at=now + timedelta(seconds=1),
        )
    )

    assert result.event_sequence == 1
    assert session.get(StageStepModel, "step-001").status == "PASSED"
    session.close()
    engine.dispose()


def test_cancel_sequence_is_idempotent_and_preserves_history(tmp_path: Path) -> None:
    engine, session = _session(tmp_path)
    now = datetime.now(UTC)
    _create_run(session, status="WAITING")
    service = StateTransitionService(session)

    cancelling = service.request_cancel(
        run_id="run-001",
        expected_state_version=1,
        idempotency_key="cancel-request",
        actor="tester",
        now=now,
    )
    replay = service.request_cancel(
        run_id="run-001",
        expected_state_version=1,
        idempotency_key="cancel-request",
        actor="tester",
        now=now,
    )
    cancelled = service.acknowledge_cancel(
        run_id="run-001",
        expected_state_version=2,
        idempotency_key="cancel-ack",
        actor="worker",
        now=now + timedelta(seconds=1),
    )

    assert replay.idempotent_replay is True
    assert cancelling.status == "CANCELLING"
    assert cancelled.status == "CANCELLED"
    assert [event.sequence for event in session.query(WorkflowEventModel).order_by(WorkflowEventModel.sequence)] == [1, 2]
    session.close()
    engine.dispose()


def test_resume_validates_checkpoint_workspace_and_policy_placeholders(tmp_path: Path) -> None:
    engine, session = _session(tmp_path)
    now = datetime.now(UTC)
    _create_run(session, status="WAITING")
    service = StateTransitionService(session)

    with pytest.raises(ResumeRejectedError):
        service.resume_from_checkpoint(
            run_id="run-001",
            expected_state_version=1,
            idempotency_key="resume-rejected",
            actor="tester",
            checkpoint_valid=True,
            workspace_valid=False,
            policy_compatible=True,
            now=now,
        )

    resumed = service.resume_from_checkpoint(
        run_id="run-001",
        expected_state_version=1,
        idempotency_key="resume-accepted",
        actor="tester",
        checkpoint_valid=True,
        workspace_valid=True,
        policy_compatible=True,
        now=now,
    )

    assert resumed.status == "RUNNING"
    assert session.get(MigrationRunModel, "run-001").state_version == 2
    session.close()
    engine.dispose()


def test_illegal_run_transition_is_rejected_without_side_effects(tmp_path: Path) -> None:
    engine, session = _session(tmp_path)
    _create_run(session)
    service = StateTransitionService(session)

    with pytest.raises(IllegalRunTransitionError):
        service.apply_transition(
            _transition_request(
                idempotency_key="illegal",
                next_run_status=RunStatus.COMPLETED,
            )
        )

    assert session.get(MigrationRunModel, "run-001").status == "CREATED"
    assert session.get(MigrationRunModel, "run-001").state_version == 1
    assert session.query(WorkflowEventModel).count() == 0
    session.close()
    engine.dispose()


def test_all_legal_run_transitions_across_event_types_still_pass(tmp_path: Path) -> None:
    engine, session = _session(tmp_path)
    _create_run(session, status="SOURCE_VALIDATION_RUNNING")
    service = StateTransitionService(session)
    legal_transitions = [
        (WorkflowEventType.RUN_STATE_CHANGED, RunStatus.SOURCE_VALIDATION_RUNNING),
        (WorkflowEventType.RUN_STATE_CHANGED, RunStatus.RUNNING),
        (WorkflowEventType.RUN_STATE_CHANGED, RunStatus.CANCELLING),
        (WorkflowEventType.RUN_STATE_CHANGED, RunStatus.CANCELLED),
        (WorkflowEventType.RUN_START_ACCEPTED, RunStatus.SOURCE_VALIDATION_RUNNING),
        (WorkflowEventType.RUN_CANCEL_REQUESTED, RunStatus.CANCELLING),
        (WorkflowEventType.RUN_CANCELLED, RunStatus.CANCELLED),
        (WorkflowEventType.SOURCE_INTAKE_FAILED, RunStatus.FAILED),
        (WorkflowEventType.SNAPSHOT_STARTED, RunStatus.SOURCE_VALIDATION_RUNNING),
        (WorkflowEventType.SNAPSHOT_CREATED, RunStatus.SOURCE_VALIDATED),
        (WorkflowEventType.BASELINE_QUALIFIED, RunStatus.BASELINE_QUALIFIED),
        (WorkflowEventType.BASELINE_BLOCKED, RunStatus.DIAGNOSTIC_HOLD),
        (WorkflowEventType.G03_APPROVED, RunStatus.BASELINE_QUALIFIED),
        (WorkflowEventType.DISCOVERY_BLOCKED, RunStatus.DIAGNOSTIC_HOLD),
        (WorkflowEventType.G02_STALE, RunStatus.DIAGNOSTIC_HOLD),
        (WorkflowEventType.EXECUTION_PROFILE_BLOCKED, RunStatus.DIAGNOSTIC_HOLD),
        (WorkflowEventType.COMPATIBILITY_RESOLUTION_COMPLETED, RunStatus.WAITING_PLAN_APPROVAL),
        (WorkflowEventType.G04_APPROVED, RunStatus.PLANNING_RUNNING),
        (WorkflowEventType.G05_APPROVED, RunStatus.PLANNING_RUNNING),
        (WorkflowEventType.G05_APPROVED, RunStatus.WAITING_PLAN_APPROVAL),
        (WorkflowEventType.G06_APPROVED, RunStatus.WAITING_STAGE_PREPARATION),
        (WorkflowEventType.G06_REJECTED, RunStatus.WAITING_PLAN_APPROVAL),
        (WorkflowEventType.PLANNING_AGENT_COMPLETED, RunStatus.WAITING_PLAN_APPROVAL),
        (WorkflowEventType.PLANNING_REVIEW_REVISION_REQUIRED, RunStatus.WAITING_PLAN_APPROVAL),
        (WorkflowEventType.PLANNING_REVIEW_REJECTED, RunStatus.WAITING_PLAN_APPROVAL),
        (WorkflowEventType.PLANNING_REVIEW_INSUFFICIENT_CONTEXT, RunStatus.WAITING_PLAN_APPROVAL),
        (WorkflowEventType.PLANNING_FAILED, RunStatus.FAILED),
        (WorkflowEventType.STAGED_MIGRATION_COMPLETED, RunStatus.COMPLETED),
        (WorkflowEventType.STAGE_CREATED, RunStatus.STAGE_CREATED),
    ]
    expected_state_version = 1
    for event_type, next_run_status in legal_transitions:
        result = service.apply_transition(
            _transition_request(
                idempotency_key=f"legal-{event_type.value}-{next_run_status.value}",
                expected_state_version=expected_state_version,
                event_type=event_type,
                next_run_status=next_run_status,
            )
        )
        assert result.status == next_run_status.value
        expected_state_version = result.next_state_version
    session.close()
    engine.dispose()
