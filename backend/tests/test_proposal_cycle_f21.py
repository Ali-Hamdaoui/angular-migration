"""Tests for F21 governed repair proposal cycles."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import MigrationRunModel, ProposalCycleModel, RepairAttemptModel
from app.repositories.session import session_scope
from app.services.proposal_cycle_service import ProposalCycleError, ProposalCycleService

NOW = datetime.now(UTC)
client = TestClient(app)


def _seed(run_id: str, attempt_id: str) -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized", created_at=NOW, updated_at=NOW))
        session.add(RepairAttemptModel(id=attempt_id, run_id=run_id, stage_id=f"stage-{run_id}",
                                       attempt_number=1, state_version=1, status="evidence_frozen",
                                       risk_level="low", created_at=NOW, updated_at=NOW))
        session.commit()


def test_create_cycle():
    run_id = f"run-f21-{uuid4().hex[:8]}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, attempt_id)
    service = ProposalCycleService()
    cycle = service.create_cycle(run_id, attempt_id, "sha256:" + "a" * 64)
    assert cycle.cycle_number == 1
    assert cycle.decision == "pending"
    assert cycle.checksum.startswith("sha256:")


def test_cycle_is_immutable_and_idempotent():
    run_id = f"run-f21-{uuid4().hex[:8]}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, attempt_id)
    service = ProposalCycleService()
    checksum = "sha256:" + "b" * 64
    first = service.create_cycle(run_id, attempt_id, checksum)
    second = service.create_cycle(run_id, attempt_id, checksum)
    assert first.cycle_id == second.cycle_id


def test_decide_accept_and_reject():
    run_id = f"run-f21-{uuid4().hex[:8]}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, attempt_id)
    service = ProposalCycleService()
    cycle = service.create_cycle(run_id, attempt_id, "sha256:" + "c" * 64)
    accepted = service.decide(cycle.cycle_id, "accepted", reviewer="operator")
    assert accepted.decision == "accepted"
    assert accepted.reviewer == "operator"
    # cannot decide twice
    try:
        service.decide(cycle.cycle_id, "rejected")
        assert False, "expected CYCLE_ALREADY_DECIDED"
    except ProposalCycleError as exc:
        assert exc.code == "CYCLE_ALREADY_DECIDED"


def test_request_changes_creates_child_cycle():
    run_id = f"run-f21-{uuid4().hex[:8]}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, attempt_id)
    service = ProposalCycleService()
    cycle = service.create_cycle(run_id, attempt_id, "sha256:" + "d" * 64)
    decided = service.decide(cycle.cycle_id, "request_changes", reviewer="operator", hints=["fix the import"])
    assert decided.decision == "request_changes"
    lineage = service.list_lineage(attempt_id)
    assert len(lineage) >= 2
    child = lineage[-1]
    assert child.parent_cycle_id == cycle.cycle_id
    assert "fix the import" in child.hints


def test_lineage_ordering():
    run_id = f"run-f21-{uuid4().hex[:8]}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, attempt_id)
    service = ProposalCycleService()
    service.create_cycle(run_id, attempt_id, "sha256:" + "e" * 64)
    service.create_cycle(run_id, attempt_id, "sha256:" + "f" * 64)
    lineage = service.list_lineage(attempt_id)
    assert [c.cycle_number for c in lineage] == [1, 2]


def test_checksum_stable_across_decision_and_matches_persisted():
    run_id = f"run-f21-{uuid4().hex[:8]}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, attempt_id)
    service = ProposalCycleService()
    checksum = "sha256:" + "h" * 64
    cycle = service.create_cycle(run_id, attempt_id, checksum)
    decided = service.decide(cycle.cycle_id, "accepted", reviewer="operator")
    # the cycle identity checksum is stable across the decision and matches the DB
    assert decided.checksum == cycle.checksum
    with session_scope() as session:
        row = session.get(ProposalCycleModel, cycle.cycle_id)
        assert row.checksum == cycle.checksum


def test_api_create_and_decide():
    run_id = f"run-f21-{uuid4().hex[:8]}"
    attempt_id = f"attempt-{uuid4().hex[:8]}"
    _seed(run_id, attempt_id)
    created = client.post(f"/runs/{run_id}/attempts/{attempt_id}/cycles", json={"proposal_checksum": "sha256:" + "g" * 64})
    assert created.status_code == 200
    cycle_id = created.json()["cycle_id"]

    decided = client.post(f"/cycles/{cycle_id}/decide", json={"decision": "accepted", "reviewer": "operator"})
    assert decided.status_code == 200
    assert decided.json()["decision"] == "accepted"

    listed = client.get(f"/attempts/{attempt_id}/cycles")
    assert listed.status_code == 200
    assert len(listed.json()["cycles"]) == 1
    with session_scope() as session:
        assert session.query(ProposalCycleModel).filter_by(attempt_id=attempt_id).count() == 1
