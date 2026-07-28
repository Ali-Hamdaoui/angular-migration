from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.repositories.models import Base, G03ApprovalModel, G04ApprovalModel
from app.services.planning_input_resolver import PlanningInputResolutionError, PlanningInputResolver


NOW = datetime(2026, 7, 28, tzinfo=UTC)
FINGERPRINT = "sha256:" + "3" * 64


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _g04(*, workspace_fingerprint=None):
    return G04ApprovalModel(
        id="g04-1", run_id="run-1", gate_id="G04", gate_version="g04-v1",
        idempotency_key="g04-1", actor="operator", status="approved", decision="approve",
        package_checksum="sha256:" + "4" * 64, artifact_set_checksum="sha256:" + "5" * 64,
        workspace_fingerprint=workspace_fingerprint, plan_version=None, state_version=1, event_sequence=1,
        artifact_ids=[], comment=None, stale_reason=None,
        created_at=NOW, updated_at=NOW,
    )


def _g03(*, fingerprint=FINGERPRINT):
    return G03ApprovalModel(
        id="g03-1", run_id="run-1", gate_id="G03", gate_version="g03-v1",
        idempotency_key="g03-1", actor="operator", status="approved", decision="approved",
        package_checksum="sha256:" + "1" * 64, evidence_set_checksum="sha256:" + "2" * 64,
        qualification_status="qualified", policy_version="g03-v1", state_version=1, event_sequence=1,
        sandbox_fingerprint=fingerprint, execution_profile_checksum="sha256:" + "7" * 64,
        package={}, artifact_ids=[], comment=None, created_at=NOW, updated_at=NOW,
    )


def test_legacy_g04_without_fingerprint_rebinds_to_approved_g03():
    session = _session()
    gate = _g04()
    session.add_all([_g03(), gate])
    session.flush()

    assert PlanningInputResolver._workspace_fingerprint(session, "run-1", gate) == FINGERPRINT


def test_g04_fingerprint_must_match_approved_g03():
    session = _session()
    gate = _g04(workspace_fingerprint="sha256:" + "9" * 64)
    session.add_all([_g03(), gate])
    session.flush()

    with pytest.raises(PlanningInputResolutionError) as error:
        PlanningInputResolver._workspace_fingerprint(session, "run-1", gate)

    assert error.value.code == "PLANNING_G04_WORKSPACE_FINGERPRINT_MISMATCH"


def test_missing_g03_fingerprint_fails_closed():
    session = _session()
    gate = _g04()
    session.add_all([_g03(fingerprint=""), gate])
    session.flush()

    with pytest.raises(PlanningInputResolutionError) as error:
        PlanningInputResolver._workspace_fingerprint(session, "run-1", gate)

    assert error.value.code == "PLANNING_WORKSPACE_FINGERPRINT_MISSING"
