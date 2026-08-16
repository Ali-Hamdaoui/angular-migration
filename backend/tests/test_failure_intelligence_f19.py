"""Tests for F19 failure intelligence."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import FailureDiagnosticPackModel, FailureIntelligenceModel, MigrationRunModel
from app.repositories.session import session_scope
from app.services.failure_intelligence_service import FailureIntelligenceService

NOW = datetime.now(UTC)
client = TestClient(app)


def _seed_packs(run_id: str) -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized", created_at=NOW, updated_at=NOW))
        for i, (code, category, message) in enumerate(
            [
                ("NPM_ERESOLVE", "dependency", "npm ERR! code ERESOLVE"),
                ("NPM_ERESOLVE", "dependency", "npm ERR! code ERESOLVE"),
                ("COMMAND_TIMED_OUT", "command", "command timed out"),
            ]
        ):
            session.add(FailureDiagnosticPackModel(
                id=f"diag-{run_id}-{i}", run_id=run_id, fault_code=code, category=category,
                severity="error", message=message, workflow_context={}, sanitized_traceback="",
                checksum="sha256:" + "a" * 64, state_version=1, created_at=NOW,
            ))
        session.commit()


def test_stable_group_key_deterministic():
    service = FailureIntelligenceService()
    first = service.stable_group_key("NPM_ERESOLVE", "dependency", "npm ERR! code ERESOLVE\nline2")
    second = service.stable_group_key("NPM_ERESOLVE", "dependency", "npm ERR! code ERESOLVE\nother")
    assert first == second
    different = service.stable_group_key("COMMAND_TIMED_OUT", "command", "npm ERR! code ERESOLVE")
    assert first != different


def test_group_merges_similar_failures():
    service = FailureIntelligenceService()
    groups = service.group([
        {"fault_code": "NPM_ERESOLVE", "category": "dependency", "message": "npm ERR! code ERESOLVE", "created_at": NOW},
        {"fault_code": "NPM_ERESOLVE", "category": "dependency", "message": "npm ERR! code ERESOLVE", "created_at": NOW},
        {"fault_code": "COMMAND_TIMED_OUT", "category": "command", "message": "command timed out", "created_at": NOW},
    ])
    assert len(groups) == 2
    eresolve = next(g for g in groups if "ERESOLVE" in str(g.fault_codes))
    assert eresolve.member_count == 2


def test_root_cause_resolution():
    service = FailureIntelligenceService()
    groups = service.group([{"fault_code": "DEPENDENCY_PREFLIGHT_BLOCKED", "category": "dependency", "message": "x", "created_at": NOW}])
    cause = service.resolve_root_cause(groups[0])
    assert cause.root_cause_code == "DEPENDENCY_PREFLIGHT_BLOCKED"
    assert cause.taxonomy == "dependency"
    assert cause.confidence == "high"


def test_dependency_graph_precedence():
    service = FailureIntelligenceService()
    groups = service.group([
        {"fault_code": "A", "category": "dependency", "message": "d", "created_at": NOW},
        {"fault_code": "B", "category": "command", "message": "c", "created_at": NOW},
    ])
    graph = service.build_dependency_graph(groups)
    dep = next(g for g in groups if g.taxonomy == "dependency")
    cmd = next(g for g in groups if g.taxonomy == "command")
    assert any(e.depends_on == dep.group_key and e.dependent == cmd.group_key for e in graph.edges)


def test_intelligence_for_run_and_persist():
    run_id = f"run-f19-{uuid4().hex[:8]}"
    _seed_packs(run_id)
    service = FailureIntelligenceService()
    intelligence = service.intelligence_for_run(run_id)
    assert len(intelligence["groups"]) == 2
    row = service.persist(run_id, intelligence)
    assert row.checksum == intelligence["graph"].checksum
    with session_scope() as session:
        assert session.query(FailureIntelligenceModel).filter_by(run_id=run_id).count() == 1


def test_api_build_and_get():
    run_id = f"run-f19-{uuid4().hex[:8]}"
    _seed_packs(run_id)
    built = client.post(f"/runs/{run_id}/failure-intelligence")
    assert built.status_code == 200
    body = built.json()
    assert len(body["groups"]) == 2
    assert "graph" in body

    persisted = client.post(f"/runs/{run_id}/failure-intelligence/persist")
    assert persisted.status_code == 200
    got = client.get(f"/runs/{run_id}/failure-intelligence")
    assert got.status_code == 200
    assert got.json()["checksum"] == persisted.json()["checksum"]
