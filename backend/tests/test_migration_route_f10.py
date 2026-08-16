"""Tests for F10 dynamic source target routing."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from fastapi.testclient import TestClient

from app.domain.migration_route import validate_envelope
from app.main import app
from app.repositories.models import MigrationRunModel
from app.repositories.session import session_scope
from app.services.migration_route_service import MigrationRouteError, MigrationRouteService


NOW = datetime.now(UTC)
client = TestClient(app)


def test_envelope_validation():
    assert validate_envelope(11, 21) is None
    assert validate_envelope(18, 19) is None
    assert validate_envelope(10, 21) == "SOURCE_OUT_OF_ENVELOPE:10"
    assert validate_envelope(11, 22) == "TARGET_OUT_OF_ENVELOPE:22"
    assert validate_envelope(19, 18) == "ROUTE_DIRECTION_INVALID:19->18"
    assert validate_envelope(18, 18) == "ROUTE_DIRECTION_INVALID:18->18"


def test_compute_adjacent_major_chain():
    service = MigrationRouteService()
    route = service.compute(11, 13)
    assert route.source_major == 11
    assert route.target_major == 13
    assert len(route.stages) == 2
    assert route.stages[0].source_major == 11 and route.stages[0].target_major == 12
    assert route.stages[1].source_major == 12 and route.stages[1].target_major == 13
    assert route.checksum.startswith("sha256:")


def test_compute_route_is_deterministic():
    service = MigrationRouteService()
    first = service.compute(18, 21)
    second = service.compute(18, 21)
    assert first.checksum == second.checksum
    assert first.model_dump() == second.model_dump()


def test_compute_out_of_envelope_raises():
    service = MigrationRouteService()
    with pytest.raises(MigrationRouteError) as exc:
        service.compute(9, 12)
    assert exc.value.code == "ENVELOPE_VIOLATION"


def test_compute_full_11_21_chain():
    service = MigrationRouteService()
    route = service.compute(11, 21)
    assert len(route.stages) == 10
    assert [s.target_major for s in route.stages] == list(range(12, 22))


def test_compute_for_run_and_persist():
    run_id = f"run-f10-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      source_version_family="angular-14.x", target_version_family="angular-17.x",
                                      created_at=NOW, updated_at=NOW))
        session.commit()
    service = MigrationRouteService()
    route = service.compute_for_run(run_id)
    assert route.source_major == 14 and route.target_major == 17
    record = service.persist(run_id, route, actor="test")
    assert record.checksum == route.checksum
    assert len(record.stages) == 3
    # idempotent
    again = service.persist(run_id, route, actor="test")
    assert again.id == record.id


def test_validate_route_detects_drift():
    run_id = f"run-f10-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      source_version_family="angular-14.x", target_version_family="angular-17.x",
                                      created_at=NOW, updated_at=NOW))
        session.commit()
    service = MigrationRouteService()
    route = service.compute_for_run(run_id)
    service.persist(run_id, route)
    validated = service.validate_route(run_id)
    assert validated.checksum == route.checksum

    # drift: change the run's target family
    with session_scope() as session:
        run = session.get(MigrationRunModel, run_id)
        run.target_version_family = "angular-18.x"
        session.commit()
    with pytest.raises(MigrationRouteError) as exc:
        service.validate_route(run_id)
    assert exc.value.code == "ROUTE_DRIFT"


def test_route_api_compute():
    response = client.post("/routes/compute", json={"source_major": 11, "target_major": 14})
    assert response.status_code == 200
    body = response.json()
    assert body["source_major"] == 11 and body["target_major"] == 14
    assert len(body["stages"]) == 3
    assert body["checksum"].startswith("sha256:")


def test_route_api_out_of_envelope_422():
    response = client.post("/routes/compute", json={"source_major": 9, "target_major": 12})
    assert response.status_code == 422
    assert response.json()["error_code"] == "ENVELOPE_VIOLATION"


def test_route_api_persist_and_get():
    run_id = f"run-f10a-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      source_version_family="angular-11.x", target_version_family="angular-13.x",
                                      created_at=NOW, updated_at=NOW))
        session.commit()
    persisted = client.post(f"/runs/{run_id}/routes")
    assert persisted.status_code == 200
    assert persisted.json()["source_major"] == 11
    got = client.get(f"/runs/{run_id}/routes")
    assert got.status_code == 200
    assert got.json()["checksum"] == persisted.json()["checksum"]
    validated = client.post(f"/runs/{run_id}/routes/validate")
    assert validated.status_code == 200
