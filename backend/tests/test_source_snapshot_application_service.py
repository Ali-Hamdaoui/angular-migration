from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.snapshot import CreateSourceSnapshotRequest, SnapshotStatus
from app.repositories.models import Base, MigrationRunModel, SourceSnapshotModel, WorkflowEventModel
from app.services.source_snapshot_application_service import (
    SnapshotApplicationError,
    SourceSnapshotApplicationService,
)
from app.snapshots import SnapshotIntegrityError, SnapshotService


def _service(tmp_path: Path, source: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshots.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    output = tmp_path / "output"
    snapshot_root = output / ".migration-factory" / "runs" / "run-1" / "source-snapshot"
    artifact_root = output / ".migration-factory" / "runs" / "run-1" / "artifacts"
    now = datetime.now(UTC)

    with sessions() as session:
        session.add(
            MigrationRunModel(
                id="run-1",
                status="CREATED",
                run_phase="PREFLIGHT_SNAPSHOT",
                phase_status="running",
                approval_status="approved",
                repair_status="not_required",
                state_version=1,
                source_path=str(source),
                resolved_output_root=str(output),
                run_root=str(output / ".migration-factory" / "runs" / "run-1"),
                artifact_root=str(artifact_root),
                workspace_aliases={"SOURCE_SNAPSHOT": str(snapshot_root)},
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    settings = SimpleNamespace(platform_repository_root=tmp_path / "platform")
    return (
        SourceSnapshotApplicationService(
            settings,
            session_scope_factory=scope,
            snapshot_service_factory=lambda root: SnapshotService(root),
        ),
        sessions,
        engine,
    )


def test_create_snapshot_persists_artifacts_events_and_replays_idempotently(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.ts").write_text("export const app = true;\n", encoding="utf-8")
    service, sessions, engine = _service(tmp_path, source)

    request = CreateSourceSnapshotRequest(
        expected_state_version=1,
        idempotency_key="snapshot-request-1",
        actor="operator",
    )
    result = service.create("run-1", request)
    replay = service.create("run-1", request)

    assert result.status is SnapshotStatus.CREATED
    assert len(result.artifacts) == 7
    assert replay.idempotent_replay is True
    assert replay.snapshot_id == result.snapshot_id
    assert result.state_version == 4
    assert result.event_sequence == 3

    with sessions() as session:
        snapshot = session.get(SourceSnapshotModel, result.snapshot_id)
        run = session.get(MigrationRunModel, "run-1")
        events = list(
            session.scalars(
                select(WorkflowEventModel)
                .where(WorkflowEventModel.run_id == "run-1")
                .order_by(WorkflowEventModel.sequence)
            )
        )
        assert snapshot is not None
        assert run.status == "SOURCE_VALIDATED"
        assert [event.event_type for event in events] == ["SNAPSHOT_STARTED", "SNAPSHOT_PROGRESS_UPDATED", "SNAPSHOT_CREATED"]
        assert {Path(ref.relative_path).name for ref in result.artifacts} == {
            "source_manifest.json",
            "source_git_metadata.json",
            "snapshot_manifest.json",
            "exclusion_policy_snapshot.json",
        "snapshot_copy_report.json",
        "snapshot_fingerprint.json",
        "source_validation_result.json",
        }

    inspected = service.get("run-1", result.snapshot_id)
    assert inspected is not None
    assert inspected.fingerprint == result.fingerprint
    engine.dispose()


def test_snapshot_rejects_stale_state_without_writing(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.ts").write_text("app", encoding="utf-8")
    service, sessions, engine = _service(tmp_path, source)

    with pytest.raises(SnapshotApplicationError) as error:
        service.create(
            "run-1",
            CreateSourceSnapshotRequest(
                expected_state_version=99,
                idempotency_key="stale-request",
                actor="operator",
            ),
        )

    assert error.value.code == "STALE_STATE_VERSION"
    with sessions() as session:
        assert session.query(SourceSnapshotModel).count() == 0
        assert session.query(WorkflowEventModel).count() == 0
    engine.dispose()

def test_snapshot_routes_expose_typed_post_and_get() -> None:
    from fastapi.testclient import TestClient

    from app.api.routes.snapshots import get_snapshot_service
    from app.main import app

    class FakeService:
        def create(self, run_id, request):
            return {
                "snapshot_id": "snapshot-1",
                "run_id": run_id,
                "status": "created",
                "source_path": "C:/source",
                "snapshot_path": "D:/output/.migration-factory/runs/run-1/source-snapshot/snapshot-1",
                "policy_version": "source-snapshot-policy-v1",
                "state_version": 3,
                "event_sequence": 2,
                "created_at": datetime.now(UTC).isoformat(),
            }

        def get(self, run_id, snapshot_id):
            return None

    app.dependency_overrides[get_snapshot_service] = lambda: FakeService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/runs/run-1/snapshots",
                json={
                    "expected_state_version": 1,
                    "idempotency_key": "route-snapshot-1",
                    "actor": "operator",
                },
            )
            assert response.status_code == 201
            assert response.json()["snapshot_id"] == "snapshot-1"
            assert client.get("/api/v1/runs/run-1/snapshots/missing").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_failed_snapshot_emits_quarantine_event_after_cleanup(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.ts").write_text("source changed", encoding="utf-8")
    service, sessions, engine = _service(tmp_path, source)

    class FailingSnapshotService:
        def create_snapshot(self, source_root: Path, snapshot_id: str):
            raise SnapshotIntegrityError("source changed while copying")

    service._snapshot_factory = lambda root: FailingSnapshotService()
    result = service.create(
        "run-1",
        CreateSourceSnapshotRequest(
            expected_state_version=1,
            idempotency_key="snapshot-failure-1",
            actor="operator",
        ),
    )

    assert result.status is SnapshotStatus.FAILED
    assert result.state_version == 5
    assert result.event_sequence == 4
    with sessions() as session:
        events = list(
            session.scalars(
                select(WorkflowEventModel)
                .where(WorkflowEventModel.run_id == "run-1")
                .order_by(WorkflowEventModel.sequence)
            )
        )
    assert [event.event_type for event in events] == [
        "SNAPSHOT_STARTED",
        "SNAPSHOT_PROGRESS_UPDATED",
        "SNAPSHOT_FAILED",
        "SNAPSHOT_QUARANTINED",
    ]
    engine.dispose()
