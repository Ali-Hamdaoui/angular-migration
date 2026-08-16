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
    assert can_transition("pending", "proposing") is True
    assert can_transition("proposing", "proposed") is True
    assert can_transition("evidence_frozen", "waiting_g10") is True
    assert can_transition("applied", "pending") is False
    assert can_transition("proposing", "applied") is False


def test_terminal_states_are_sealed():
    for status in ("applied", "superseded", "rejected", "failed", "completed", "applied_verified"):
        assert is_sealed(status) is True
    assert is_sealed("proposing") is False
    assert is_sealed(None) is False


def test_evaluate_transition_rejects_sealed_lifecycle():
    result = evaluate_transition("attempt-1", "applied", "pending")
    assert result.allowed is False
    assert result.sealed is True
    assert "sealed" in result.reason


def test_restart_recovery_targets():
    assert restart_recovery_target("proposing") == "pending"
    assert restart_recovery_target("proposed") == "evidence_frozen"
    assert restart_recovery_target("evidence_frozen") == "evidence_frozen"
    assert restart_recovery_target("applied") is None
    assert restart_recovery_target("pending") == "pending"


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


def test_restart_sweep_recovers_stranded_in_flight_attempt(tmp_path: Path):
    run_id = f"run-f04-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, stage_id, attempt_id, "proposing")

    service = RepairLifecycleReliabilityService()
    recovered = service.recover_in_flight_repairs(run_id=run_id)
    assert attempt_id in recovered

    with session_scope() as session:
        attempt = session.get(RepairAttemptModel, attempt_id)
        assert attempt.status == "pending"
        assert attempt.state_version == 2
        # a recovery event was recorded
        events = session.query(WorkflowEventModel).filter_by(run_id=run_id).all()
        assert any("recover" in (e.idempotency_key or "") for e in events)
        # a diagnostic pack was recorded
        packs = session.query(FailureDiagnosticPackModel).filter_by(run_id=run_id).all()
        assert any(p.fault_code == "REPAIR_LIFECYCLE_RECOVERED" for p in packs)


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
    _seed(run_id, stage_id, attempt_id, "pending")

    service = RepairLifecycleReliabilityService()
    # stale expected version rejected
    with pytest.raises(RepairLifecycleError) as exc:
        service.transition(attempt_id, "proposing", expected_state_version=99)
    assert exc.value.code == "REPAIR_STATE_VERSION_CONFLICT"
    # correct CAS succeeds
    attempt = service.transition(attempt_id, "proposing", expected_state_version=1)
    assert attempt.status == "proposing"
    assert attempt.state_version == 2


def test_illegal_transition_rejected(tmp_path: Path):
    run_id = f"run-f04-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, stage_id, attempt_id, "pending")

    service = RepairLifecycleReliabilityService()
    with pytest.raises(RepairLifecycleError) as exc:
        service.transition(attempt_id, "applied", expected_state_version=1)
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


def test_reconcile_converges_observed_to_intended(tmp_path: Path):
    run_id = f"run-f04-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, stage_id, attempt_id, "pending")

    service = RepairLifecycleReliabilityService()
    with session_scope() as session:
        attempt = session.get(RepairAttemptModel, attempt_id)
        reconciled = service.reconcile_attempt_status(attempt, observed_status="proposing")
    assert reconciled.status == "pending"
