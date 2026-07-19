from fastapi.testclient import TestClient

from app.api.llm_contracts import LlmActivityResponse, LlmInvocationResponse, LlmReadinessResponse, LlmUsageResponse
from app.api.routes import llm as llm_routes
from app.main import app
from app.services.llm_evidence_application_service import LlmEvidenceError


def invocation() -> LlmInvocationResponse:
    return LlmInvocationResponse(invocation_id="llm-invocation-1", run_id="run-1", status="completed", role="phase_proposer", task_type="assistant_response", provider="azure_openai", deployment_alias="azure-openai", input_tokens=10, output_tokens=5, total_tokens=15, input_cost_usd=0.0000025, output_cost_usd=0.00001, total_cost_usd=0.0000125, retries=1, latency_ms=120, state_version=2, event_sequence=2)


class StubLlmService:
    def readiness(self):
        return LlmReadinessResponse(status="ready", deployment_configured=True, model_capability="responses_json_object")

    def smoke(self, request):
        return invocation()

    def activity(self, run_id):
        return LlmActivityResponse(run_id=run_id, invocations=[invocation()])

    def usage(self, run_id):
        return LlmUsageResponse(run_id=run_id, invocation_count=1, input_tokens=10, output_tokens=5, total_tokens=15, input_cost_usd=0.0000025, output_cost_usd=0.00001, total_cost_usd=0.0000125, pricing_versions=["mvp-pricing-2026-01"])


class RejectingLlmService(StubLlmService):
    def smoke(self, request):
        raise LlmEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409)


def test_llm_api_contract_exposes_readiness_smoke_activity_and_usage() -> None:
    app.dependency_overrides[llm_routes.get_service] = lambda: StubLlmService()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.get("/api/v1/llm/readiness").json()["status"] == "ready"
            smoke = client.post("/api/v1/llm/smoke", json={"run_id": "run-1", "expected_state_version": 1, "idempotency_key": "smoke-1"})
            assert smoke.status_code == 200
            assert smoke.json()["total_cost_usd"] == 0.0000125
            assert client.get("/api/v1/runs/run-1/llm/activity").json()["invocations"][0]["invocation_id"] == "llm-invocation-1"
            assert client.get("/api/v1/runs/run-1/usage").json()["total_tokens"] == 15
    finally:
        app.dependency_overrides.pop(llm_routes.get_service, None)


def test_llm_api_returns_stable_correlation_safe_errors_for_invalid_and_stale_requests() -> None:
    app.dependency_overrides[llm_routes.get_service] = lambda: RejectingLlmService()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            invalid = client.post("/api/v1/llm/smoke", headers={"x-correlation-id": "corr-invalid"}, json={"run_id": "run-1"})
            assert invalid.status_code == 422
            assert invalid.json()["error_code"] == "validation_error"
            assert invalid.json()["correlation_id"] == "corr-invalid"
            assert "api_key" not in invalid.text.lower()

            stale = client.post("/api/v1/llm/smoke", headers={"x-correlation-id": "corr-stale"}, json={"run_id": "run-1", "expected_state_version": 1, "idempotency_key": "stale-1"})
            assert stale.status_code == 409
            assert stale.json()["error_code"] == "STALE_STATE_VERSION"
            assert stale.headers["x-correlation-id"] == "corr-stale"
    finally:
        app.dependency_overrides.pop(llm_routes.get_service, None)
