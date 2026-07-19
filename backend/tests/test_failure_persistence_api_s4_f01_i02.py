"""Tests for S4-F01-I02: Failure evidence persistence, API, events, and artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.router import api_router
from app.domain.contracts import WorkflowEventType
from app.domain.failure import (
    DiagnosticParserType,
    FailureBuilderInput,
    FailureDiagnostic,
    FailureEvidence,
    FailureFingerprintService,
    FailureOrigin,
    FailureStatus,
)
from app.repositories.failure_repository import FailureRepository
from app.repositories.models import Base, MigrationRunModel, WorkflowEventModel
from app.repositories.models.workflow import FailureDiagnosticModel, FailureModel
from app.repositories.session import create_database_engine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_engine(tmp_path: Path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test-failures.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    session = sessionmaker(bind=db_engine, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def repo() -> FailureRepository:
    return FailureRepository()


@pytest.fixture
def sample_run(db_session):
    now = datetime.now(UTC)
    run = MigrationRunModel(
        id="run-001",
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
def sample_evidence() -> FailureEvidence:
    return FailureEvidence(
        failure_id="failure-001",
        run_id="run-001",
        stage_id="stage-001",
        execution_id="exec-001",
        failure_fingerprint="sha256:abc123" + "0" * 51,
        origin=FailureOrigin.MIGRATION_CAUSED,
        diagnostics=[
            FailureDiagnostic(
                message="Type 'X' is not assignable to type 'Y'",
                code="TS2322",
                file_path="src/app.component.ts",
                line_number=42,
                column=5,
                severity="error",
                parser_type=DiagnosticParserType.TYPESCRIPT,
                parser_confidence=0.9,
            ),
            FailureDiagnostic(
                message="npm ERR! code ERESOLVE",
                code="ERESOLVE",
                severity="error",
                parser_type=DiagnosticParserType.NPM,
                parser_confidence=0.95,
            ),
        ],
        workspace_fingerprint="sha256:workspace" + "0" * 51,
        status=FailureStatus.FINALIZED,
    )


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------


class TestFailureRepository:
    """Tests for FailureRepository persistence operations."""

    def test_save_and_retrieve_failure(
        self, db_session, repo, sample_run, sample_evidence
    ):
        """A saved failure can be retrieved by run_id and failure_id."""
        persisted = repo.save_failure(
            db_session, sample_evidence, "idem-001", state_version=1
        )
        db_session.commit()

        assert persisted.id == "failure-001"
        assert persisted.run_id == "run-001"
        assert persisted.origin == "migration_caused"
        assert persisted.status == "finalized"

        loaded = repo.get_failure(db_session, "run-001", "failure-001")
        assert loaded is not None
        assert loaded.id == "failure-001"
        # Verify stored JSON contains diagnostics
        parsed = json.loads(loaded.failure_json)
        assert len(parsed["diagnostics"]) == 2

    def test_get_failure_returns_none_for_missing(
        self, db_session, repo
    ):
        """get_failure returns None when no matching record exists."""
        loaded = repo.get_failure(db_session, "run-999", "failure-999")
        assert loaded is None

    def test_get_failures_by_run_returns_all(
        self, db_session, repo, sample_run
    ):
        """get_failures_by_run returns all failures for a run."""
        ev1 = FailureEvidence(
            failure_id="failure-a",
            run_id="run-001",
            stage_id="stage-001",
            execution_id="exec-001",
            failure_fingerprint="sha256:aaaa" + "0" * 52,
            origin=FailureOrigin.MIGRATION_CAUSED,
            diagnostics=[
                FailureDiagnostic(
                    message="error A",
                    severity="error",
                    parser_type=DiagnosticParserType.GENERIC,
                    parser_confidence=0.3,
                )
            ],
            workspace_fingerprint="sha256:w" + "0" * 53,
            status=FailureStatus.FINALIZED,
        )
        ev2 = FailureEvidence(
            failure_id="failure-b",
            run_id="run-001",
            stage_id="stage-001",
            execution_id="exec-002",
            failure_fingerprint="sha256:bbbb" + "0" * 52,
            origin=FailureOrigin.PRE_EXISTING_UNCHANGED,
            diagnostics=[
                FailureDiagnostic(
                    message="error B",
                    severity="warning",
                    parser_type=DiagnosticParserType.GENERIC,
                    parser_confidence=0.5,
                )
            ],
            workspace_fingerprint="sha256:w" + "0" * 53,
            status=FailureStatus.FINALIZED,
        )
        repo.save_failure(db_session, ev1, "idem-a", state_version=1)
        repo.save_failure(db_session, ev2, "idem-b", state_version=1)
        db_session.commit()

        all_failures = repo.get_failures_by_run(db_session, "run-001")
        assert len(all_failures) == 2
        assert all_failures[0].id == "failure-a"
        assert all_failures[1].id == "failure-b"

    def test_save_diagnostics(
        self, db_session, repo, sample_run, sample_evidence
    ):
        """Diagnostics are persisted and retrievable."""
        persisted = repo.save_failure(
            db_session, sample_evidence, "idem-diag", state_version=1
        )
        diag_models = repo.save_diagnostics(
            db_session, persisted.id, sample_evidence.diagnostics
        )
        db_session.commit()

        assert len(diag_models) == 2
        assert diag_models[0].failure_id == persisted.id
        assert diag_models[0].parser_type == "typescript"
        assert diag_models[1].parser_type == "npm"

        loaded_diags = repo.get_diagnostics(db_session, persisted.id)
        assert len(loaded_diags) == 2

    def test_idempotent_save_returns_existing(
        self, db_session, repo, sample_run, sample_evidence
    ):
        """Saving with the same idempotency key returns the existing record."""
        first = repo.save_failure(
            db_session, sample_evidence, "idem-key", state_version=1
        )
        second = repo.save_failure(
            db_session, sample_evidence, "idem-key", state_version=2
        )
        assert first.id == second.id
        assert first.run_id == second.run_id
        assert db_session.query(FailureModel).count() == 1


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest.fixture
def app(db_engine):
    """Create a FastAPI app with the shared engine for testing."""
    application = FastAPI()
    application.include_router(api_router)

    with patch("app.repositories.session.engine", db_engine):
        with patch("app.api.routes.failures.session_scope"):
            yield application


@pytest.fixture
def client(db_engine):
    """Test client backed by the in-memory SQLite database."""
    from app.repositories import session as session_module

    original_engine = session_module.engine

    application = FastAPI()
    application.include_router(api_router)

    # Override the module-level engine so session_scope uses our test DB
    with patch.object(session_module, "engine", db_engine):
        # Re-create SessionLocal bound to test engine
        test_session_local = sessionmaker(
            bind=db_engine, autocommit=False, autoflush=False, expire_on_commit=False
        )
        with patch.object(session_module, "SessionLocal", test_session_local):
            with TestClient(application) as c:
                yield c


class TestFailureEvidenceAPI:
    """Tests for the failure evidence API endpoints."""

    def test_capture_failure_evidence_success(
        self, client, db_engine
    ):
        """POST succeeds with valid input and returns 201."""
        # First create a run in the database
        session = sessionmaker(bind=db_engine, expire_on_commit=False)()
        now = datetime.now(UTC)
        session.add(
            MigrationRunModel(
                id="run-api-001",
                status="RUNNING",
                run_phase="STAGED_MIGRATION",
                state_version=1,
                source_version_family="18.x",
                target_version_family="21.x",
                source_version_detected="18.2.x",
                source_angular_version="18.x",
                target_angular_version="21.x",
                artifact_root="/tmp/artifacts/run-api-001",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
        session.close()

        payload = {
            "run_id": "run-api-001",
            "stage_id": "stage-001",
            "execution_id": "exec-001",
            "exit_code": 1,
            "stdout": "Build failed with errors",
            "stderr": "src/app.ts(42,5): error TS2323: Type error",
            "workspace_fingerprint": "sha256:" + "a" * 62,
            "idempotency_key": "capture-001",
            "baseline_artifact_ids": [],
            "expected_state_version": 1,
            "actor": "tester",
        }

        response = client.post(
            "/api/v1/runs/run-api-001/commands/cmd-001/failure-evidence",
            json=payload,
        )

        # Should succeed with 201
        assert response.status_code == 201, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["run_id"] == "run-api-001"
        assert data["failure_id"].startswith("failure-")
        assert data["origin"] == "migration_caused"
        assert data["status"] == "finalized"
        assert len(data["diagnostics"]) > 0

    def test_capture_failure_run_not_found(self, client):
        """POST returns 404 when run does not exist."""
        payload = {
            "run_id": "run-nonexistent",
            "stage_id": "stage-001",
            "execution_id": "exec-001",
            "stdout": "some error",
            "workspace_fingerprint": "sha256:" + "b" * 62,
            "idempotency_key": "capture-notfound",
            "baseline_artifact_ids": [],
            "expected_state_version": 1,
        }
        response = client.post(
            "/api/v1/runs/run-nonexistent/commands/cmd-001/failure-evidence",
            json=payload,
        )
        assert response.status_code == 404
        assert "RUN_NOT_FOUND" in response.text

    def test_get_failure_evidence_success(
        self, client, db_engine, sample_run, sample_evidence
    ):
        """GET returns the stored failure with diagnostics."""
        # Persist directly
        session = sessionmaker(bind=db_engine, expire_on_commit=False)()
        repo = FailureRepository()
        persisted = repo.save_failure(session, sample_evidence, "idem-get", state_version=1)
        repo.save_diagnostics(session, persisted.id, sample_evidence.diagnostics)
        session.commit()
        session.close()

        response = client.get(
            f"/api/v1/runs/run-001/failures/{persisted.id}"
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["failure_id"] == persisted.id
        assert data["origin"] == "migration_caused"
        assert len(data["diagnostics"]) == 2

    def test_get_failure_not_found(self, client):
        """GET returns 404 for a non-existent failure."""
        response = client.get(
            "/api/v1/runs/run-001/failures/failure-nonexistent"
        )
        assert response.status_code == 404
        assert "FAILURE_NOT_FOUND" in response.text
