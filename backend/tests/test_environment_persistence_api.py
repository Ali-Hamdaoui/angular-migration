from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes.environment import get_environment_service
from app.domain.system import (
    CorporateNetworkReadiness,
    EnvironmentCapabilityResult,
    EnvironmentCapabilitySnapshot,
    LocalStorageReadiness,
    RuntimeInventoryEntry,
)
from app.main import app
from app.repositories.environment_capability import EnvironmentCapabilityRepository
from app.repositories.models import Base
from app.services.environment_diagnostics_application_service import (
    EnvironmentDiagnosticsApplicationService,
)


def result() -> EnvironmentCapabilityResult:
    return EnvironmentCapabilityResult(
        snapshot=EnvironmentCapabilitySnapshot(
            snapshot_id="environment-test",
            captured_at=datetime(2026, 7, 14, tzinfo=UTC),
            policy_version="environment-readiness-v1",
            status="available",
            runtimes=[
                RuntimeInventoryEntry(
                    name=name,
                    executable=f"C:/tools/{name}.exe",
                    version="1.2.3",
                    installation_root="C:/tools",
                    status="available",
                )
                for name in ("node", "npm", "npx", "git", "python")
            ],
            node_npm_npx_paired=True,
            git_ready=True,
            python_ready=True,
            storage=LocalStorageReadiness(
                database_path="C:/state.db",
                artifact_root="C:/runs",
                writable=True,
                local_filesystem=True,
                free_bytes=1,
                status="available",
            ),
            network=CorporateNetworkReadiness(
                registry_configured=True,
                proxy_configured=False,
                https_proxy_configured=False,
                strict_ssl=True,
                custom_ca_configured=False,
            ),
            checksum="sha256:test",
        ),
        artifact={"summary": "artifact-summary"},
    )


def test_repository_persists_snapshot_and_durable_events(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'environment.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    repository = EnvironmentCapabilityRepository()

    @contextmanager
    def session_scope():
        with sessions() as session:
            yield session
            session.commit()

    with session_scope() as session:
        repository.save(
            session,
            result(),
            idempotency_key="refresh-1",
            actor="operator",
            now=datetime(2026, 7, 14, tzinfo=UTC),
        )

    with session_scope() as session:
        stored = repository.get_by_idempotency(session, "refresh-1")
        assert stored is not None
        assert repository.to_result(stored).snapshot.checksum == "sha256:test"
        assert len(stored.snapshot["runtimes"]) == 5


def test_application_service_returns_same_persisted_result_for_duplicate_idempotency(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'environment.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    calls = []

    @contextmanager
    def session_scope():
        with sessions() as session:
            yield session
            session.commit()

    class FakeCapabilityService:
        def diagnose(self, idempotency_key):
            calls.append(idempotency_key)
            return result()

    service = EnvironmentDiagnosticsApplicationService(
        SimpleNamespace(),
        capability_service=FakeCapabilityService(),
        session_scope_factory=session_scope,
    )
    request = SimpleNamespace(idempotency_key="refresh-1", actor="operator")
    first = service.refresh(request)
    second = service.refresh(request)

    assert first.snapshot.checksum == second.snapshot.checksum
    assert calls == ["refresh-1"]


def test_environment_routes_expose_typed_refresh_and_latest():
    class FakeEnvironmentService:
        def refresh(self, request):
            return result()

        def latest(self):
            return result()

    app.dependency_overrides[get_environment_service] = lambda: FakeEnvironmentService()
    try:
        with TestClient(app) as client:
            response = client.post("/environment/refresh", json={"idempotency_key": "route-1", "actor": "operator"})
            assert response.status_code == 200
            assert response.json()["snapshot"]["checksum"] == "sha256:test"

            latest = client.get("/environment/diagnostics")
            assert latest.status_code == 200
            assert latest.json()["snapshot"]["status"] == "available"
    finally:
        app.dependency_overrides.clear()
def test_refresh_request_rejects_whitespace_idempotency():
    from app.domain.system import RefreshEnvironmentRequest

    try:
        RefreshEnvironmentRequest(idempotency_key="   ")
    except ValidationError as exc:
        assert "idempotency_key" in str(exc)
    else:
        raise AssertionError("whitespace idempotency keys must be rejected")
