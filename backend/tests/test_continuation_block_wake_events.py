"""T07: atomic continuation queue/block transitions with durable events.

Every continuation queue/block transition commits together with an
idempotency-keyed workflow event; stuck ``waiting_command`` continuations are
reconciled after worker loss; command wakes are bound to the exact execution.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.contracts import WorkflowEventType
from app.domain.transformation import StageGateDecisionRequest
from app.orchestration.transformer_graph import TransformerOrchestrator
from app.orchestration.transformer_sealing_flow import TransformerSealingFlow
from app.orchestration.transformer_worker import TransformerWorker
from app.repositories.models import (
    CommandExecutionModel,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationStageModel,
    StageGatePackageModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.services.stage_gate_service import StageGateService
from app.services.transformation_continuation_service import (
    TransformationContinuationService,
    append_continuation_event,
)
from app.services.validation_runner import ValidationRunnerError
from tests.test_transformation_continuation import _create, _session

NOW = datetime.now(UTC)

CLAIMED = WorkflowEventType.TRANSFORMATION_CONTINUATION_CLAIMED.value
WAITING = WorkflowEventType.TRANSFORMATION_CONTINUATION_WAITING.value
RESUMED = WorkflowEventType.TRANSFORMATION_CONTINUATION_RESUMED.value
FAILED = WorkflowEventType.TRANSFORMATION_CONTINUATION_FAILED.value
COMPLETED = WorkflowEventType.TRANSFORMATION_CONTINUATION_COMPLETED.value
BLOCKED = WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED.value
CANCEL_REQUESTED = WorkflowEventType.TRANSFORMATION_CANCEL_REQUESTED.value


def _events(session):
    return list(
        session.scalars(
            select(WorkflowEventModel)
            .where(WorkflowEventModel.run_id == "run-1")
            .order_by(WorkflowEventModel.sequence)
        )
    )


def _scope_factory(sessions):
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


def _execution(execution_id: str, *, status: str) -> CommandExecutionModel:
    return CommandExecutionModel(
        id=execution_id,
        run_id="run-1",
        stage_id="stage-1",
        command_id="npm-ci-bootstrap",
        executable="npm",
        arguments=["ci"],
        status=status,
        exit_code=0 if status == "succeeded" else 1,
        failure_code=None if status == "succeeded" else "EXEC_FAILED",
        requested_at=NOW,
        finished_at=NOW,
    )


def _waiting(service, session, *, waiting_execution_id: str):
    continuation = _create(service, session)
    continuation.status = "waiting_command"
    continuation.current_node = "bootstrap_install"
    continuation.worker_id = None
    continuation.lease_expires_at = None
    continuation.waiting_execution_id = waiting_execution_id
    continuation.state_version += 1
    session.commit()
    return continuation


def test_claim_wait_complete_emit_lifecycle_events(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    continuation = _create(service, session)
    session.commit()

    claimed = service.claim_next(session, "worker-1", NOW)
    service.wait(
        session,
        claimed.id,
        "worker-1",
        status="waiting_command",
        current_node="bootstrap_install",
        now=NOW,
    )
    service.wake(session, claimed.id, now=NOW)
    reclaimed = service.claim_next(session, "worker-1", NOW)
    service.complete(session, reclaimed.id, "worker-1", now=NOW)
    session.commit()

    events = _events(session)
    types = [event.event_type for event in events]
    assert CLAIMED in types
    assert WAITING in types
    assert COMPLETED in types
    assert session.get(TransformationContinuationModel, continuation.id).status == "completed"

    claimed_events = [event for event in events if event.event_type == CLAIMED]
    assert [event.idempotency_key for event in claimed_events] == [
        f"{continuation.id}:claim:1",
        f"{continuation.id}:claim:2",
    ]
    assert claimed_events[0].payload["expected_state_version"] == 1
    waiting_events = [event for event in events if event.event_type == WAITING]
    assert waiting_events[0].idempotency_key == f"{continuation.id}:wait:waiting_command:2"
    completed_events = [event for event in events if event.event_type == COMPLETED]
    assert completed_events[0].idempotency_key == f"{continuation.id}:complete"
    session.close()
    engine.dispose()


def test_request_cancel_emits_cancel_requested_idempotently(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    continuation = _create(service, session)
    session.commit()
    service.claim_next(session, "worker-1", NOW)
    service.request_cancel(
        session,
        continuation.id,
        actor="operator",
        idempotency_key="cancel-1",
        expected_state_version=continuation.state_version,
        now=NOW,
    )
    service.request_cancel(
        session,
        continuation.id,
        actor="operator",
        idempotency_key="cancel-1",
        expected_state_version=continuation.state_version,
        now=NOW,
    )
    session.commit()

    cancel_events = [
        event for event in _events(session) if event.event_type == CANCEL_REQUESTED
    ]
    assert len(cancel_events) == 1
    assert cancel_events[0].idempotency_key == f"{continuation.id}:cancel:cancel-1"
    assert session.get(TransformationContinuationModel, continuation.id).status == "cancelling"
    session.close()
    engine.dispose()


def test_graph_block_emits_blocked_event_atomically(tmp_path: Path):
    engine, seed = _session(tmp_path)
    continuation = _create(TransformationContinuationService(), seed)
    gate = seed.get(G06ApprovalModel, "g06-1")
    gate.status = "rejected"
    continuation.status = "running"
    continuation.worker_id = "worker-1"
    continuation.current_node = "validate_g06"
    continuation_id = continuation.id
    seed.commit()
    seed.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    orchestrator = TransformerOrchestrator(scope=_scope_factory(sessions))

    orchestrator.advance(continuation_id, "worker-1")

    with sessions() as session:
        durable = session.get(TransformationContinuationModel, continuation_id)
        assert durable.status == "blocked"
        assert durable.last_error_code == "G06_BINDING_STALE"
        blocked_events = [
            event for event in _events(session) if event.event_type == BLOCKED
        ]
        assert len(blocked_events) == 1
        assert blocked_events[0].idempotency_key == f"{continuation_id}:block:1:G06_BINDING_STALE"
        assert blocked_events[0].payload["last_error_code"] == "G06_BINDING_STALE"
        assert blocked_events[0].payload["expected_state_version"] == 1
    engine.dispose()


def test_block_status_write_rolls_back_with_event_append_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    engine, seed = _session(tmp_path)
    continuation = _create(TransformationContinuationService(), seed)
    gate = seed.get(G06ApprovalModel, "g06-1")
    gate.status = "rejected"
    continuation.status = "running"
    continuation.worker_id = "worker-1"
    continuation.current_node = "validate_g06"
    continuation_id = continuation.id
    seed.commit()
    seed.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    orchestrator = TransformerOrchestrator(scope=_scope_factory(sessions))

    def boom(*_args, **_kwargs):
        raise RuntimeError("event append failed")

    monkeypatch.setattr(
        "app.orchestration.transformer_graph.append_continuation_event", boom
    )
    with pytest.raises(RuntimeError, match="event append failed"):
        orchestrator.advance(continuation_id, "worker-1")

    with sessions() as session:
        durable = session.get(TransformationContinuationModel, continuation_id)
        assert durable.status == "running"
        assert durable.last_error_code is None
        blocked_events = [
            event for event in _events(session) if event.event_type == BLOCKED
        ]
        assert blocked_events == []
    engine.dispose()


def test_wake_fires_only_for_linked_execution_and_emits_resumed(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    session.add_all([_execution("exec-a", status="succeeded"), _execution("exec-b", status="failed")])
    continuation = _waiting(service, session, waiting_execution_id="exec-a")
    session.commit()
    session.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    worker = TransformerWorker(scope=_scope_factory(sessions))

    worker._wake_command_waiter("exec-b")

    with sessions() as session:
        durable = session.get(TransformationContinuationModel, continuation.id)
        assert durable.status == "waiting_command"
        assert durable.wake_sequence == 0

    worker._wake_command_waiter("exec-a")

    with sessions() as session:
        durable = session.get(TransformationContinuationModel, continuation.id)
        assert durable.status == "queued"
        assert durable.wake_sequence == 1
        resumed_events = [event for event in _events(session) if event.event_type == RESUMED]
        assert len(resumed_events) == 1
        assert resumed_events[0].idempotency_key == f"{continuation.id}:wake:1"
        assert resumed_events[0].payload["execution_id"] == "exec-a"
    engine.dispose()


def test_stuck_waiting_command_is_reconciled_after_worker_loss(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    session.add(_execution("exec-1", status="succeeded"))
    continuation = _waiting(service, session, waiting_execution_id="exec-1")
    session.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    scope = _scope_factory(sessions)
    worker = TransformerWorker(scope=scope)

    with scope() as session:
        reconciled = worker.reconcile_stuck_command_waiters(session, NOW)

    assert reconciled == [continuation.id]
    with sessions() as session:
        durable = session.get(TransformationContinuationModel, continuation.id)
        assert durable.status == "queued"
        assert durable.wake_sequence == 1
        resumed_events = [event for event in _events(session) if event.event_type == RESUMED]
        assert len(resumed_events) == 1
        assert resumed_events[0].idempotency_key == f"{continuation.id}:wake:1"
        assert resumed_events[0].payload["execution_id"] == "exec-1"
    engine.dispose()


def test_stuck_waiting_command_with_missing_execution_is_blocked(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    continuation = _waiting(service, session, waiting_execution_id="exec-gone")
    session.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    scope = _scope_factory(sessions)
    worker = TransformerWorker(scope=scope)

    with scope() as session:
        reconciled = worker.reconcile_stuck_command_waiters(session, NOW)

    assert reconciled == [continuation.id]
    with sessions() as session:
        durable = session.get(TransformationContinuationModel, continuation.id)
        assert durable.status == "blocked"
        assert durable.last_error_code == "COMMAND_LOST_AFTER_RESTART"
        blocked_events = [event for event in _events(session) if event.event_type == BLOCKED]
        assert len(blocked_events) == 1
        assert (
            blocked_events[0].idempotency_key
            == f"{continuation.id}:block:2:COMMAND_LOST_AFTER_RESTART"
        )
    engine.dispose()


def test_run_once_requeues_stuck_waiter_then_reclaims_it(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    session.add(_execution("exec-1", status="succeeded"))
    continuation = _waiting(service, session, waiting_execution_id="exec-1")
    session.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    stub_workflow = SimpleNamespace(invoke=lambda continuation_id, worker_id: None)
    worker = TransformerWorker(
        scope=_scope_factory(sessions), workflow=stub_workflow, worker_id="worker-loop"
    )

    worked = worker.run_once()

    assert worked is True
    with sessions() as session:
        durable = session.get(TransformationContinuationModel, continuation.id)
        assert durable.status == "running"
        assert durable.worker_id == "worker-loop"
        assert durable.claim_count == 1
        event_types = [event.event_type for event in _events(session)]
        assert RESUMED in event_types
        assert CLAIMED in event_types
    engine.dispose()


def test_validation_failure_emits_failed_event(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    continuation = _create(service, session)
    continuation.status = "running"
    continuation.worker_id = "worker-1"
    session.commit()

    TransformerOrchestrator._validation_failure(
        session,
        continuation,
        ValidationRunnerError("VALIDATION_BINDING_STALE", "binding stale"),
    )
    session.commit()

    assert continuation.status == "queued"
    assert continuation.last_error_code == "VALIDATION_BINDING_STALE"
    failed_events = [event for event in _events(session) if event.event_type == FAILED]
    assert len(failed_events) == 1
    assert (
        failed_events[0].idempotency_key
        == f"{continuation.id}:failed:1:VALIDATION_BINDING_STALE"
    )
    assert failed_events[0].payload["last_error_code"] == "VALIDATION_BINDING_STALE"
    session.close()
    engine.dispose()


def test_append_continuation_event_is_idempotent_under_replay(tmp_path: Path):
    engine, session = _session(tmp_path)
    continuation = _create(TransformationContinuationService(), session)

    append_continuation_event(
        session,
        continuation,
        event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED,
        key="block:7:REPLAY_CODE",
        reason="replayed block",
    )
    append_continuation_event(
        session,
        continuation,
        event_type=WorkflowEventType.TRANSFORMATION_CONTINUATION_BLOCKED,
        key="block:7:REPLAY_CODE",
        reason="replayed block",
    )
    session.commit()

    blocked_events = [event for event in _events(session) if event.event_type == BLOCKED]
    assert len(blocked_events) == 1
    assert blocked_events[0].idempotency_key == f"{continuation.id}:block:7:REPLAY_CODE"
    session.close()
    engine.dispose()


def _gate_decision(version: int, *, key: str, decision: str = "approve", comment: str | None = None):
    return StageGateDecisionRequest(
        expected_state_version=version,
        idempotency_key=key,
        package_checksum="sha256:g07-package",
        workspace_fingerprint="sha256:workspace",
        decision=decision,
        comment=comment,
        correlation_id="correlation-1",
    )


def _gate_waiting(service, session, *, gate_id: str = "G07"):
    continuation = _create(service, session)
    continuation.status = "running"
    continuation.worker_id = "worker-1"
    package = StageGateService().create(
        session,
        continuation,
        gate_id=gate_id,
        package_artifact_id=f"artifact-{gate_id.lower()}",
        package_checksum="sha256:g07-package",
        artifact_set_checksum="sha256:g07-set",
        workspace_fingerprint="sha256:workspace",
        now=NOW,
    )
    session.commit()
    return continuation, package


def test_gate_rejection_blocks_with_atomic_blocked_event(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    continuation, _package = _gate_waiting(service, session)
    expected_state_version = continuation.state_version

    StageGateService().decide(
        session,
        continuation,
        "G07",
        _gate_decision(
            expected_state_version,
            key="g07-reject-1",
            decision="reject",
            comment="needs rework",
        ),
        actor="operator",
        now=NOW,
    )
    session.commit()

    durable = session.get(TransformationContinuationModel, continuation.id)
    assert durable.status == "blocked"
    assert durable.last_error_code == "G07_REJECT"
    blocked_events = [event for event in _events(session) if event.event_type == BLOCKED]
    assert len(blocked_events) == 1
    assert (
        blocked_events[0].idempotency_key
        == f"{continuation.id}:block:{expected_state_version}:G07_REJECT"
    )
    assert blocked_events[0].payload["last_error_code"] == "G07_REJECT"
    assert blocked_events[0].payload["expected_state_version"] == expected_state_version
    assert blocked_events[0].payload["reason"] == "needs rework"
    session.close()
    engine.dispose()


def test_gate_approval_requeues_with_atomic_resumed_event(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    continuation, package = _gate_waiting(service, session)
    expected_state_version = continuation.state_version

    StageGateService().decide(
        session,
        continuation,
        "G07",
        _gate_decision(expected_state_version, key="g07-approve-1", decision="approve"),
        actor="operator",
        now=NOW,
    )
    session.commit()

    durable = session.get(TransformationContinuationModel, continuation.id)
    assert durable.status == "queued"
    assert durable.current_node == "bootstrap_install"
    assert durable.wake_sequence == 1
    resumed_events = [event for event in _events(session) if event.event_type == RESUMED]
    assert len(resumed_events) == 1
    assert (
        resumed_events[0].idempotency_key
        == f"{continuation.id}:gate-accepted:G07:{package.id}"
    )
    assert resumed_events[0].payload["expected_state_version"] == expected_state_version
    assert resumed_events[0].payload["gate_id"] == "G07"
    session.close()
    engine.dispose()


def test_gate_decision_replay_does_not_duplicate_events(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    continuation, _package = _gate_waiting(service, session)
    expected_state_version = continuation.state_version
    gate_service = StageGateService()
    request = _gate_decision(
        expected_state_version,
        key="g07-reject-replay",
        decision="reject",
        comment="replayed",
    )

    gate_service.decide(session, continuation, "G07", request, actor="operator", now=NOW)
    gate_service.decide(session, continuation, "G07", request, actor="operator", now=NOW)
    session.commit()

    blocked_events = [event for event in _events(session) if event.event_type == BLOCKED]
    assert len(blocked_events) == 1
    assert blocked_events[0].payload["reason"] == "replayed"
    session.close()
    engine.dispose()


def _seed_completed_route(session, continuation) -> None:
    plan = session.get(MigrationPlanModel, "plan-1")
    plan.plan = {"route": ["stage-1"]}
    stage = session.get(MigrationStageModel, "stage-1")
    stage.status = "sealed"
    for gate_id in ("G07", "G08", "G09", "G12"):
        session.add(
            StageGatePackageModel(
                id=f"gate-package-{gate_id.lower()}",
                run_id="run-1",
                stage_id="stage-1",
                gate_id=gate_id,
                gate_version=1,
                status="approved",
                package_artifact_id=f"artifact-{gate_id.lower()}",
                package_checksum=f"sha256:{gate_id.lower()}-package",
                artifact_set_checksum=f"sha256:{gate_id.lower()}-set",
                plan_id="plan-1",
                plan_version=1,
                stage_plan_id="stage-plan-1",
                stage_plan_checksum="sha256:stage-plan",
                workspace_fingerprint="sha256:workspace",
                expected_state_version=2,
                created_at=NOW,
            )
        )


def test_sealing_complete_emits_completed_event_atomically(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    continuation = _create(service, session)
    continuation.status = "running"
    continuation.worker_id = "worker-1"
    _seed_completed_route(session, continuation)
    continuation_id = continuation.id
    session.commit()
    session.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    flow = TransformerSealingFlow(
        scope=_scope_factory(sessions),
        stage_service=MagicMock(),
        gate_service=MagicMock(),
    )

    flow.complete(continuation_id, "worker-1")

    with sessions() as session:
        durable = session.get(TransformationContinuationModel, continuation_id)
        assert durable.status == "completed"
        completed_events = [
            event for event in _events(session) if event.event_type == COMPLETED
        ]
        assert len(completed_events) == 1
        assert completed_events[0].idempotency_key == f"{continuation_id}:complete"
    engine.dispose()


def test_null_linkage_waiter_with_single_terminal_command_is_requeued(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    session.add(_execution("exec-1", status="succeeded"))
    continuation = _waiting(service, session, waiting_execution_id=None)
    session.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    scope = _scope_factory(sessions)
    worker = TransformerWorker(scope=scope)

    with scope() as session:
        reconciled = worker.reconcile_stuck_command_waiters(session, NOW)

    assert reconciled == [continuation.id]
    with sessions() as session:
        durable = session.get(TransformationContinuationModel, continuation.id)
        assert durable.status == "queued"
        assert durable.wake_sequence == 1
        resumed_events = [event for event in _events(session) if event.event_type == RESUMED]
        assert len(resumed_events) == 1
        assert resumed_events[0].idempotency_key == f"{continuation.id}:wake:1"
        assert resumed_events[0].payload["execution_id"] == "exec-1"
    engine.dispose()


def test_null_linkage_waiter_with_zero_command_rows_is_blocked(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    continuation = _waiting(service, session, waiting_execution_id=None)
    session.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    scope = _scope_factory(sessions)
    worker = TransformerWorker(scope=scope)

    with scope() as session:
        reconciled = worker.reconcile_stuck_command_waiters(session, NOW)

    assert reconciled == [continuation.id]
    with sessions() as session:
        durable = session.get(TransformationContinuationModel, continuation.id)
        assert durable.status == "blocked"
        assert durable.last_error_code == "COMMAND_LOST_AFTER_RESTART"
        blocked_events = [event for event in _events(session) if event.event_type == BLOCKED]
        assert len(blocked_events) == 1
        assert (
            blocked_events[0].idempotency_key
            == f"{continuation.id}:block:2:COMMAND_LOST_AFTER_RESTART"
        )
    engine.dispose()


def test_null_linkage_waiter_with_two_terminal_commands_is_blocked_ambiguous(
    tmp_path: Path,
):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    session.add(_execution("exec-1", status="succeeded"))
    session.add(_execution("exec-2", status="failed"))
    continuation = _waiting(service, session, waiting_execution_id=None)
    session.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    scope = _scope_factory(sessions)
    worker = TransformerWorker(scope=scope)

    with scope() as session:
        reconciled = worker.reconcile_stuck_command_waiters(session, NOW)

    assert reconciled == [continuation.id]
    with sessions() as session:
        durable = session.get(TransformationContinuationModel, continuation.id)
        assert durable.status == "blocked"
        assert durable.last_error_code == "COMMAND_WAIT_AMBIGUOUS"
        blocked_events = [event for event in _events(session) if event.event_type == BLOCKED]
        assert len(blocked_events) == 1
        assert (
            blocked_events[0].idempotency_key
            == f"{continuation.id}:block:2:COMMAND_WAIT_AMBIGUOUS"
        )
    engine.dispose()


def test_null_linkage_waiter_with_only_active_command_stays_waiting(tmp_path: Path):
    engine, session = _session(tmp_path)
    service = TransformationContinuationService()
    session.add(_execution("exec-1", status="running"))
    continuation = _waiting(service, session, waiting_execution_id=None)
    session.close()
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    scope = _scope_factory(sessions)
    worker = TransformerWorker(scope=scope)

    with scope() as session:
        reconciled = worker.reconcile_stuck_command_waiters(session, NOW)

    assert reconciled == []
    with sessions() as session:
        durable = session.get(TransformationContinuationModel, continuation.id)
        assert durable.status == "waiting_command"
        assert durable.wake_sequence == 0
    engine.dispose()
