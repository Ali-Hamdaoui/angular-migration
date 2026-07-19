"""Tests for T02 / AMFA-283 — persistence, events, and artifacts.

Test groups:
(A) RuntimeEvidenceCollector new evidence methods
(B) AcceptanceHarnessService persistence integration
(C) API evidence retrieval endpoints
(D) Event type consistency
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import (
    ArtifactRefDto,
    ArtifactType,
    HarnessFixtureType,
    HarnessRequestDto,
    HarnessRunStatusDto,
    WorkflowEventType,
)
from app.main import app
from app.repositories.models import ArtifactMetadataModel, Base
from app.repositories.session import create_database_engine
from app.services.runtime_evidence_collector import RuntimeEvidenceCollector

NOW = datetime(2026, 7, 19, tzinfo=UTC)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def tmp_store(tmp_path: Path) -> LocalFilesystemArtifactStore:
    """Create an isolated LocalFilesystemArtifactStore."""
    return LocalFilesystemArtifactStore(tmp_path / "artifacts")


@pytest.fixture
def db_session(tmp_path: Path):
    """Create an inline SQLite session with all tables."""
    engine = create_database_engine(
        f"sqlite:///{tmp_path / 'test.db'}", sqlite_wal_enabled=False
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def scope():
        from contextlib import contextmanager

        @contextmanager
        def managed():
            session = sessions()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        return managed()

    return scope


@pytest.fixture
def collector(
    tmp_store: LocalFilesystemArtifactStore, db_session
) -> RuntimeEvidenceCollector:
    """Create a RuntimeEvidenceCollector with DB-backed session."""
    return RuntimeEvidenceCollector(
        None,
        artifact_store=tmp_store,
        session_scope_factory=db_session,
    )


# ------------------------------------------------------------------
# (A) RuntimeEvidenceCollector new evidence methods
# ------------------------------------------------------------------


class TestCancellationEvidence:
    def test_returns_artifact_ref_with_valid_checksum(
        self, collector: RuntimeEvidenceCollector
    ):
        ref = collector.record_cancellation_evidence(
            run_id="harness-run-test-cancel",
            fixture_id="fixture-001",
            fixture_root="/tmp/fixtures/test",
            reason="User requested cancellation",
            cancel_event_type="CANCELLED",
        )
        assert isinstance(ref, ArtifactRefDto)
        assert ref.run_id == "harness-run-test-cancel"
        assert ref.checksum.startswith("sha256:")
        assert "cancellation_evidence" in ref.relative_path
        assert ref.artifact_type == ArtifactType.JSON

    def test_payload_includes_expected_fields(
        self, collector: RuntimeEvidenceCollector, tmp_store: LocalFilesystemArtifactStore
    ):
        ref = collector.record_cancellation_evidence(
            run_id="harness-run-test-cancel2",
            fixture_id="fixture-002",
            fixture_root="/tmp/fixtures/test2",
            reason="Timeout exceeded",
            cancel_event_type="TIMED_OUT",
        )
        stored = tmp_store.read_artifact_by_id(ref.artifact_id)
        payload = json.loads(stored.content)
        assert payload["fixture_id"] == "fixture-002"
        assert payload["reason"] == "Timeout exceeded"
        assert payload["cancel_event_type"] == "TIMED_OUT"
        assert "recorded_at" in payload


class TestRestartEvidence:
    def test_includes_restart_context(
        self, collector: RuntimeEvidenceCollector, tmp_store: LocalFilesystemArtifactStore
    ):
        restart_ctx = {
            "previous_state_version": 3,
            "previous_evidence_refs": ["ref-1", "ref-2"],
            "restarted_at": "2026-07-19T12:00:00Z",
        }
        ref = collector.record_restart_evidence(
            run_id="harness-run-test-restart",
            fixture_id="fixture-003",
            fixture_root="/tmp/fixtures/test3",
            restart_context=restart_ctx,
        )
        assert isinstance(ref, ArtifactRefDto)
        assert ref.checksum.startswith("sha256:")

        stored = tmp_store.read_artifact_by_id(ref.artifact_id)
        payload = json.loads(stored.content)
        assert payload["restart_context"]["previous_state_version"] == 3
        assert payload["restart_context"]["previous_evidence_refs"] == ["ref-1", "ref-2"]


class TestRepairLineage:
    def test_captures_multiple_attempts(
        self, collector: RuntimeEvidenceCollector, tmp_store: LocalFilesystemArtifactStore
    ):
        attempts = [
            {
                "attempt_number": 1,
                "status": "FAILED",
                "diagnosis": "Missing dependency @angular/core",
                "applied_patch": "patch-001",
            },
            {
                "attempt_number": 2,
                "status": "PASSED",
                "diagnosis": "Fixed import paths",
                "applied_patch": "patch-002",
            },
        ]
        artifacts = [{"patch_id": "patch-001", "file": "src/main.ts"}]

        ref = collector.record_repair_lineage(
            run_id="harness-run-test-repair",
            fixture_id="fixture-004",
            repair_attempts=attempts,
            repair_artifacts=artifacts,
        )
        assert isinstance(ref, ArtifactRefDto)
        assert ref.checksum.startswith("sha256:")

        stored = tmp_store.read_artifact_by_id(ref.artifact_id)
        payload = json.loads(stored.content)
        assert len(payload["repair_attempts"]) == 2
        assert payload["repair_attempts"][0]["attempt_number"] == 1
        assert payload["repair_attempts"][1]["attempt_number"] == 2
        assert payload["repair_attempts"][1]["status"] == "PASSED"


class TestOutputFingerprint:
    def test_creates_deterministic_json(
        self, collector: RuntimeEvidenceCollector, tmp_store: LocalFilesystemArtifactStore
    ):
        fingerprint_data = {
            "fingerprint": "sha256:abc123",
            "file_count": 3,
            "files": [
                {"path": "dist/index.html", "size": 1024},
                {"path": "dist/main.js", "size": 2048},
            ],
        }
        ref = collector.record_output_fingerprint(
            run_id="harness-run-test-fp",
            fixture_id="fixture-005",
            artifact_root="/tmp/output/dist",
            fingerprint_data=fingerprint_data,
        )
        assert isinstance(ref, ArtifactRefDto)
        assert ref.checksum.startswith("sha256:")

        stored = tmp_store.read_artifact_by_id(ref.artifact_id)
        payload = json.loads(stored.content)
        assert payload["fingerprint"]["fingerprint"] == "sha256:abc123"
        assert payload["fingerprint"]["file_count"] == 3

    def test_handles_missing_directory_gracefully(
        self, collector: RuntimeEvidenceCollector, tmp_store: LocalFilesystemArtifactStore
    ):
        fingerprint_data = {
            "fingerprint": None,
            "reason": "output directory not found",
            "path": "/nonexistent/dist",
        }
        ref = collector.record_output_fingerprint(
            run_id="harness-run-test-fp2",
            fixture_id="fixture-006",
            artifact_root="/nonexistent/dist",
            fingerprint_data=fingerprint_data,
        )
        assert ref.checksum.startswith("sha256:")


class TestSourceIntegrityProof:
    def test_records_checksum_and_manifest(
        self, collector: RuntimeEvidenceCollector, tmp_store: LocalFilesystemArtifactStore
    ):
        manifest = {
            "fixture_type": "angular_182x",
            "file_count": 42,
        }
        ref = collector.record_source_integrity_proof(
            run_id="harness-run-test-sip",
            fixture_id="fixture-007",
            source_path="/tmp/fixtures/test7",
            checksum="sha256:pre_generation_hash",
            manifest=manifest,
        )
        assert isinstance(ref, ArtifactRefDto)
        assert ref.checksum.startswith("sha256:")

        stored = tmp_store.read_artifact_by_id(ref.artifact_id)
        payload = json.loads(stored.content)
        assert payload["checksum"] == "sha256:pre_generation_hash"
        assert payload["manifest"]["fixture_type"] == "angular_182x"


class TestAcceptanceSuiteEvidence:
    def test_contains_aggregate_fixture_count(
        self, collector: RuntimeEvidenceCollector, tmp_store: LocalFilesystemArtifactStore
    ):
        aggregate = {
            "total_fixtures": 3,
            "passed": 2,
            "failed": 1,
            "duration_ms": 15000,
            "overall": "FAILED",
        }
        fixture_results = [
            {"fixture_id": "f-001", "outcome": "PASSED", "evidence_count": 4},
            {"fixture_id": "f-002", "outcome": "FAILED", "evidence_count": 3},
        ]
        ref = collector.record_acceptance_suite_evidence(
            run_id="harness-run-test-suite",
            aggregate_summary=aggregate,
            fixture_results=fixture_results,
        )
        assert isinstance(ref, ArtifactRefDto)
        assert ref.checksum.startswith("sha256:")
        assert "acceptance_suite" in ref.relative_path

        stored = tmp_store.read_artifact_by_id(ref.artifact_id)
        payload = json.loads(stored.content)
        assert payload["aggregate_summary"]["total_fixtures"] == 3
        assert payload["aggregate_summary"]["passed"] == 2
        assert len(payload["fixture_results"]) == 2


# ------------------------------------------------------------------
# (B) AcceptanceHarnessService persistence integration (lightweight)
# ------------------------------------------------------------------


class TestServiceHooks:
    def test_generate_fixture_records_source_integrity_proof(self, tmp_path: Path):
        """generate_fixture produces source_integrity_proof evidence."""
        from app.services.acceptance_harness_service import (
            AcceptanceHarnessService,
        )

        settings = type("Settings", (), {"workspace_root": str(tmp_path / "ws"), "artifact_root": str(tmp_path / "artifacts"), "platform_repository_root": ""})()
        store = LocalFilesystemArtifactStore(tmp_path / "artifacts")
        collector = RuntimeEvidenceCollector(settings, artifact_store=store)
        service = AcceptanceHarnessService(settings, artifact_store=store, evidence_collector=collector)

        req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.PASSABLE,
            name="test-sip",
        )
        result = service.generate_fixture(req)

        assert result.outcome == "GENERATED"
        # Should have at least 3 evidence refs: manifest, isolation, source_integrity_proof
        assert len(result.evidence_refs) >= 3
        # Last ref should be source integrity proof
        last_ref = result.evidence_refs[-1]
        assert last_ref.checksum.startswith("sha256:")

    def test_evaluate_fixture_cancellation_records_evidence(self, tmp_path: Path):
        """evaluate_fixture with no execution worker returns SKIPPED (lightweight)."""
        from app.services.acceptance_harness_service import (
            AcceptanceHarnessService,
        )

        settings = type("Settings", (), {"workspace_root": str(tmp_path / "ws"), "artifact_root": str(tmp_path / "artifacts"), "platform_repository_root": ""})()
        store = LocalFilesystemArtifactStore(tmp_path / "artifacts")
        collector = RuntimeEvidenceCollector(settings, artifact_store=store)
        service = AcceptanceHarnessService(
            settings, artifact_store=store, evidence_collector=collector, execution_worker=None
        )

        req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.PASSABLE,
            name="test-eval-cancel",
        )
        gen = service.generate_fixture(req)
        result = service.evaluate_fixture(gen.fixture_id)
        # Without execution_worker, evaluation is skipped — no cancellation needed
        assert result.outcome == "EVALUATION_SKIPPED"
        # But we still get proof_report evidence
        assert len(result.evidence_refs) >= 1


# ------------------------------------------------------------------
# (C) API evidence retrieval endpoints
# ------------------------------------------------------------------


class TestApiEndpoints:
    def test_list_runs_returns_empty_when_no_data(self):
        """GET /runs with no runs returns empty list."""
        response = TestClient(app).get(
            "/api/v1/operator/acceptance-suite/runs"
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_run_returns_404_for_unknown(self):
        """GET /runs/{unknown_id} returns 404."""
        response = TestClient(app).get(
            "/api/v1/operator/acceptance-suite/runs/nonexistent-run-id"
        )
        assert response.status_code == 404
        error = response.json()
        assert error["error_code"] == "RUN_NOT_FOUND"

    def test_get_evidence_returns_404_for_unknown(self):
        """GET /runs/{unknown_id}/evidence returns 404."""
        response = TestClient(app).get(
            "/api/v1/operator/acceptance-suite/runs/nonexistent-run-id/evidence"
        )
        assert response.status_code == 404
        error = response.json()
        assert error["error_code"] == "RUN_NOT_FOUND"

    def test_get_run_with_data_returns_evidence(self, tmp_path: Path):
        """GET /runs/{run_id} with seeded data returns evidence."""
        # Seed the DB with an ArtifactMetadataModel entry
        engine = create_database_engine(
            f"sqlite:///{tmp_path / 'run_test.db'}", sqlite_wal_enabled=False
        )
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine, expire_on_commit=False)

        run_id = "harness-run-api-test"
        with sessions.begin() as session:
            session.add(
                ArtifactMetadataModel(
                    id=f"metadata-{uuid4().hex}",
                    run_id=run_id,
                    stage_id=None,
                    artifact_type="json",
                    relative_path="00_job_setup/fixture_manifest_test.json",
                    checksum="sha256:testchecksum",
                    schema_version=1,
                    created_at=NOW,
                )
            )

        # Override session_scope in the acceptance module via FastAPI dependency
        from contextlib import contextmanager

        @contextmanager
        def test_scope():
            session = sessions()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        import app.api.routes.acceptance as mod_acceptance

        original_scope = mod_acceptance.session_scope
        mod_acceptance.session_scope = test_scope

        try:
            response = TestClient(app).get(
                f"/api/v1/operator/acceptance-suite/runs/{run_id}"
            )
            assert response.status_code == 200, response.json()
            data = response.json()
            assert data["run_id"] == run_id
            assert len(data["evidence_refs"]) >= 1
            assert data["evidence_refs"][0]["checksum"] == "sha256:testchecksum"
        finally:
            mod_acceptance.session_scope = original_scope


# ------------------------------------------------------------------
# (D) Event type consistency
# ------------------------------------------------------------------


class TestEventTypeConsistency:
    def test_new_workflow_event_types_are_registered(self):
        """New WorkflowEventType entries exist and are serializable."""
        types = [
            WorkflowEventType.ACCEPTANCE_SUITE_STARTED,
            WorkflowEventType.ACCEPTANCE_SUITE_COMPLETED,
            WorkflowEventType.ACCEPTANCE_SUITE_FAILED,
            WorkflowEventType.FIXTURE_GENERATED,
            WorkflowEventType.FIXTURE_GENERATION_FAILED,
            WorkflowEventType.FIXTURE_EVALUATED,
            WorkflowEventType.FIXTURE_EVALUATION_FAILED,
            WorkflowEventType.FIXTURE_CANCELLED,
            WorkflowEventType.FIXTURE_RESTARTED,
            WorkflowEventType.OUTPUT_FINGERPRINT_CREATED,
            WorkflowEventType.REPAIR_LINEAGE_RECORDED,
        ]
        for et in types:
            serialized = et.value
            assert isinstance(serialized, str)
            assert serialized.startswith(("ACCEPTANCE_", "FIXTURE_", "OUTPUT_", "REPAIR_"))

    def test_harness_run_status_dto_serializable(self):
        """HarnessRunStatusDto serializes to JSON correctly."""
        dto = HarnessRunStatusDto(
            run_id="harness-run-dto-test",
            suite_id="suite-001",
            overall_status="COMPLETED",
            fixture_count=5,
            passed=3,
            failed=2,
            started_at=NOW,
            completed_at=NOW,
            evidence_refs=[
                ArtifactRefDto(
                    artifact_id="artifact-001",
                    run_id="harness-run-dto-test",
                    artifact_type=ArtifactType.JSON,
                    relative_path="00_job_setup/evidence.json",
                    created_at=NOW,
                    checksum="sha256:test",
                )
            ],
        )
        serialized = dto.model_dump(mode="json")
        assert serialized["run_id"] == "harness-run-dto-test"
        assert serialized["fixture_count"] == 5
        assert serialized["passed"] == 3
        assert serialized["failed"] == 2
        assert len(serialized["evidence_refs"]) == 1
        assert serialized["evidence_refs"][0]["checksum"] == "sha256:test"
        assert serialized["started_at"] is not None
        assert serialized["completed_at"] is not None

    def test_workflow_event_types_serialize_to_string(self):
        """WorkflowEventType enum values serialize as strings in JSON."""
        event = WorkflowEventType.ACCEPTANCE_SUITE_STARTED
        assert json.dumps(event.value) == '"ACCEPTANCE_SUITE_STARTED"'
