"""Tests for F09 compatibility catalogue: envelope, query, versioning, audit."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import CompatibilityCatalogueModel
from app.repositories.session import session_scope
from app.services.catalogue_registry_service import CompatibilityCatalogueRegistry
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider

client = TestClient(app)
NOW = datetime.now(UTC)


def test_catalogue_covers_full_11_21_envelope():
    catalogue = CompatibilityCatalogueProvider().load()
    assert len(catalogue.entries) == 10
    assert catalogue.entry_for("angular-11.x", "angular-12.x") is not None
    assert catalogue.entry_for("angular-20.x", "angular-21.x") is not None
    assert catalogue.entry_for("angular-18.x", "angular-19.x").support_level == "historical_validated"
    assert catalogue.entry_for("angular-11.x", "angular-12.x").support_level == "historical_experimental"


def test_query_catalogue_api():
    response = client.get("/catalogue")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "catalog-v3"
    assert len(body["entries"]) == 10

    entry = client.get("/catalogue/entries/angular-11.x/angular-12.x")
    assert entry.status_code == 200
    assert entry.json()["node_minimum"] == "12.14.0"
    assert entry.json()["typescript_minimum"] == "4.2.3"
    assert entry.json()["certification_status"] == "seeded_official"

    certified = client.get("/catalogue/entries/angular-18.x/angular-19.x")
    assert certified.json()["certification_status"] == "certified"
    assert certified.json()["support_level"] == "historical_validated"


def test_catalogue_entry_missing_404():
    response = client.get("/catalogue/entries/angular-30.x/angular-31.x")
    assert response.status_code == 404
    assert response.json()["error_code"] == "CATALOGUE_ENTRY_MISSING"


def test_record_and_list_catalogue_versions():
    run_tag = uuid4().hex[:6]
    registry = CompatibilityCatalogueRegistry()
    record = registry.record_version(actor="reviewer", reason=f"envelope expansion {run_tag}")
    assert record.version == "catalog-v3"
    assert record.created_by == "reviewer"
    assert record.change_reason == f"envelope expansion {run_tag}"

    versions = client.get("/catalogue/versions")
    assert versions.status_code == 200
    assert any(v["version"] == "catalog-v3" for v in versions.json()["versions"])

    with session_scope() as session:
        assert session.query(CompatibilityCatalogueModel).filter_by(version="catalog-v3").count() >= 1


def test_record_version_is_idempotent():
    registry = CompatibilityCatalogueRegistry()
    first = registry.record_version(actor="a", reason="idempotent")
    second = registry.record_version(actor="b", reason="idempotent again")
    assert first.id == second.id
    with session_scope() as session:
        assert session.query(CompatibilityCatalogueModel).filter_by(version="catalog-v3").count() == 1
