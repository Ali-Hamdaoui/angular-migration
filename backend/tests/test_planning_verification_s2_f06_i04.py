"""Verification seams for S2-F06-I04.

These tests exercise the public planning boundary with isolated SQLite and
Artifact Store roots. They deliberately do not execute migration commands.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes.plans import get_service
from app.main import app
from app.repositories.models import MigrationPlanModel, MigrationRunModel, WorkflowEventModel
from app.services import planning_evidence_application_service as planning_module

from backend.tests.test_planning_evidence_persistence_api_s2_f06_i02 import setup


def test_api_returns_correlated_authorization_error_without_mutation(tmp_path: Path):
    service, payload, sessions, _ = setup(tmp_path)
    app.dependency_overrides[get_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/runs/run-1/plans",
            headers={"x-authenticated-actor": "unauthorized", "x-correlation-id": "corr-auth"},
            json=payload.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_service, None)

    assert response.status_code == 403
    assert response.headers["x-correlation-id"] == "corr-auth"
    assert response.json()["error_code"] == "RUN_NOT_AUTHORIZED"
    with sessions() as session:
        assert session.query(MigrationPlanModel).count() == 0
        assert session.query(WorkflowEventModel).count() == 0


def test_api_fail_closed_preserves_legal_state_on_generation_failure(tmp_path: Path, monkeypatch):
    service, payload, sessions, _ = setup(tmp_path)

    def fail_closed(*_args, **_kwargs):
        raise RuntimeError("provider detail must not escape")

    monkeypatch.setattr(planning_module.PlanningApplicationService, "generate", fail_closed)
    app.dependency_overrides[get_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/runs/run-1/plans",
            headers={"x-authenticated-actor": "operator", "x-correlation-id": "corr-failure"},
            json=payload.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_service, None)

    assert response.status_code == 503
    assert response.headers["x-correlation-id"] == "corr-failure"
    body = response.json()
    assert body["error_code"] == "PLAN_GENERATION_FAILED"
    assert "provider detail" not in body["message"]
    with sessions() as session:
        run = session.get(MigrationRunModel, "run-1")
        assert run.state_version == 1
        assert session.query(MigrationPlanModel).count() == 0
        assert session.query(WorkflowEventModel).count() == 0


def test_success_evidence_is_checksum_bound_and_event_payload_is_auditable(tmp_path: Path):
    service, payload, sessions, store = setup(tmp_path)
    result = service.create("run-1", payload, "operator")

    with sessions() as session:
        events = session.query(WorkflowEventModel).order_by(WorkflowEventModel.sequence).all()
        assert [event.event_type for event in events] == ["MIGRATION_PLAN_CREATED", "STAGE_PLAN_CREATED"]
        assert [event.sequence for event in events] == [1, 2]
        assert events[0].payload["plan_id"] == result.plan["plan_id"]
        assert events[1].payload["stage_plan_id"] == result.stage_plan["stage_plan_id"]

    assert len(result.artifact_ids) == 7
    assert all(store.read_artifact_by_id(artifact_id).ref.checksum == result.artifact_checksums[artifact_id] for artifact_id in result.artifact_ids)
    assert all("shell" not in store.read_artifact_by_id(artifact_id).content or '"shell": false' in store.read_artifact_by_id(artifact_id).content for artifact_id in result.artifact_ids)
