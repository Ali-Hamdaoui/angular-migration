"""S2-F01 verification: durable discovery evidence is authoritative and replayable."""

import asyncio
import json
from contextlib import contextmanager
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.discovery_contracts import DiscoveryCaptureRequest
from app.api.routes import discovery as discovery_routes
from app.api.routes import runs as runs_routes
from app.main import app
from app.repositories.models import ArtifactMetadataModel, Base, DiscoveryEvidenceModel, MigrationRunModel, WorkflowEventModel
from app.services.discovery_evidence_application_service import DiscoveryEvidenceApplicationService

NOW = datetime(2026, 7, 18, tzinfo=UTC)


def fixture(tmp_path):
    workspace = tmp_path / "source-snapshot"
    workspace.mkdir()
    (workspace / "package.json").write_text(json.dumps({"dependencies": {"@angular/core": "18.2.0"}, "scripts": {"test": "ng test"}}), encoding="utf-8")
    (workspace / "angular.json").write_text(json.dumps({"projects": {"app": {"projectType": "application", "architect": {"build": {"builder": "@angular-devkit/build-angular:application"}}}}}), encoding="utf-8")
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-1", status="CREATED", run_phase="DISCOVERY_BASELINE", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, artifact_root=str(tmp_path / "artifacts"), workspace_aliases={"SOURCE_SNAPSHOT": str(workspace)}, created_at=NOW, updated_at=NOW))
        session.add(ArtifactMetadataModel(id="metadata-baseline", run_id="run-1", stage_id=None, artifact_type="json", relative_path="baseline.json", checksum="sha256:baseline", created_at=NOW))
        session.commit()
    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()
    return scope, sessions, engine


def request(key="discovery-1", version=1, checksum="sha256:baseline"):
    return DiscoveryCaptureRequest(expected_state_version=version, idempotency_key=key, actor="operator", prerequisite_artifact_ids=["baseline"], prerequisite_artifact_checksums={"baseline": checksum})


def test_discovery_persists_immutable_evidence_events_and_idempotent_replay(tmp_path):
    scope, sessions, engine = fixture(tmp_path)
    service = DiscoveryEvidenceApplicationService(session_scope_factory=scope, now_provider=lambda: NOW)
    result = service.capture("run-1", request())
    assert service.capture("run-1", request()).idempotent_replay
    with sessions() as session:
        record = session.get(DiscoveryEvidenceModel, result.discovery_id)
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == "run-1").order_by(WorkflowEventModel.sequence)))
        assert record is not None and len(result.artifact_ids) == 5
        assert [event.event_type for event in events] == ["DISCOVERY_STARTED", *["SCANNER_COMPLETED"] * 5, "DISCOVERY_COMPLETED"]
        assert [event.sequence for event in events] == list(range(1, 8))
        assert all(value.startswith("sha256:") for value in result.artifact_checksums.values())
    engine.dispose()


def test_discovery_rejects_tampered_prerequisite_and_stale_state_before_events(tmp_path):
    scope, sessions, engine = fixture(tmp_path)
    service = DiscoveryEvidenceApplicationService(session_scope_factory=scope, now_provider=lambda: NOW)
    for payload, code in ((request("tampered", checksum="sha256:tampered"), "PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH"), (request("stale", version=2), "STALE_STATE_VERSION")):
        try:
            service.capture("run-1", payload)
        except Exception as error:
            assert getattr(error, "code") == code
        else:
            raise AssertionError(f"{code} was accepted")
    with sessions() as session:
        assert session.scalar(select(DiscoveryEvidenceModel)) is None
        assert session.scalar(select(WorkflowEventModel)) is None
    engine.dispose()


def test_discovery_versioned_api_and_sse_replay_expose_authoritative_events(monkeypatch, tmp_path):
    scope, _sessions, engine = fixture(tmp_path)
    app.dependency_overrides[discovery_routes.service] = lambda: DiscoveryEvidenceApplicationService(session_scope_factory=scope, now_provider=lambda: NOW)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/runs/run-1/discovery", json=request().model_dump(mode="json"))
            assert response.status_code == 200
            assert client.get("/api/v1/runs/run-1/discovery").json()["discovery_id"] == response.json()["discovery_id"]
        class Request:
            headers = {"last-event-id": "0"}; query_params = {}; calls = 0
            async def is_disconnected(self):
                self.calls += 1
                return self.calls > 1
        monkeypatch.setattr(runs_routes, "session_scope", scope)
        assert "event: DISCOVERY_STARTED" in asyncio.run(runs_routes.stream_run_events("run-1", Request()).body_iterator.__anext__())
    finally:
        app.dependency_overrides.pop(discovery_routes.service, None)
        engine.dispose()
