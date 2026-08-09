import pytest
from types import SimpleNamespace

from app.api.baseline_g03_contracts import BaselineQualifyRequest
from app.services.baseline_g03_application_service import BaselineG03ApplicationError, BaselineG03ApplicationService
from tests.test_baseline_parity_persistence_api_s1_f13 import fixture


def test_g03_preserves_exact_skipped_validation_status():
    service = BaselineG03ApplicationService()

    assert service.validation_status(
        SimpleNamespace(
            status="passed",
            results=[{"status": "skipped_not_configured"}],
        )
    ) == "skipped_not_configured"
    assert service.validation_status(
        SimpleNamespace(
            status="passed",
            results=[{"status": "skipped_not_applicable"}],
        )
    ) == "skipped_not_applicable"


def test_g03_rejects_missing_s1_f13_evidence(tmp_path):
    scope, _sessions, engine = fixture(tmp_path)
    try:
        with pytest.raises(BaselineG03ApplicationError, match="parity evidence") as error:
            BaselineG03ApplicationService(scope=scope).qualify(
                "run-1",
                BaselineQualifyRequest(expected_state_version=1, idempotency_key="g03-without-parity", actor="operator"),
            )
        assert error.value.code == "BASELINE_PARITY_EVIDENCE_REQUIRED"
    finally:
        engine.dispose()
