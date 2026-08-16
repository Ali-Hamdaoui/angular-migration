"""Tests for F04 repair lifecycle reliability."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.domain.repair_lifecycle import (
    RepairLifecycleStatus,
    can_transition,
    evaluate_transition,
    is_sealed,
    restart_recovery_target,
)
from app.repositories.models import (
    FailureDiagnosticPackModel,
    MigrationRunModel,
    MigrationStageModel,
    RepairAttemptModel,
    WorkflowEventModel,
)
from app.repositories.session import session_scope
from app.services.repair_lifecycle_reliability_service import (
    RepairLifecycleError,
    RepairLifecycleReliabilityService,
)

NOW = datetime.now(UTC)


def test_lifecycle_status_vocabulary_and_legal_transitions():
    assert can_transition("evidence_frozen", "proposed") is True
    assert can_transition("proposed", "review_accepted") is True
    assert can_transition("review_accepted", "waiting_g10") is True
    assert can_transition("waiting_g10", "approved_pending_execution") is True
    assert can_transition("approved_pending_execution", "applied_verified") is True
    assert can_transition("applied_verified", "migration_retried") is True
    assert can_transition("proposed", "evidence_frozen") is False
    assert can_transition("superseded", "proposed") is False


def test_terminal_states_are_sealed():
    for status in ("superseded", "rejected", "cancelled"):
        assert is_sealed(status) is True
    # conservative sealed set: workflow-resumable states are never sealed
    for status in ("evidence_frozen", "proposed", "review_accepted", "waiting_g10",
                   "approved_pending_execution", "executing", "applied", "applied_verified",
                   "migration_retried", "revalidating", "apply_recovery_required"):
        assert is_sealed(status) is False
    assert is_sealed(None) is False


def test_evaluate_transition_rejects_sealed_lifecycle():
    result = evaluate_transition("attempt-1", "superseded", "proposed")
    assert result.allowed is False
    assert result.sealed is True
    assert "sealed" in result.reason


def test_restart_recovery_targets():
    assert restart_recovery_target("executing") == "apply_recovery_required"
    assert restart_recovery_target("applying") == "apply_recovery_required"
    # resumable states are never demoted
    assert restart_recovery_target("evidence_frozen") is None
    assert restart_recovery_target("proposed") is None
    assert restart_recovery_target("review_accepted") is None
    assert restart_recovery_target("applied") is None
    assert restart_recovery_target("superseded") is None


def _seed(run_id: str, stage_id: str, attempt_id: str, status: str) -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(id=stage_id, run_id=run_id, stage_order=1,
                                        source_version_family="angular-18.x", target_version_family="angular-19.x",
                                        status="planned", created_at=NOW))
        session.add(RepairAttemptModel(
            id=attempt_id, run_id=run_id, stage_id=stage_id, attempt_number=1,
            state_version=1, status=status, risk_level="low",
            created_at=NOW, updated_at=NOW,
        ))
        session.commit()


def test_restart_sweep_recovers_interrupted_apply(tmp_path: Path):
    run_id = f"run-f04-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, stage_id, attempt_id, "executing")

    service = RepairLifecycleReliabilityService()
    recovered = service.recover_in_flight_repairs(run_id=run_id)
    assert attempt_id in recovered

    with session_scope() as session:
        attempt = session.get(RepairAttemptModel, attempt_id)
        assert attempt.status == "apply_recovery_required"
        assert attempt.state_version == 2
        # a recovery event was recorded
        events = session.query(WorkflowEventModel).filter_by(run_id=run_id).all()
        assert any("recover" in (e.idempotency_key or "") for e in events)
        # a diagnostic pack was recorded
        packs = session.query(FailureDiagnosticPackModel).filter_by(run_id=run_id).all()
        assert any(p.fault_code == "REPAIR_LIFECYCLE_RECOVERED" for p in packs)


def test_restart_sweep_keeps_resumable_states_with_marker(tmp_path: Path):
    run_id = f"run-f04-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, stage_id, attempt_id, "proposed")

    service = RepairLifecycleReliabilityService()
    recovered = service.recover_in_flight_repairs(run_id=run_id)
    assert attempt_id in recovered

    with session_scope() as session:
        attempt = session.get(RepairAttemptModel, attempt_id)
        # proposed is resumable by the continuation authority; status unchanged
        assert attempt.status == "proposed"
        assert attempt.state_version == 1
        events = session.query(WorkflowEventModel).filter_by(run_id=run_id).all()
        assert any("resumable" in (e.idempotency_key or "") for e in events)


def test_restart_sweep_is_idempotent_and_skips_sealed(tmp_path: Path):
    run_id = f"run-f04-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, stage_id, attempt_id, "applied")

    service = RepairLifecycleReliabilityService()
    assert service.recover_in_flight_repairs(run_id=run_id) == []
    with session_scope() as session:
        assert session.get(RepairAttemptModel, attempt_id).status == "applied"


def test_optimistic_version_transition_cas(tmp_path: Path):
    run_id = f"run-f04-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, stage_id, attempt_id, "evidence_frozen")

    service = RepairLifecycleReliabilityService()
    # stale expected version rejected
    with pytest.raises(RepairLifecycleError) as exc:
        service.transition(attempt_id, "proposed", expected_state_version=99)
    assert exc.value.code == "REPAIR_STATE_VERSION_CONFLICT"
    # correct CAS succeeds
    attempt = service.transition(attempt_id, "proposed", expected_state_version=1)
    assert attempt.status == "proposed"
    assert attempt.state_version == 2


def test_illegal_transition_rejected(tmp_path: Path):
    run_id = f"run-f04-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, stage_id, attempt_id, "evidence_frozen")

    service = RepairLifecycleReliabilityService()
    with pytest.raises(RepairLifecycleError) as exc:
        service.transition(attempt_id, "applied_verified", expected_state_version=1)
    assert exc.value.code == "REPAIR_TRANSITION_ILLEGAL"


def test_assert_mutable_blocks_sealed_lifecycle(tmp_path: Path):
    run_id = f"run-f04-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, stage_id, attempt_id, "superseded")

    service = RepairLifecycleReliabilityService()
    with pytest.raises(RepairLifecycleError) as exc:
        service.assert_mutable(attempt_id)
    assert exc.value.code == "REPAIR_LIFECYCLE_SEALED"
    # resumable attempts are mutable
    with session_scope() as session:
        session.add(RepairAttemptModel(id="attempt-mut", run_id=run_id, stage_id=stage_id,
            attempt_number=2, state_version=1, status="proposed", risk_level="low",
            created_at=NOW, updated_at=NOW))
        session.commit()
    assert service.assert_mutable("attempt-mut").status == "proposed"


def test_reconcile_converges_observed_to_intended(tmp_path: Path):
    run_id = f"run-f04-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, stage_id, attempt_id, "proposed")

    service = RepairLifecycleReliabilityService()
    with session_scope() as session:
        attempt = session.get(RepairAttemptModel, attempt_id)
        reconciled = service.reconcile_attempt_status(attempt, observed_status="evidence_frozen")
    assert reconciled.status == "proposed"
