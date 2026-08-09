import pytest

from app.repositories.models import G05ApprovalModel
from app.services.planning_evidence_application_service import PlanningEvidenceError

from tests.test_planning_evidence_persistence_api_s2_f06_i02 import setup


def test_legacy_empty_policy_snapshot_does_not_bypass_missing_g05(tmp_path):
    service, payload, sessions, _ = setup(tmp_path)
    with sessions.begin() as session:
        session.query(G05ApprovalModel).delete()

    with pytest.raises(PlanningEvidenceError) as error:
        service.create("run-1", payload, "operator")

    assert error.value.code == "G05_APPROVAL_REQUIRED"
