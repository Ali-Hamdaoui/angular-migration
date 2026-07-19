"""Tests for S4-F02-I02: C-Lite failure routing persistence, API, events."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.domain.failure import FailureRoute
from app.domain.route import FailureRouteDecision
from app.repositories.models import Base, MigrationRunModel
from app.repositories.models.workflow import FailureAttemptModel, FailureRouteModel
from app.repositories.route_repository import RouteRepository
from app.repositories.session import create_database_engine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_engine(tmp_path: Path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test-routing.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    session = sessionmaker(bind=db_engine, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def repo() -> RouteRepository:
    return RouteRepository()


@pytest.fixture
def sample_run(db_session):
    now = datetime.now(UTC)
    run = MigrationRunModel(
        id="run-routing-001",
        status="RUNNING",
        run_phase="STAGED_MIGRATION",
        state_version=1,
        source_version_family="18.x",
        target_version_family="21.x",
        source_version_detected="18.2.x",
        source_angular_version="18.x",
        target_angular_version="21.x",
        created_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.flush()
    return run


@pytest.fixture
def sample_decision() -> FailureRouteDecision:
    return FailureRouteDecision(
        failure_id="failure-route-001",
        route=FailureRoute.CODE_OR_CONFIG_REPAIR,
        policy_version="c-lite-v1",
        decision_checksum="sha256:" + "a" * 64,
        actions=["fix type errors", "check tsconfig"],
        risk="medium",
    )


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------


class TestRouteRepository:
    """Tests for RouteRepository persistence operations."""

    def test_save_and_retrieve_route_decision(
        self, db_session, repo, sample_run, sample_decision
    ):
        """A saved route decision can be retrieved by run_id and failure_id."""
        persisted = repo.save_route_decision(
            db_session,
            "run-routing-001",
            "failure-route-001",
            sample_decision,
            "idem-route-001",
            state_version=1,
        )
        db_session.commit()

        assert persisted.failure_id == "failure-route-001"
        assert persisted.run_id == "run-routing-001"
        assert persisted.route == "CODE_OR_CONFIG_REPAIR"
        assert persisted.policy_version == "c-lite-v1"
        assert persisted.decision_checksum.startswith("sha256:")
        assert "fix type errors" in persisted.actions
        assert persisted.risk == "medium"
        assert persisted.state_version == 1
        assert persisted.idempotency_key == "idem-route-001"

        loaded = repo.get_route_decision(db_session, "run-routing-001", "failure-route-001")
        assert loaded is not None
        assert loaded.id == persisted.id
        assert loaded.route == "CODE_OR_CONFIG_REPAIR"

    def test_get_route_decision_returns_none_for_missing(
        self, db_session, repo
    ):
        """get_route_decision returns None when no matching record exists."""
        loaded = repo.get_route_decision(db_session, "run-999", "failure-999")
        assert loaded is None

    def test_save_and_retrieve_retry_attempt(
        self, db_session, repo, sample_run
    ):
        """A saved retry attempt can be retrieved by failure_id."""
        attempt = repo.save_retry_attempt(
            db_session,
            "run-routing-001",
            "failure-001",
            attempt_number=1,
            route="CODE_OR_CONFIG_REPAIR",
        )
        db_session.commit()

        assert attempt.failure_id == "failure-001"
        assert attempt.run_id == "run-routing-001"
        assert attempt.attempt_number == 1
        assert attempt.route == "CODE_OR_CONFIG_REPAIR"
        assert attempt.retry_count == 0
        assert attempt.status == "pending"
        assert attempt.max_retries == 3

        attempts = repo.get_attempts(db_session, "failure-001")
        assert len(attempts) == 1
        assert attempts[0].id == attempt.id

    def test_get_attempts_returns_empty_for_no_attempts(
        self, db_session, repo
    ):
        """get_attempts returns an empty list when no attempts exist."""
        attempts = repo.get_attempts(db_session, "failure-nonexistent")
        assert attempts == []

    def test_get_attempts_returns_multiple_ordered(
        self, db_session, repo, sample_run
    ):
        """get_attempts returns attempts ordered by attempt_number."""
        for i in range(1, 4):
            repo.save_retry_attempt(
                db_session,
                "run-routing-001",
                "failure-003",
                attempt_number=i,
                route="DEPENDENCY_REPAIR",
            )
        db_session.commit()

        attempts = repo.get_attempts(db_session, "failure-003")
        assert len(attempts) == 3
        assert [a.attempt_number for a in attempts] == [1, 2, 3]


# ---------------------------------------------------------------------------
# API tests — uses a minimal app with only the routing router to avoid
# the pre-existing import issue in app.api.routes.failures.
# ---------------------------------------------------------------------------


def _create_run(db_engine, run_id="run-routing-api-001"):
    """Helper to create a run, fully closes the session before returning."""
    session = sessionmaker(bind=db_engine, expire_on_commit=False)()
    try:
        now = datetime.now(UTC)
        session.add(
            MigrationRunModel(
                id=run_id,
                status="RUNNING",
                run_phase="STAGED_MIGRATION",
                state_version=1,
                source_version_family="18.x",
                target_version_family="21.x",
                source_version_detected="18.2.x",
                source_angular_version="18.x",
                target_angular_version="21.x",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    finally:
        session.close()


def _save_route(db_engine, run_id, failure_id, decision, idempotency_key, state_version=1):
    """Helper to persist a route decision, fully closes the session."""
    session = sessionmaker(bind=db_engine, expire_on_commit=False)()
    try:
        repo = RouteRepository()
        persisted = repo.save_route_decision(
            session, run_id, failure_id, decision, idempotency_key, state_version
        )
        session.commit()
        return persisted
    finally:
        session.close()


def _save_attempt(db_engine, run_id, failure_id, attempt_number, route):
    """Helper to persist a retry attempt, fully closes the session."""
    session = sessionmaker(bind=db_engine, expire_on_commit=False)()
    try:
        repo = RouteRepository()
        repo.save_retry_attempt(
            session, run_id, failure_id, attempt_number, route
        )
        session.commit()
    finally:
        session.close()


@pytest.fixture
def routing_app(db_engine):
    """Test app that only includes the routing router (avoids failures import issue)."""
    from app.api.routes.routing import router as routing_router

    application = FastAPI()
    application.include_router(routing_router)
    return application


@pytest.fixture
def api_client(db_engine, routing_app):
    """Test client backed by the in-memory SQLite database for routing endpoints only."""
    from app.repositories import session as session_module

    with patch.object(session_module, "engine", db_engine):
        test_session_local = sessionmaker(
            bind=db_engine, autocommit=False, autoflush=False, expire_on_commit=False
        )
        with patch.object(session_module, "SessionLocal", test_session_local):
            with TestClient(routing_app) as c:
                yield c


class TestFailureRoutingAPI:
    """Tests for the failure routing API endpoints."""

    # -- POST classify -------------------------------------------------------

    def test_classify_failure_success(self, api_client, db_engine):
        """POST classify succeeds with valid diagnostics and returns 201."""
        _create_run(db_engine)

        payload = {
            "diagnostics": [
                {
                    "message": "npm ERR! code ERESOLVE could not resolve dependency",
                    "severity": "error",
                    "parser_type": "npm",
                    "parser_confidence": 0.95,
                }
            ],
            "policy_version": "c-lite-v1",
            "idempotency_key": "classify-001",
            "expected_state_version": 1,
            "actor": "tester",
        }

        response = api_client.post(
            "/runs/run-routing-api-001/failures/failure-foo/classify",
            json=payload,
        )

        assert response.status_code == 201, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["failure_id"] == "failure-foo"
        assert data["route"] == "DEPENDENCY_REPAIR"
        assert data["policy_version"] == "c-lite-v1"
        assert data["decision_checksum"].startswith("sha256:")
        assert len(data["actions"]) > 0
        assert data["risk"] == "low"
        assert data["state_version"] == 1

    def test_classify_failure_unknown_route(self, api_client, db_engine):
        """POST classify returns UNKNOWN_DIAGNOSIS when no rule matches."""
        _create_run(db_engine)

        payload = {
            "diagnostics": [
                {
                    "message": "some completely unrecognized error no one has seen",
                    "severity": "error",
                    "parser_type": "generic",
                    "parser_confidence": 0.5,
                }
            ],
            "policy_version": "c-lite-v1",
            "idempotency_key": "classify-unknown",
            "expected_state_version": 1,
            "actor": "tester",
        }

        response = api_client.post(
            "/runs/run-routing-api-001/failures/failure-unknown/classify",
            json=payload,
        )

        assert response.status_code == 201, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["route"] == "UNKNOWN_DIAGNOSIS"
        assert data["risk"] == "medium"

    def test_classify_failure_run_not_found(self, api_client):
        """POST classify returns 404 when run does not exist."""
        payload = {
            "diagnostics": [
                {
                    "message": "npm ERR! code ERESOLVE",
                    "severity": "error",
                    "parser_type": "npm",
                    "parser_confidence": 0.95,
                }
            ],
            "policy_version": "c-lite-v1",
            "idempotency_key": "classify-nf",
            "expected_state_version": 1,
        }
        response = api_client.post(
            "/runs/run-nonexistent/failures/failure-001/classify",
            json=payload,
        )
        assert response.status_code == 404
        assert "RUN_NOT_FOUND" in response.text

    def test_classify_failure_invalid_diagnostics(self, api_client, db_engine):
        """POST classify returns 422 for malformed diagnostics (empty message)."""
        _create_run(db_engine)

        payload = {
            "diagnostics": [
                {
                    "message": "",
                    "severity": "error",
                    "parser_type": "generic",
                    "parser_confidence": 1.0,
                }
            ],
            "policy_version": "c-lite-v1",
            "idempotency_key": "classify-inv",
            "expected_state_version": 1,
        }
        response = api_client.post(
            "/runs/run-routing-api-001/failures/failure-001/classify",
            json=payload,
        )
        assert response.status_code == 422
        assert "INVALID_DIAGNOSTICS" in response.text

    # -- GET route -----------------------------------------------------------

    def test_get_route_decision_success(self, api_client, db_engine):
        """GET route returns the stored route decision."""
        _create_run(db_engine, "run-routing-002")
        _save_route(
            db_engine,
            "run-routing-002",
            "failure-route-002",
            FailureRouteDecision(
                failure_id="failure-route-002",
                route=FailureRoute.CODE_OR_CONFIG_REPAIR,
                policy_version="c-lite-v1",
                decision_checksum="sha256:" + "b" * 64,
                actions=["fix type errors"],
                risk="medium",
            ),
            "idem-get-route",
        )

        response = api_client.get(
            "/runs/run-routing-002/failures/failure-route-002/route"
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["failure_id"] == "failure-route-002"
        assert data["route"] == "CODE_OR_CONFIG_REPAIR"
        assert data["policy_version"] == "c-lite-v1"
        assert data["decision_checksum"].startswith("sha256:")

    def test_get_route_decision_not_found(self, api_client):
        """GET route returns 404 for a non-existent decision."""
        response = api_client.get(
            "/runs/run-001/failures/failure-nonexistent/route"
        )
        assert response.status_code == 404
        assert "ROUTE_NOT_FOUND" in response.text

    # -- POST retry ----------------------------------------------------------

    def test_retry_failure_success(self, api_client, db_engine):
        """POST retry succeeds and records the attempt."""
        _create_run(db_engine, "run-retry-001")
        _save_route(
            db_engine,
            "run-retry-001",
            "failure-retry-001",
            FailureRouteDecision(
                failure_id="failure-retry-001",
                route=FailureRoute.CODE_OR_CONFIG_REPAIR,
                policy_version="c-lite-v1",
                decision_checksum="sha256:" + "c" * 64,
                actions=["fix"],
                risk="medium",
            ),
            "idem-route-retry",
        )

        payload = {
            "idempotency_key": "retry-001",
            "actor": "tester",
        }
        response = api_client.post(
            "/runs/run-retry-001/failures/failure-retry-001/retry",
            json=payload,
        )

        assert response.status_code == 201, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["failure_id"] == "failure-retry-001"
        assert data["run_id"] == "run-retry-001"
        assert data["attempt_number"] == 1
        assert data["status"] == "pending"
        assert data["max_retries"] == 3

    def test_retry_failure_run_not_found(self, api_client):
        """POST retry returns 404 when run does not exist."""
        payload = {
            "idempotency_key": "retry-nf",
            "actor": "tester",
        }
        response = api_client.post(
            "/runs/run-nonexistent/failures/failure-001/retry",
            json=payload,
        )
        assert response.status_code == 404
        assert "RUN_NOT_FOUND" in response.text

    def test_retry_failure_max_retries_exceeded(self, api_client, db_engine):
        """POST retry returns 409 when max retries is exceeded."""
        _create_run(db_engine, "run-maxed-001")
        _save_route(
            db_engine,
            "run-maxed-001",
            "failure-maxed",
            FailureRouteDecision(
                failure_id="failure-maxed",
                route=FailureRoute.CODE_OR_CONFIG_REPAIR,
                policy_version="c-lite-v1",
                decision_checksum="sha256:" + "d" * 64,
                actions=["fix"],
                risk="medium",
            ),
            "idem-route-maxed",
        )
        # Create 3 attempts already (matching max_retries=3)
        for i in range(1, 4):
            _save_attempt(
                db_engine,
                "run-maxed-001",
                "failure-maxed",
                attempt_number=i,
                route="CODE_OR_CONFIG_REPAIR",
            )

        payload = {
            "idempotency_key": "retry-maxed",
            "actor": "tester",
        }
        response = api_client.post(
            "/runs/run-maxed-001/failures/failure-maxed/retry",
            json=payload,
        )
        assert response.status_code == 409
        assert "MAX_RETRIES_EXCEEDED" in response.text
