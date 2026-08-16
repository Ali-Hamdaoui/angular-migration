"""Tests for F30 catalogue certification pipeline."""

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.catalogue_certification import (
    CatalogueCertificationCase,
    CertificationStatus,
)
from app.main import app
from app.repositories.catalogue_certification_models import CatalogueCertificationModel
from app.repositories.session import session_scope
from app.services.catalogue_certification_pipeline import CatalogueCertificationPipeline, build_fixture_workspace

client = TestClient(app)


def _root() -> Path:
    root = Path("/tmp") / f"cert-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_fixture_workspace_is_deterministic():
    root = _root()
    first = build_fixture_workspace(root, "angular-11.x", "angular-12.x")
    second = build_fixture_workspace(root, "angular-11.x", "angular-12.x")
    assert (first / "package.json").read_text() == (second / "package.json").read_text()
    assert (first / "src" / "main.ts").read_text() == (second / "src" / "main.ts").read_text()


def test_pipeline_certifies_only_runtime_proven_transitions():
    root = _root()
    pipeline = CatalogueCertificationPipeline()
    run = pipeline.run(fixture_root=root)
    assert run.deterministic is True
    assert run.certified_count == 3  # only the runtime-proven transitions
    assert run.rejected_count == len(run.outcomes) - 3
    assert run.certified_count + run.rejected_count == len(run.outcomes)
    assert run.checksum.startswith("sha256:")
    certified_pairs = {(o.source_family, o.target_family) for o in run.outcomes if o.status is CertificationStatus.CERTIFIED}
    assert certified_pairs == {("angular-18.x", "angular-19.x"), ("angular-19.x", "angular-20.x"), ("angular-20.x", "angular-21.x")}
    # unproven entries are rejected with evidence
    rejected = [o for o in run.outcomes if o.status is CertificationStatus.REJECTED]
    assert rejected
    assert all("runtime_profile_missing" in o.evidence for o in rejected)
    assert all("runtime_proof" not in o.evidence for o in rejected)


def test_pipeline_is_reproducible():
    root = _root()
    pipeline = CatalogueCertificationPipeline()
    first = pipeline.run(fixture_root=root)
    second = pipeline.run(fixture_root=root)
    assert first.checksum == second.checksum
    assert [o.status for o in first.outcomes] == [o.status for o in second.outcomes]


def test_every_outcome_has_evidence_and_checksum():
    root = _root()
    pipeline = CatalogueCertificationPipeline()
    run = pipeline.run(fixture_root=root)
    for outcome in run.outcomes:
        assert outcome.evidence
        assert outcome.checksum.startswith("sha256:")
        if outcome.status is CertificationStatus.CERTIFIED:
            assert outcome.runtime_proof
        assert outcome.reason


def test_pipeline_rejects_missing_catalogue_entry():
    root = _root()
    pipeline = CatalogueCertificationPipeline()
    run = pipeline.run(
        fixture_root=root,
        cases=[CatalogueCertificationCase(case_id="missing", source_family="angular-99.x", target_family="angular-100.x")],
    )
    outcome = run.outcomes[0]
    assert outcome.status is CertificationStatus.REJECTED
    assert "catalogue_entry_missing" in outcome.evidence


def test_persist_and_query():
    root = _root()
    pipeline = CatalogueCertificationPipeline()
    run = pipeline.run(fixture_root=root)
    pipeline.persist(run)
    with session_scope() as session:
        from sqlalchemy import select

        rows = session.scalars(
            select(CatalogueCertificationModel).where(CatalogueCertificationModel.run_id == run.run_id)
        ).all()
        assert len(rows) == len(run.outcomes)
        certified = [r for r in rows if r.status == "certified"]
        assert len(certified) >= 3
        assert all(r.checksum.startswith("sha256:") for r in rows)


def test_persist_is_idempotent():
    root = _root()
    pipeline = CatalogueCertificationPipeline()
    run = pipeline.run(fixture_root=root)
    pipeline.persist(run)
    pipeline.persist(run)
    with session_scope() as session:
        from sqlalchemy import select

        rows = session.scalars(
            select(CatalogueCertificationModel).where(CatalogueCertificationModel.run_id == run.run_id)
        ).all()
        assert len(rows) == len(run.outcomes)


def test_list_certifications_filtered():
    root = _root()
    pipeline = CatalogueCertificationPipeline()
    run = pipeline.run(fixture_root=root)
    pipeline.persist(run)
    rows = pipeline.list_certifications(source="angular-18.x")
    assert rows
    assert all(r.source_family == "angular-18.x" for r in rows)
    none = pipeline.list_certifications(source="angular-99.x")
    assert none == []


def test_api_run_and_list():
    from app.core.config import get_settings

    get_settings.cache_clear()
    allowed = get_settings().allowed_source_roots[0] if get_settings().allowed_source_roots else Path("/tmp")
    root = allowed / "overnight-v2" / f"F30-api-{uuid4().hex[:6]}"
    root.mkdir(parents=True, exist_ok=True)
    response = client.post("/catalogue-certification/run", json={"fixture_root": str(root)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["catalogue_version"] == "catalog-v3"
    assert body["certified_count"] == 3
    assert body["checksum"].startswith("sha256:")
    assert body["deterministic"] is True

    listed = client.get("/catalogue-certification?source=angular-18.x")
    assert listed.status_code == 200
    assert all(r["source_family"] == "angular-18.x" for r in listed.json())


def test_api_fixture_root_outside_allowed_roots_fails_closed():
    from app.core.config import get_settings

    get_settings.cache_clear()
    outside = Path("/tmp") / f"F30-outside-{uuid4().hex[:6]}"
    outside.mkdir(parents=True, exist_ok=True)
    response = client.post("/catalogue-certification/run", json={"fixture_root": str(outside)})
    assert response.status_code == 422
    assert response.json()["error_code"] == "FIXTURE_ROOT_NOT_ALLOWED"
