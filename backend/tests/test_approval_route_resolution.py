from fastapi.testclient import TestClient

from app.api.routes import analysis as analysis_routes
from app.api.routes import compatibility as compatibility_routes
from app.api.routes import g02 as g02_routes
from app.api.routes import planning_review as planning_review_routes
from app.main import app


CHECKSUM = "sha256:" + "a" * 64


class _G02Service:
    def decide(self, run_id, request):
        return {"run_id": run_id, "gate_id": "G02", "gate_version": "g02-v1", "status": "approved", "decision": "approve", "package": {}, "state_version": 2, "event_sequence": 2}


class _AnalysisService:
    def decide_g04(self, run_id, payload, actor):
        return {"run_id": run_id, "gate_id": "G04", "gate_version": "g04-v1", "decision": "approve", "status": "approved", "accepted": True, "package_checksum": CHECKSUM, "state_version": 2, "event_sequence": 2}


class _CompatibilityService:
    def decide_g05(self, run_id, payload, actor):
        return {"run_id": run_id, "gate_id": "G05", "gate_version": "g05-v1", "decision": "approve", "status": "approved", "accepted": True, "package_checksum": CHECKSUM, "artifact_set_checksum": CHECKSUM, "state_version": 2, "event_sequence": 2}


class _PlanningReviewService:
    def decide_g06(self, run_id, payload, actor):
        return {"run_id": run_id, "gate_id": "G06", "gate_version": "g06-v1", "decision": "approve", "status": "approved", "accepted": True, "package_checksum": CHECKSUM, "artifact_set_checksum": CHECKSUM, "plan_checksum": CHECKSUM, "stage_plan_checksum": CHECKSUM, "state_version": 2, "event_sequence": 2}


def _overrides():
    return {
        g02_routes.get_g02_service: lambda: _G02Service(),
        analysis_routes.get_service: lambda: _AnalysisService(),
        compatibility_routes.get_service: lambda: _CompatibilityService(),
        planning_review_routes.get_service: lambda: _PlanningReviewService(),
    }


def test_assembled_approval_routes_are_fixed_on_compatibility_and_versioned_surfaces():
    payloads = {
        "G02": {"expected_state_version": 1, "idempotency_key": "g02", "actor": "operator", "decision": "approved", "gate_id": "G02"},
        "G04": {"expected_state_version": 1, "idempotency_key": "g04", "gate_version": "g04-v1", "package_checksum": CHECKSUM, "decision": "approve"},
        "G05": {"expected_state_version": 1, "idempotency_key": "g05", "gate_version": "g05-v1", "package_checksum": CHECKSUM, "artifact_set_checksum": CHECKSUM, "decision": "approve"},
        "G06": {"expected_state_version": 1, "idempotency_key": "g06", "gate_version": "g06-v1", "package_checksum": CHECKSUM, "artifact_set_checksum": CHECKSUM, "plan_checksum": CHECKSUM, "stage_plan_checksum": CHECKSUM, "decision": "approve"},
    }
    with TestClient(app) as client:
        app.dependency_overrides.update(_overrides())
        try:
            for prefix in ("", "/api/v1"):
                for gate_id, payload in payloads.items():
                    response = client.post(f"{prefix}/runs/run-1/approvals/{gate_id}/decisions", json=payload)
                    assert response.status_code == 200, (prefix, gate_id, response.text)
                    assert response.json()["gate_id"] == gate_id
                unknown = client.post(f"{prefix}/runs/run-1/approvals/G07/decisions", json=payloads["G04"])
                assert unknown.status_code == 404
        finally:
            app.dependency_overrides.clear()
