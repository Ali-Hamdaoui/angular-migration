"""Endpoint tests for the FastAPI skeleton."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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


def test_mock_migration_state_uses_shared_contracts() -> None:
    response = client.get("/migrations/mock-state")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "mock-run-angular-18-to-21"
    assert body["status"] == "WAITING_PLAN_APPROVAL"
    assert [stage["stage_id"] for stage in body["stages"]] == [
        "angular-18-to-19",
        "angular-19-to-20",
        "angular-20-to-21",
    ]
    assert body["validation_gates"][0]["status"] == "manual_validation_required"


def test_application_lifespan_verifies_database_connection() -> None:
    with TestClient(app) as lifespan_client:
        response = lifespan_client.get("/health")

    assert response.status_code == 200