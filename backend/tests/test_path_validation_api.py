from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes.sources import get_path_validation_service
from app.domain.path_validation import PathRuleResult, PathValidationResult, PathValidationSnapshot
from app.main import app
from app.repositories.models import Base
from app.repositories.path_validation import PathValidationRepository
from app.services.path_validation_application_service import PathValidationApplicationService


def make_result():
    return PathValidationResult(snapshot=PathValidationSnapshot(
        validation_id="path-validation-test",
        captured_at=datetime(2026, 7, 14, tzinfo=UTC),
        policy_version="path-validation-v1",
        status="passed",
        source_path="C:/sources/app",
        target_output_path="C:/targets/out",
        source_fingerprint="sha256:source",
        rules=[PathRuleResult(code="SOURCE_OK", status="passed", message="ok")],
        target_reservation_eligible=True,
        checksum="sha256:path",
    ))


def test_path_validation_repository_and_idempotency(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paths.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    repository = PathValidationRepository()
    class FakeValidator:
        def __init__(self):
            self.calls = 0
        def validate(self, request):
            self.calls += 1
            return make_result()

    validator = FakeValidator()
    service = PathValidationApplicationService(SimpleNamespace(), validator=validator, session_scope_factory=scope)
    request = SimpleNamespace(idempotency_key="same-path-request", actor="operator")
    first = service.validate(request)
    second = service.validate(request)

    assert first.snapshot.checksum == second.snapshot.checksum
    assert validator.calls == 1

    with scope() as session:
        stored = repository.get_by_id(session, first.snapshot.validation_id)
        assert stored is not None
        assert repository.to_result(stored).snapshot.source_fingerprint == "sha256:source"


def test_path_validation_routes_use_typed_contracts():
    class FakeService:
        def validate(self, request):
            return make_result()
        def get(self, validation_id):
            return make_result()

    app.dependency_overrides[get_path_validation_service] = lambda: FakeService()
    try:
        with TestClient(app) as client:
            response = client.post("/sources/validate-paths", json={
                "source_path": "C:/sources/app",
                "target_output_path": "C:/targets/out",
                "idempotency_key": "route-path",
                "actor": "operator",
            })
            assert response.status_code == 200
            assert response.json()["snapshot"]["checksum"] == "sha256:path"
            assert client.get("/sources/path-validations/path-validation-test").status_code == 200
    finally:
        app.dependency_overrides.clear()