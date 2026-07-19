"""Tests for G08 S4-F10 startup reconciliation service."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.repositories.models.base import Base
from app.repositories.models import (
    MigrationRunModel,
    WorkflowEventModel,
    WorkerLeaseModel,
    CommandExecutionModel,
    ArtifactMetadataModel,
    ReconciliationRunModel,
    ArtifactIntegrityFindingModel,
)
from app.services.reconciliation_service import (
    ReconciliationRequest,
    StartupReconciliationService,
)


@pytest.fixture
def in_memory_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def scope_factory(in_memory_session):
    @contextmanager
    def factory():
        yield in_memory_session
    return factory


@pytest.fixture
def settings():
    class FakeSettings:
        artifact_root = "/tmp/test-artifacts"
        platform_repository_root = "/tmp"
        worker_lease_seconds = 120
    return FakeSettings()


@pytest.fixture
def now():
    return datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def service(settings, scope_factory, now):
    svc = StartupReconciliationService(
        settings,
        session_scope_factory=scope_factory,
        now_provider=lambda: now,
        artifact_store=MagicMock(),
    )
    svc._artifact_store.ensure_run_layout = MagicMock()
    svc._artifact_store.write_text_artifact = MagicMock(
        side_effect=lambda *args, **kwargs: MagicMock(
            ref=MagicMock(
                artifact_id=f"test-artifact-{uuid4().hex[:8]}",
                artifact_type=MagicMock(value="json"),
                relative_path="reconciliation/test.json",
                checksum="sha256:abc123",
            )
        )
    )
    return svc


def _seed_run(session, run_id: str, status: str, state_version: int = 1):
    run = MigrationRunModel(
        id=run_id,
        status=status,
        run_phase="STAGED_MIGRATION",
        phase_status="running",
        state_version=state_version,
        created_at=datetime(2026, 7, 19, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 7, 19, 10, 0, 0, tzinfo=UTC),
    )
    session.add(run)
    session.flush()
    return run


class TestStartupReconciliationService:
    def test_execute_happy_path(self, service, in_memory_session, now):
        """Happy path: reconciliation runs and completes successfully."""
        result = service.execute(ReconciliationRequest(
            idempotency_key="test-key-001",
            actor="test-operator",
        ))

        assert result.status == "completed"
        assert result.stale_leases_found == 0
        assert result.interrupted_commands_found == 0
        assert result.artifact_mismatches_found == 0
        assert result.backend_instance_id.startswith("backend-")

    def test_execute_with_stale_leases(self, service, in_memory_session, now):
        """Reconciliation detects and expires stale leases."""
        lease = WorkerLeaseModel(
            id=f"lease-{uuid4().hex[:12]}",
            run_id="test-run",
            worker_id="worker-1",
            lease_owner="owner-1",
            acquired_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
        in_memory_session.add(lease)
        in_memory_session.flush()

        result = service.execute(ReconciliationRequest(
            idempotency_key="test-key-002",
            actor="test-operator",
        ))

        assert result.stale_leases_found == 1
        assert result.status == "completed"

    def test_execute_with_interrupted_commands(self, service, in_memory_session, now):
        """Reconciliation detects and marks interrupted commands."""
        cmd = CommandExecutionModel(
            id=f"cmd-{uuid4().hex[:12]}",
            run_id="test-run",
            executable="npm",
            arguments=["run", "build"],
            status="RUNNING",
            requested_at=now - timedelta(hours=1),
            state_version=1,
            event_sequence=1,
        )
        in_memory_session.add(cmd)
        in_memory_session.flush()

        result = service.execute(ReconciliationRequest(
            idempotency_key="test-key-003",
            actor="test-operator",
        ))

        assert result.interrupted_commands_found == 1
        assert cmd.status == "FAILED"
        assert cmd.reconstruction_required is True

    def test_idempotent_replay(self, service, in_memory_session, now):
        """Same idempotency key returns original result."""
        result1 = service.execute(ReconciliationRequest(
            idempotency_key="test-key-004",
            actor="test-operator",
        ))
        result2 = service.execute(ReconciliationRequest(
            idempotency_key="test-key-004",
            actor="test-operator",
        ))

        assert result1.reconciliation_id == result2.reconciliation_id
        assert result2.status == "completed"

    def test_get_latest_when_none(self, service, in_memory_session):
        """get_latest returns None when no reconciliation has run."""
        result = service.get_latest()
        assert result is None

    def test_get_latest_after_execution(self, service, in_memory_session, now):
        """get_latest returns the most recent reconciliation."""
        service.execute(ReconciliationRequest(
            idempotency_key="test-key-005",
            actor="test-operator",
        ))
        latest = service.get_latest()
        assert latest is not None
        assert latest.status == "completed"

    def test_recover_runs(self, service, in_memory_session, now):
        """Reconciliation recovers runs in recoverable states."""
        _seed_run(in_memory_session, "run-001", "RECOVERY_RUNNING")
        _seed_run(in_memory_session, "run-002", "WORKER_LOST")

        result = service.execute(ReconciliationRequest(
            idempotency_key="test-key-006",
            actor="test-operator",
        ))

        assert result.recovered_runs == 2
        assert result.status == "completed"

    def test_quarantine_runs(self, service, in_memory_session, now):
        """Reconciliation quarantines orphaned runs."""
        _seed_run(in_memory_session, "run-003", "ORPHANED")

        result = service.execute(ReconciliationRequest(
            idempotency_key="test-key-007",
            actor="test-operator",
        ))

        assert result.quarantined_runs == 1

    def test_artifact_integrity_check(self, service, in_memory_session, now):
        """Reconciliation detects orphaned artifacts."""
        artifact = ArtifactMetadataModel(
            id="metadata-test-artifact",
            run_id="nonexistent-run",
            artifact_type="json",
            relative_path="test.json",
            checksum="sha256:abc",
            created_at=now,
        )
        in_memory_session.add(artifact)
        in_memory_session.flush()

        result = service.execute(ReconciliationRequest(
            idempotency_key="test-key-008",
            actor="test-operator",
        ))

        assert result.artifact_mismatches_found == 1

    def test_graph_reconstruction(self, service, in_memory_session, now):
        """Reconstruction flag reflects run presence in DB."""
        _seed_run(in_memory_session, "run-004", "COMPLETED")

        result = service.execute(ReconciliationRequest(
            idempotency_key="test-key-009",
            actor="test-operator",
        ))

        assert result.graph_reconstructed is True
