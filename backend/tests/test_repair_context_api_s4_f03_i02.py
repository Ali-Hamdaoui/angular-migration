"""Tests for S4-F03-I02: RepairContextPack persistence, API, events, and artifacts."""

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
    FailureDiagnostic,
    FailureEvidence,
    FailureOrigin,
    FailureStatus,
)
from app.domain.repair_context import (
    ContextSegment,
    ContextSegmentType,
    RepairContextPack,
    RepairContextStatus,
)
from app.repositories.failure_repository import FailureRepository
from app.repositories.models import Base, MigrationRunModel, WorkflowEventModel
from app.repositories.models.workflow import (
    FailureDiagnosticModel,
    FailureModel,
    RepairContextPackModel,
)
from app.repositories.repair_context_repository import RepairContextRepository
from app.repositories.session import create_database_engine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_engine(tmp_path: Path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test-repair-context.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    session = sessionmaker(bind=db_engine, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def repo() -> RepairContextRepository:
    return RepairContextRepository()


@pytest.fixture
def failure_repo() -> FailureRepository:
    return FailureRepository()


@pytest.fixture
def sample_run(db_session):
    now = datetime.now(UTC)
    run = MigrationRunModel(
        id="run-ctx-001",
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
def sample_failure(db_session, sample_run, failure_repo):
    evidence = FailureEvidence(
        failure_id="failure-ctx-001",
        run_id="run-ctx-001",
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
        ],
        workspace_fingerprint="sha256:workspace" + "0" * 51,
        status=FailureStatus.FINALIZED,
    )
    return failure_repo.save_failure(db_session, evidence, "idem-failure-ctx", state_version=1)


@pytest.fixture
def sample_context_pack() -> RepairContextPack:
    return RepairContextPack(
        context_pack_id="ctx-pack-001",
        failure_id="failure-ctx-001",
        stage_id="stage-001",
        repair_attempt=1,
        workspace_fingerprint="sha256:workspace" + "0" * 51,
        selection_policy_version="repair-selection-v1",
        sanitization_checksum="sha256:" + "a" * 62,
        content_checksum="sha256:" + "b" * 62,
        segments=[
            ContextSegment(
                segment_type=ContextSegmentType.FAILURE_EVIDENCE,
                content="Test diagnostic message",
                reason="Diagnostic test",
                checksum="sha256:" + "c" * 62,
                redacted=False,
            ),
        ],
        status=RepairContextStatus.FINALIZED,
    )


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------


class TestRepairContextRepository:
    """Tests for RepairContextRepository persistence operations."""

    def test_save_and_retrieve_context_pack(
        self, db_session, repo, sample_run, sample_failure, sample_context_pack
    ):
        """A saved context pack can be retrieved by run_id and ID."""
        persisted = repo.save_context_pack(
            db_session, sample_context_pack, "idem-ctx-001", state_version=1
        )
        db_session.commit()

        assert persisted.id == "ctx-pack-001"
        assert persisted.failure_id == "failure-ctx-001"
        assert persisted.status == "finalized"
        assert persisted.state_version == 1

        loaded = repo.get_context_pack(db_session, "run-ctx-001", "ctx-pack-001")
        assert loaded is not None
        assert loaded.id == "ctx-pack-001"
        # Verify stored JSON contains segments
        parsed = json.loads(loaded.context_json)
        assert len(parsed["segments"]) == 1
        assert parsed["selection_policy_version"] == "repair-selection-v1"

    def test_get_context_pack_returns_none_for_missing(
        self, db_session, repo
    ):
        """get_context_pack returns None when no matching record exists."""
        loaded = repo.get_context_pack(db_session, "run-999", "ctx-999")
        assert loaded is None

    def test_get_context_packs_by_failure(
        self, db_session, repo, sample_run, sample_failure
    ):
        """get_context_packs_by_failure returns all packs for a failure."""
        pack1 = RepairContextPack(
            context_pack_id="ctx-pack-a",
            failure_id="failure-ctx-001",
            stage_id="stage-001",
            repair_attempt=1,
            workspace_fingerprint="sha256:w" + "0" * 53,
            selection_policy_version="repair-selection-v1",
            sanitization_checksum="sha256:" + "d" * 62,
            content_checksum="sha256:" + "e" * 62,
            segments=[
                ContextSegment(
                    segment_type=ContextSegmentType.FAILURE_EVIDENCE,
                    content="Error A",
                    reason="test",
                    checksum="sha256:" + "f" * 62,
                ),
            ],
            status=RepairContextStatus.FINALIZED,
        )
        pack2 = RepairContextPack(
            context_pack_id="ctx-pack-b",
            failure_id="failure-ctx-001",
            stage_id="stage-001",
            repair_attempt=2,
            workspace_fingerprint="sha256:w" + "0" * 53,
            selection_policy_version="repair-selection-v1",
            sanitization_checksum="sha256:" + "g" * 62,
            content_checksum="sha256:" + "h" * 62,
            segments=[
                ContextSegment(
                    segment_type=ContextSegmentType.FAILURE_EVIDENCE,
                    content="Error B",
                    reason="test",
                    checksum="sha256:" + "i" * 62,
                ),
            ],
            status=RepairContextStatus.FINALIZED,
        )
        repo.save_context_pack(db_session, pack1, "idem-a", state_version=1)
        repo.save_context_pack(db_session, pack2, "idem-b", state_version=1)
        db_session.commit()

        all_packs = repo.get_context_packs_by_failure(db_session, "failure-ctx-001")
        assert len(all_packs) == 2
        assert all_packs[0].id == "ctx-pack-a"
        assert all_packs[1].id == "ctx-pack-b"

    def test_save_context_pack_idempotent(
        self, db_session, repo, sample_run, sample_failure, sample_context_pack
    ):
        """Saving with the same idempotency key returns the existing record."""
        first = repo.save_context_pack(
            db_session, sample_context_pack, "idem-same", state_version=1
        )
        second = repo.save_context_pack(
            db_session, sample_context_pack, "idem-same", state_version=2
        )
        assert first.id == second.id
        assert db_session.query(RepairContextPackModel).count() == 1


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest.fixture
def app(db_engine):
    """Create a FastAPI app with the shared engine for testing."""
    application = FastAPI()
    application.include_router(api_router)

    with patch("app.repositories.session.engine", db_engine):
        with patch("app.api.routes.repair_context.session_scope"):
            yield application


@pytest.fixture
def client(db_engine):
    """Test client backed by the in-memory SQLite database."""
    from app.repositories import session as session_module

    application = FastAPI()
    application.include_router(api_router)

    with patch.object(session_module, "engine", db_engine):
        test_session_local = sessionmaker(
            bind=db_engine, autocommit=False, autoflush=False, expire_on_commit=False
        )
        with patch.object(session_module, "SessionLocal", test_session_local):
            with TestClient(application) as c:
                yield c


class TestRepairContextAPI:
    """Tests for the repair context API endpoints."""

    def test_build_repair_context_success(
        self, client, db_engine
    ):
        """POST succeeds with valid input and returns 201."""
        # Create a run and failure in database
        session = sessionmaker(bind=db_engine, expire_on_commit=False)()
        now = datetime.now(UTC)
        run = MigrationRunModel(
            id="run-api-ctx-001",
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
        session.add(run)
        session.flush()

        # Add a failure
        failure_evidence = FailureEvidence(
            failure_id="failure-api-ctx-001",
            run_id="run-api-ctx-001",
            stage_id="stage-001",
            execution_id="exec-001",
            failure_fingerprint="sha256:abc123" + "0" * 51,
            origin=FailureOrigin.MIGRATION_CAUSED,
            diagnostics=[
                FailureDiagnostic(
                    message="Type error in app.component.ts",
                    code="TS2322",
                    file_path="src/app.component.ts",
                    line_number=42,
                    severity="error",
                    parser_type=DiagnosticParserType.TYPESCRIPT,
                    parser_confidence=0.9,
                ),
            ],
            workspace_fingerprint="sha256:workspace" + "0" * 51,
            status=FailureStatus.FINALIZED,
        )
        repo = FailureRepository()
        repo.save_failure(session, failure_evidence, "idem-api-ctx", state_version=1)
        session.commit()
        session.close()

        payload = {
            "failure_id": "failure-api-ctx-001",
            "stage_id": "stage-001",
            "repair_attempt": 1,
            "workspace_files": [
                {
                    "file_path": "src/app.component.ts",
                    "content": "import { Component } from '@angular/core';",
                }
            ],
            "token_budget": 32000,
            "idempotency_key": "build-ctx-001",
            "expected_state_version": 1,
            "actor": "tester",
        }

        response = client.post(
            "/api/v1/runs/run-api-ctx-001/failures/failure-api-ctx-001/repair-context",
            json=payload,
        )

        assert response.status_code == 201, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["run_id"] == "run-api-ctx-001"
        assert data["failure_id"] == "failure-api-ctx-001"
        assert data["status"] in ("finalized", "insufficient")
        assert len(data["segments"]) > 0
        assert data["context_pack_id"].startswith("ctx-")
        assert data["selection_policy_version"] == "repair-selection-v1"

    def test_build_repair_context_run_not_found(self, client):
        """POST returns 404 when run does not exist."""
        payload = {
            "failure_id": "failure-xyz",
            "stage_id": "stage-001",
            "repair_attempt": 1,
            "workspace_files": [],
            "idempotency_key": "build-notfound",
            "expected_state_version": 1,
        }
        response = client.post(
            "/api/v1/runs/run-nonexistent/failures/failure-xyz/repair-context",
            json=payload,
        )
        assert response.status_code == 404
        assert "RUN_NOT_FOUND" in response.text

    def test_build_repair_context_failure_not_found(self, client, db_engine):
        """POST returns 404 when failure does not exist."""
        session = sessionmaker(bind=db_engine, expire_on_commit=False)()
        now = datetime.now(UTC)
        run = MigrationRunModel(
            id="run-api-ctx-002",
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
        session.add(run)
        session.commit()
        session.close()

        payload = {
            "failure_id": "failure-nonexistent",
            "stage_id": "stage-001",
            "repair_attempt": 1,
            "workspace_files": [],
            "idempotency_key": "build-no-failure",
            "expected_state_version": 1,
        }
        response = client.post(
            "/api/v1/runs/run-api-ctx-002/failures/failure-nonexistent/repair-context",
            json=payload,
        )
        assert response.status_code == 404
        assert "FAILURE_NOT_FOUND" in response.text

    def test_get_repair_context_success(
        self, client, db_engine, sample_context_pack
    ):
        """GET returns the stored context pack."""
        # Persist directly
        session = sessionmaker(bind=db_engine, expire_on_commit=False)()
        repo = RepairContextRepository()

        # Need a run and failure first
        now = datetime.now(UTC)
        run = MigrationRunModel(
            id="run-ctx-get-001",
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
        session.add(run)
        session.flush()

        # Update the pack to reference the correct run
        pack_with_run = sample_context_pack.model_copy()
        # Restore failure and run references
        pack_with_run = RepairContextPack(
            context_pack_id="ctx-pack-get-001",
            failure_id="failure-get-ctx",
            stage_id="stage-001",
            repair_attempt=1,
            workspace_fingerprint="sha256:workspace" + "0" * 51,
            selection_policy_version="repair-selection-v1",
            sanitization_checksum="sha256:" + "j" * 62,
            content_checksum="sha256:" + "k" * 62,
            segments=[
                ContextSegment(
                    segment_type=ContextSegmentType.FAILURE_EVIDENCE,
                    content="GET test diagnostic",
                    reason="GET test",
                    checksum="sha256:" + "l" * 62,
                ),
            ],
            status=RepairContextStatus.FINALIZED,
        )
        persisted = repo.save_context_pack(session, pack_with_run, "idem-get-ctx", state_version=1)
        session.commit()
        session.close()

        response = client.get(
            f"/api/v1/runs/run-ctx-get-001/repair-contexts/{persisted.id}"
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert data["context_pack_id"] == persisted.id
        assert data["status"] == "finalized"
        assert len(data["segments"]) == 1

    def test_get_repair_context_not_found(self, client):
        """GET returns 404 for a non-existent context pack."""
        response = client.get(
            "/api/v1/runs/run-001/repair-contexts/ctx-nonexistent"
        )
        assert response.status_code == 404
        assert "CONTEXT_NOT_FOUND" in response.text
