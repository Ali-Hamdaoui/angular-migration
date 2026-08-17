"""Tests for F17 Angular stage knowledge."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.domain.stage_knowledge import knowledge_entry_for
from app.main import app
from app.repositories.models import StageKnowledgeEntryModel
from app.repositories.session import session_scope
from app.services.stage_knowledge_service import StageKnowledgeError, StageKnowledgeRegistry

NOW = datetime.now(UTC)
client = TestClient(app)


def test_knowledge_entry_for_transition():
    entry = knowledge_entry_for(18, 19)
    assert entry.source_major == 18 and entry.target_major == 19
    assert "build" in entry.validation_expectations
    assert any(c["package"] == "@angular/core" for c in entry.expected_dependency_changes)
    assert entry.version == 1


def test_knowledge_varied_by_major():
    old = knowledge_entry_for(12, 13)
    modern = knowledge_entry_for(20, 21)
    assert any("rxjs" in c["package"] for c in old.expected_dependency_changes)
    assert not any("rxjs" in c["package"] for c in modern.expected_dependency_changes)
    assert old.known_risks != modern.known_risks


def test_dependency_rules_are_capability_driven():
    entry = knowledge_entry_for(12, 13)
    legacy = StageKnowledgeRegistry.dependency_dispositions(
        entry,
        [{"key": "package:tslint", "value": "present"}, {"key": "lockfile_format:v1", "value": "present"}],
    )
    modern = StageKnowledgeRegistry.dependency_dispositions(entry, [])
    assert {item["package"] for item in legacy} >= {"tslint", "package-lock"}
    assert not any(item["package"] == "tslint" for item in modern)
    assert {item["action"] for item in entry.migration_actions} == {
        "run-official-angular-migrations",
        "authorize-installed-migration-fallback",
    }


def test_registry_entries_cover_envelope():
    registry = StageKnowledgeRegistry()
    entries = registry.entries()
    assert len(entries) == 10
    assert entries[0].source_major == 11 and entries[-1].target_major == 21


def test_registry_rejects_non_adjacent():
    registry = StageKnowledgeRegistry()
    try:
        registry.entry(18, 20)
        assert False, "expected NOT_ADJACENT"
    except StageKnowledgeError as exc:
        assert exc.code == "NOT_ADJACENT"


def test_persist_and_audit():
    registry = StageKnowledgeRegistry()
    entry = registry.entry(18, 19)
    row = registry.persist(entry, actor="reviewer", reason="seed 18-19 knowledge")
    assert row.version == 1
    assert row.created_by == "reviewer"
    assert row.change_reason == "seed 18-19 knowledge"
    # idempotent
    again = registry.persist(entry, actor="other")
    assert again.id == row.id
    with session_scope() as session:
        assert session.query(StageKnowledgeEntryModel).filter_by(source_major=18, target_major=19).count() == 1


def test_api_list_and_get():
    listed = client.get("/stage-knowledge")
    assert listed.status_code == 200
    assert len(listed.json()["entries"]) == 10

    entry = client.get("/stage-knowledge/18/19")
    assert entry.status_code == 200
    assert entry.json()["target_major"] == 19

    bad = client.get("/stage-knowledge/18/20")
    assert bad.status_code == 422
    assert bad.json()["error_code"] == "NOT_ADJACENT"


def test_api_persist():
    persisted = client.post("/stage-knowledge/18/19/persist", json={"actor": "test", "reason": "seed"})
    assert persisted.status_code == 200
    assert persisted.json()["source_major"] == 18
    listed = client.get("/stage-knowledge/persisted")
    assert listed.status_code == 200
    assert len(listed.json()["entries"]) >= 1
