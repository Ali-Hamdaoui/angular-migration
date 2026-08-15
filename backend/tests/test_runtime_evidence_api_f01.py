"""API tests for F01-04 runtime execution evidence persistence and resolution surface."""

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import RuntimeExecutionEvidenceModel
from app.repositories.session import session_scope

client = TestClient(app)


def _create_run() -> str:
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.repositories.models import MigrationRunModel

    run_id = f"run-f01-{uuid4().hex[:10]}"
    with session_scope() as session:
        session.add(
            MigrationRunModel(
                id=run_id,
                status="CREATED",
                run_phase="initialized",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        session.commit()
    return run_id


def test_resolve_requirements_returns_bindings():
    response = client.post(
        "/runtime/requirements/resolve",
        json={
            "requirements": [
                {"kind": "node", "runtime_id": "node18", "version_exact": "18.20.8"},
                {"kind": "npm", "runtime_id": "node18", "minimum_version": "9.0.0"},
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["bindings"]) == 2
    node_binding = body["bindings"][0]
    assert node_binding["descriptor"] is not None
    assert node_binding["descriptor"]["version_exact"] == "18.20.8"
    assert len(node_binding["descriptor"]["sha256"]) == 64
    assert node_binding["descriptor"]["resolved_path"].startswith("/home/ubuntu/.nvm/versions/node/")


def test_discover_runtime_executables():
    response = client.get("/runtime/executables")
    assert response.status_code == 200
    descriptors = response.json()["descriptors"]
    assert len(descriptors) >= 12
    assert all(item["resolved_path"].startswith("/home/ubuntu/.nvm/versions/node/") for item in descriptors)


def test_record_and_list_evidence_idempotent():
    run_id = _create_run()
    payload = {
        "requirements": [
            {"kind": "node", "runtime_id": "node18", "version_exact": "18.20.8"},
            {"kind": "npm", "runtime_id": "node18", "minimum_version": "9.0.0"},
        ]
    }
    first = client.post(f"/runs/{run_id}/runtime/evidence", json=payload)
    assert first.status_code == 200
    assert first.json()["recorded"] == 2

    second = client.post(f"/runs/{run_id}/runtime/evidence", json=payload)
    assert second.status_code == 200
    assert second.json()["recorded"] == 2

    listed = client.get(f"/runs/{run_id}/runtime/evidence")
    assert listed.status_code == 200
    evidence = listed.json()["evidence"]
    assert len(evidence) == 2
    assert {item["kind"] for item in evidence} == {"node", "npm"}

    with session_scope() as session:
        rows = session.query(RuntimeExecutionEvidenceModel).filter_by(run_id=run_id).all()
        assert len(rows) == 2


def test_unresolvable_requirement_records_nothing_and_lists_empty():
    run_id = _create_run()
    payload = {"requirements": [{"kind": "node", "runtime_id": "node99", "version_exact": "99.0.0"}]}
    response = client.post(f"/runs/{run_id}/runtime/evidence", json=payload)
    assert response.status_code == 200
    assert response.json()["recorded"] == 0
    listed = client.get(f"/runs/{run_id}/runtime/evidence")
    assert listed.json()["evidence"] == []


def test_resolve_rejects_empty_requirements():
    response = client.post("/runtime/requirements/resolve", json={"requirements": []})
    assert response.status_code == 400
    assert response.json()["error_code"] == "EMPTY_REQUIREMENTS"
