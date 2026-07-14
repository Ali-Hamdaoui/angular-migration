"""Endpoint tests for the FastAPI skeleton."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.api.routes.migrations import get_service
from app.domain.contracts import PreflightResultDto
from app.main import app
from app.services.mock_migration_api_service import EXPIRED_PREFLIGHT_CHECKSUM, MockMigrationApiService

client = TestClient(app)


class FakePreflightService:
    checksum = "sha256:route-test-preflight"

    def validate(self, request):
        return PreflightResultDto(
            preflight_id="preflight-route-test",
            checksum=self.checksum,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
            source_path=request.source_path,
            target_output_path=request.target_output_path,
            status="passed",
            message="Route test preflight passed.",
        )

    def is_current_and_runnable(self, checksum: str) -> bool:
        return checksum == self.checksum


def _override_service(fake: FakePreflightService) -> None:
    app.dependency_overrides[get_service] = lambda: MockMigrationApiService(preflight_service=fake)


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_returns_application_metadata() -> None:
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {
        "name": "AI Frontend Migration Factory API",
        "version": "0.1.0",
        "environment": "development",
    }


def test_openapi_exposes_sprint0_route_shells() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    expected_paths = {
        "/health",
        "/version",
        "/migrations/preflight",
        "/migrations/mock",
        "/migrations/{run_id}/state",
        "/migrations/{run_id}/events",
        "/migrations/{run_id}/approvals",
        "/migrations/{run_id}/approval-policy",
        "/migrations/{run_id}/cancel",
        "/migrations/{run_id}/resume",
        "/migrations/{run_id}/artifacts",
        "/migrations/{run_id}/artifacts/{artifact_path}",
        "/artifacts/{artifact_id}",
        "/assistant/messages",
    }
    assert expected_paths.issubset(paths.keys())
    assert "/api/v1/migrations/{run_id}/state" in paths
    assert "/api/v1/health" in paths


def test_preflight_returns_checksum_bound_result() -> None:
    fake = FakePreflightService()
    _override_service(fake)
    try:
        response = client.post(
            "/migrations/preflight",
            json={
                "source_path": "C:/fixtures/angular-18-app",
                "target_output_path": "C:/tmp/angular-migration-output",
                "target_angular_family": "21.x",
                "migration_mode": "strict-functional-parity",
            },
        )
    finally:
        _clear_overrides()
    assert response.status_code == 200
    body = response.json()
    assert body["checksum"] == fake.checksum
    assert body["status"] == "passed"


def test_create_mock_run_rejects_missing_preflight_checksum_with_error_envelope() -> None:
    response = client.post(
        "/migrations/mock",
        json={},
        headers={"x-correlation-id": "test-correlation-id"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "validation_error"
    assert body["correlation_id"] == "test-correlation-id"
    assert "errors" in body["details"]


def test_create_mock_run_rejects_mismatched_preflight_checksum() -> None:
    response = client.post(
        "/migrations/mock",
        json={"preflight_checksum": "wrong-checksum"},
        headers={"x-correlation-id": "test-correlation-id"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body == {
        "error_code": "preflight_checksum_invalid",
        "message": "Create mock migration requires a valid preflight checksum.",
        "correlation_id": "test-correlation-id",
        "details": {},
    }


def test_create_mock_run_rejects_expired_preflight_checksum() -> None:
    response = client.post("/migrations/mock", json={"preflight_checksum": EXPIRED_PREFLIGHT_CHECKSUM})
    assert response.status_code == 400
    assert response.json()["error_code"] == "preflight_checksum_expired"


def test_create_mock_run_accepts_valid_preflight_checksum() -> None:
    fake = FakePreflightService()
    _override_service(fake)
    try:
        response = client.post("/migrations/mock", json={"preflight_checksum": fake.checksum})
    finally:
        _clear_overrides()
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "mock-run-angular-18-to-21"
    assert body["status"] == "WAITING"
    assert body["phase_status"] == "running"
    assert body["approval_status"] == "not_required"
    assert body["repair_status"] == "not_required"


def test_mock_migration_state_uses_shared_contracts() -> None:
    response = client.get("/migrations/mock-state")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "mock-run-angular-18-to-21"
    assert body["status"] == "WAITING"
    assert body["phase_status"] == "running"
    assert body["approval_status"] == "not_required"
    assert body["repair_status"] == "not_required"
    assert [stage["stage_id"] for stage in body["stages"]] == [
        "angular-18-to-19",
        "angular-19-to-20",
        "angular-20-to-21",
    ]
    assert body["validation_gates"][0]["status"] == "manual_validation_required"
    assert body["delivery"]["status"] == "not_published"


def test_state_endpoint_returns_backend_snapshot_for_run_id() -> None:
    response = client.get("/migrations/custom-run/state")
    assert response.status_code == 200
    assert response.json()["run_id"] == "custom-run"


def test_cancel_and_resume_are_idempotent_shells() -> None:
    first_cancel = client.post("/migrations/mock-run/cancel")
    second_cancel = client.post("/migrations/mock-run/cancel")
    resume = client.post("/migrations/mock-run/resume")

    assert first_cancel.status_code == 200
    assert second_cancel.status_code == 200
    assert first_cancel.json() == second_cancel.json()
    assert first_cancel.json()["idempotent"] is True
    assert resume.json()["operation"] == "resume"
    assert resume.json()["idempotent"] is True


def test_approval_policy_and_assistant_shells() -> None:
    policy = client.put(
        "/migrations/mock-run/approval-policy",
        json={"auto_approval_enabled": True, "actor": "tester"},
    )
    assistant = client.post(
        "/assistant/messages",
        json={"run_id": "mock-run", "message": "What is waiting?"},
    )

    assert policy.status_code == 409
    assert policy.json()["error_code"] == "AUTO_APPROVAL_NOT_ALLOWED"
    assert assistant.status_code == 200
    assert assistant.json()["status"] == "mock_unavailable"


def test_application_lifespan_verifies_database_connection() -> None:
    with TestClient(app) as lifespan_client:
        response = lifespan_client.get("/health")

    assert response.status_code == 200

def test_versioned_production_auto_approval_is_rejected() -> None:
    response = client.put(
        "/api/v1/migrations/mock-run/approval-policy",
        json={"auto_approval_enabled": True, "actor": "tester"},
        headers={"x-correlation-id": "auto-approval-test"},
    )
    assert response.status_code == 409
    assert response.json() == {
        "error_code": "AUTO_APPROVAL_NOT_ALLOWED",
        "message": "Production auto-approval is disabled; submit an explicit human decision.",
        "correlation_id": "auto-approval-test",
        "details": {},
    }