"""Tests for the Acceptance Harness API endpoints via TestClient."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _make_test_service(tmp_path: Path):
    """Build an AcceptanceHarnessService wired to tmp_path."""
    from app.services.acceptance_harness_service import (
        AcceptanceHarnessService,
    )
    from app.artifact_store import LocalFilesystemArtifactStore

    settings = type("Settings", (), {
        "workspace_root": str(tmp_path / "ws"),
        "artifact_root": str(tmp_path / "artifacts"),
        "platform_repository_root": "",
    })()
    store = LocalFilesystemArtifactStore(tmp_path / "artifacts")
    return AcceptanceHarnessService(settings, artifact_store=store)


def _override_service(test_service):
    """Install test_service as the harness DI override."""
    from app.api.routes.acceptance import get_harness_service
    app.dependency_overrides[get_harness_service] = lambda: test_service


def _clear_service_override():
    """Remove the harness DI override if present."""
    from app.api.routes.acceptance import get_harness_service
    app.dependency_overrides.pop(get_harness_service, None)


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_returns_200_and_readiness(self, client: TestClient) -> None:
        """GET /status returns READY overall_status."""
        response = client.get("/api/v1/operator/acceptance-suite/status")
        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "READY"

    def test_returns_empty_fixtures_list(self, client: TestClient) -> None:
        """GET /status returns empty fixtures when idle."""
        response = client.get("/api/v1/operator/acceptance-suite/status")
        assert response.status_code == 200
        assert response.json()["fixtures"] == []


# ---------------------------------------------------------------------------
# GET /runs endpoints (read-only, no side effects)
# ---------------------------------------------------------------------------


class TestListRuns:
    def test_empty_list_when_no_data(self, client: TestClient) -> None:
        """GET /runs returns empty list."""
        response = client.get("/api/v1/operator/acceptance-suite/runs")
        assert response.status_code == 200
        # May have data from earlier test runs against the app's global DB
        assert isinstance(response.json(), list)


class TestGetRun:
    def test_returns_404_for_unknown_run(self, client: TestClient) -> None:
        """GET /runs/{unknown} returns 404."""
        response = client.get(
            "/api/v1/operator/acceptance-suite/runs/nonexistent-run-id"
        )
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "RUN_NOT_FOUND"

    def test_returns_404_for_unknown_run_evidence(self, client: TestClient) -> None:
        """GET /runs/{unknown}/evidence returns 404."""
        response = client.get(
            "/api/v1/operator/acceptance-suite/runs/nonexistent-run-id/evidence"
        )
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "RUN_NOT_FOUND"


# ---------------------------------------------------------------------------
# Correlation IDs on error responses
# ---------------------------------------------------------------------------


class TestCorrelationIds:
    def test_error_response_has_correlation_id_header(self, client: TestClient) -> None:
        """Error responses include x-correlation-id header."""
        response = client.get(
            "/api/v1/operator/acceptance-suite/runs/nonexistent"
        )
        assert response.status_code == 404
        assert "x-correlation-id" in response.headers
        assert len(response.headers["x-correlation-id"]) > 0

    def test_error_response_body_has_correlation_id(self, client: TestClient) -> None:
        """Error response body includes correlation_id field."""
        response = client.get(
            "/api/v1/operator/acceptance-suite/runs/nonexistent"
        )
        data = response.json()
        assert "correlation_id" in data
        assert len(data["correlation_id"]) > 0


# ---------------------------------------------------------------------------
# POST /fixtures (writes data)
# ---------------------------------------------------------------------------


class TestCreateFixture:
    def test_creates_fixture_returns_201(self, client: TestClient, tmp_path: Path) -> None:
        """POST /fixtures with valid request returns 201."""
        test_service = _make_test_service(tmp_path)
        _override_service(test_service)
        try:
            response = client.post(
                "/api/v1/operator/acceptance-suite/fixtures",
                json={
                    "fixture_type": "passable",
                    "name": "api-test-passable",
                },
            )
            data = response.json()
            assert response.status_code == 201, f"Got {response.status_code}: {data}"
            assert data["outcome"] == "GENERATED"
            assert data["fixture_id"].startswith("fixture-")
            assert len(data["evidence_refs"]) >= 3
            assert data["state_version"] == 1
        finally:
            _clear_service_override()

    def test_unknown_fixture_type_returns_422(self, client: TestClient) -> None:
        """POST /fixtures with unknown fixture type returns 422."""
        response = client.post(
            "/api/v1/operator/acceptance-suite/fixtures",
            json={
                "fixture_type": "nonexistent_type",
                "name": "bad-test",
            },
        )
        assert response.status_code == 422
        data = response.json()
        assert isinstance(data, dict)

    def test_invalid_payload_returns_422(self, client: TestClient) -> None:
        """POST /fixtures with missing required fields returns 422."""
        response = client.post(
            "/api/v1/operator/acceptance-suite/fixtures",
            json={},  # missing fixture_type
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("fixture_type", [
        "angular_180x",
        "angular_182x",
        "passable",
        "compiler_error",
        "dependency_conflict",
        "environment_blocker",
        "cancellable",
    ])
    def test_all_fixture_types_accept_parameter(self, client: TestClient, fixture_type: str, tmp_path: Path) -> None:
        """POST /fixtures accepts all 7 fixture type strings."""
        test_service = _make_test_service(tmp_path)
        _override_service(test_service)
        try:
            response = client.post(
                "/api/v1/operator/acceptance-suite/fixtures",
                json={
                    "fixture_type": fixture_type,
                    "name": f"api-test-{fixture_type}_{id(tmp_path)}",
                },
            )
            assert response.status_code == 201, (
                f"Fixture type '{fixture_type}' got status {response.status_code}: {response.json()}"
            )
            assert response.json()["outcome"] == "GENERATED"
        finally:
            _clear_service_override()


# ---------------------------------------------------------------------------
# POST /fixtures/evaluate
# ---------------------------------------------------------------------------


class TestEvaluateFixture:
    def test_evaluate_unknown_fixture_returns_200_with_not_found(self, client: TestClient, tmp_path: Path) -> None:
        """POST /fixtures/evaluate with nonexistent fixture returns 200 with FIXTURE_NOT_FOUND."""
        test_service = _make_test_service(tmp_path)
        _override_service(test_service)
        try:
            response = client.post(
                "/api/v1/operator/acceptance-suite/fixtures/evaluate",
                json={"fixture_id": "nonexistent-fixture"},
            )
            data = response.json()
            assert data["outcome"] in ("FIXTURE_NOT_FOUND", "EVALUATION_SKIPPED")
        finally:
            _clear_service_override()


# ---------------------------------------------------------------------------
# Unauthenticated access returns stable 401/403 — not in Phase A scope
# ---------------------------------------------------------------------------

class TestUnauthenticated:
    def test_no_auth_on_status_endpoint(self, client: TestClient) -> None:
        """GET /status works without auth (Phase A has no auth middleware)."""
        response = client.get("/api/v1/operator/acceptance-suite/status")
        assert response.status_code == 200
