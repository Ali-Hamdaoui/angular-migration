from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.compatibility_contracts import G05DecisionRequest
from app.api.routes import compatibility as compatibility_routes
from app.main import app
from app.repositories.models import CompatibilityResolutionModel, G05ApprovalModel, WorkflowEventModel
from app.services.compatibility_evidence_application_service import CompatibilityEvidenceError, CompatibilityEvidenceApplicationService

from tests.test_compatibility_evidence_persistence_api_s2_f05_i02 import setup


def _decision(result, *, decision="approve"):
    return G05DecisionRequest(
        expected_state_version=result.state_version,
        idempotency_key="g05-verification-1",
        gate_version=result.gate_version,
        package_checksum=result.package_checksum,
        artifact_set_checksum=result.package["artifact_set_checksum"],
        workspace_fingerprint=result.package.get("workspace_fingerprint"),
        plan_version=result.package.get("plan_version"),
        decision=decision,
        comment="Verification decision" if decision == "approve_with_comment" else None,
    )


def test_invalid_api_input_returns_stable_error_without_calling_service(tmp_path):
    service, payload, sessions, _, _ = setup(tmp_path)
    app.dependency_overrides[compatibility_routes.get_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/runs/run-1/feasibility",
            headers={"x-authenticated-actor": "operator", "x-correlation-id": "corr-invalid"},
            json={**payload.model_dump(mode="json"), "registry_snapshot_checksum": "not-a-checksum"},
        )
    finally:
        app.dependency_overrides.pop(compatibility_routes.get_service, None)

    assert response.status_code == 422
    assert response.json()["error_code"] == "validation_error"
    assert response.json()["correlation_id"] == "corr-invalid"
    assert response.json()["details"]["errors"][0]["type"] == "string_pattern_mismatch"
    with sessions() as session:
        assert session.query(CompatibilityResolutionModel).count() == 0
        assert session.query(WorkflowEventModel).count() == 0


def test_provider_failure_fails_closed_without_partial_authoritative_mutation(tmp_path):
    service, payload, sessions, store, _ = setup(tmp_path)

    class FailingResolver:
        def resolve(self, request):
            raise RuntimeError("provider detail must not escape")

    failing_service = CompatibilityEvidenceApplicationService(
        session_scope_factory=service._scope,
        resolver=FailingResolver(),
        artifact_store_factory=service._artifact_store_factory,
    )
    with pytest.raises(CompatibilityEvidenceError) as error:
        failing_service.resolve("run-1", payload, "operator")
    assert error.value.code == "COMPATIBILITY_RESOLUTION_FAILED"
    assert "provider detail" not in error.value.message
    with sessions() as session:
        assert session.query(CompatibilityResolutionModel).count() == 0
        assert session.query(G05ApprovalModel).count() == 0
        assert session.query(WorkflowEventModel).count() == 0
    assert [path for path in Path(store._fixed_run_root).rglob("*.json") if not path.name.endswith(".meta.json")] == [Path(store._fixed_run_root) / "02_analysis" / "findings.json"]


def test_blocked_feasibility_cannot_create_g05_approval_and_pending_gate_blocks_progression(tmp_path):
    service, payload, sessions, _, _ = setup(tmp_path)
    with pytest.raises(CompatibilityEvidenceError) as missing:
        service.require_approved_g05("run-1", expected_state_version=1, workspace_fingerprint=None, plan_version=None, actor="operator")
    assert missing.value.code == "G05_APPROVAL_REQUIRED"

    blocked = service.resolve("run-1", payload.model_copy(update={"runtime_candidates": (), "idempotency_key": "blocked-1"}), "operator")
    assert blocked.status == "blocked"
    with pytest.raises(CompatibilityEvidenceError) as blocked_decision:
        service.decide_g05("run-1", _decision(blocked), "operator")
    assert blocked_decision.value.code == "G05_BLOCKED"
    with sessions() as session:
        assert session.query(G05ApprovalModel).count() == 1
        assert session.query(G05ApprovalModel).one().status == "blocked"


def test_tampered_package_is_rejected_before_g05_decision(tmp_path):
    service, payload, sessions, store, _ = setup(tmp_path)
    result = service.resolve("run-1", payload, "operator")
    package_path = Path(store._fixed_run_root) / store.read_artifact_by_id(result.artifact_ids[-1]).ref.relative_path
    package_path.write_text("tampered", encoding="utf-8")

    with pytest.raises(CompatibilityEvidenceError) as error:
        service.decide_g05("run-1", _decision(result), "operator")
    assert error.value.code == "G05_PACKAGE_INTEGRITY_FAILED"
    with sessions() as session:
        assert session.query(G05ApprovalModel).count() == 1
        assert session.query(G05ApprovalModel).one().status == "pending"
        assert session.query(WorkflowEventModel).count() == 2
