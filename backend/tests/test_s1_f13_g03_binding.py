import pytest
from datetime import timedelta
from types import SimpleNamespace

from app.api.baseline_g03_contracts import BaselineQualifyRequest
from app.repositories.baseline_g03_models import G03ApprovalModel
from app.repositories.models import BaselineAssessmentModel
from app.services.baseline_g03_application_service import BaselineG03ApplicationError, BaselineG03ApplicationService
from tests.test_baseline_parity_persistence_api_s1_f13 import NOW, fixture


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


def test_g03_uses_only_latest_validation_per_kind_after_governed_repair():
    history = [
        SimpleNamespace(kind="test", id="failed-before-repair"),
        SimpleNamespace(kind="lint", id="current-lint"),
        SimpleNamespace(kind="test", id="passed-after-repair"),
    ]

    selected = BaselineG03ApplicationService._latest_validations(history)

    assert [(item.kind, item.id) for item in selected] == [
        ("test", "passed-after-repair"), ("lint", "current-lint"),
    ]


def test_g03_get_does_not_attach_a_superseded_package_decision(tmp_path):
    scope, sessions, engine = fixture(tmp_path)
    common = {
        "run_id": "run-1", "actor": "operator", "status": "qualified_with_known_failures",
        "policy": "qualified_known_failures", "policy_version": "g03-v1", "blockers": [],
        "warnings": [], "known_failures": [], "evidence_confidence": {},
        "evidence_set_checksum": "sha256:evidence", "sandbox_fingerprint": "sha256:sandbox",
        "execution_profile_checksum": "sha256:profile", "source_artifact_ids": [],
        "artifact_ids": [], "artifact_checksums": {}, "parity_binding": {},
        "state_version": 1, "event_sequence": 1,
    }
    try:
        with sessions() as session:
            session.add(BaselineAssessmentModel(
                id="assessment-old", idempotency_key="old", package_checksum="sha256:old",
                stale_reason="governed repair applied", created_at=NOW, updated_at=NOW, **common,
            ))
            session.add(G03ApprovalModel(
                id="g03-old", run_id="run-1", gate_id="G03", gate_version="g03-v1",
                idempotency_key="old-decision", actor="operator", status="modification_requested",
                decision="modification_requested", package_checksum="sha256:old",
                evidence_set_checksum="sha256:evidence", qualification_status="qualified_with_known_failures",
                policy_version="g03-v1", state_version=1, event_sequence=1,
                sandbox_fingerprint="sha256:sandbox", execution_profile_checksum="sha256:profile",
                package={}, artifact_ids=[], comment="repair test", created_at=NOW, updated_at=NOW,
            ))
            session.add(BaselineAssessmentModel(
                id="assessment-new", idempotency_key="new", package_checksum="sha256:new",
                stale_reason=None, created_at=NOW + timedelta(seconds=1),
                updated_at=NOW + timedelta(seconds=1), **common,
            ))
            session.commit()

        assert BaselineG03ApplicationService(scope=scope).get("run-1").g03_decision is None
    finally:
        engine.dispose()


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
