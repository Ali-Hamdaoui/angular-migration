"""Tests for F14 Angular update governance."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.models import MigrationRunModel, MigrationStageModel
from app.repositories.session import session_scope
from app.services.ng_update_governance_service import NgUpdateGovernanceError, NgUpdateGovernanceService


NOW = datetime.now(UTC)
client = TestClient(app)


def test_spec_resolves_per_major_transition():
    service = NgUpdateGovernanceService()
    spec = service.spec_for_transition(18, 19)
    assert spec.target_exact == "19.0.0"
    assert spec.target_cli_exact == "19.0.0"
    assert spec.template_id == "tpl-angular-update-exact-v3"
    assert "@angular/cli@19.0.0" in spec.rendered_arguments
    assert "@angular/core@19.0.0" in spec.rendered_arguments
    assert spec.checksum.startswith("sha256:")


def test_spec_is_deterministic():
    service = NgUpdateGovernanceService()
    first = service.spec_for_transition(11, 12)
    second = service.spec_for_transition(11, 12)
    assert first.checksum == second.checksum
    assert first.model_dump() == second.model_dump()


def test_spec_rejects_non_adjacent_and_out_of_envelope():
    service = NgUpdateGovernanceService()
    try:
        service.spec_for_transition(18, 20)
        assert False, "expected NOT_ADJACENT"
    except NgUpdateGovernanceError as exc:
        assert exc.code == "NOT_ADJACENT"
    try:
        service.spec_for_transition(9, 10)
        assert False, "expected ENVELOPE_VIOLATION"
    except NgUpdateGovernanceError as exc:
        assert exc.code == "ENVELOPE_VIOLATION"


def _seed(stage_id: str, source: str, target: str) -> str:
    run_id = f"run-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized", created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(id=stage_id, run_id=run_id, stage_order=1,
                                        source_version_family=source, target_version_family=target,
                                        status="planned", created_at=NOW))
        session.commit()
    return run_id


def test_authorize_certified_transition():
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id, "angular-18.x", "angular-19.x")
    service = NgUpdateGovernanceService()
    authz = service.authorize_update(18, 19, stage_id=stage_id)
    assert authz.certified is True
    assert authz.allowed is True
    assert authz.spec_checksum.startswith("sha256:")


def test_authorize_experimental_transition_denied():
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id, "angular-11.x", "angular-12.x")
    service = NgUpdateGovernanceService()
    authz = service.authorize_update(11, 12, stage_id=stage_id)
    assert authz.certified is False
    assert authz.allowed is False


def test_api_spec():
    response = client.get("/governance/ng-update/18/19")
    assert response.status_code == 200
    body = response.json()
    assert body["target_exact"] == "19.0.0"
    assert body["checksum"].startswith("sha256:")


def test_api_authorize_certified():
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id, "angular-18.x", "angular-19.x")
    response = client.post(f"/runs/{run_id}/stages/{stage_id}/governance/ng-update/18/19")
    assert response.status_code == 200
    assert response.json()["allowed"] is True
    assert response.json()["certified"] is True


def test_api_authorize_experimental_denied():
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id, "angular-11.x", "angular-12.x")
    response = client.post(f"/runs/{run_id}/stages/{stage_id}/governance/ng-update/11/12")
    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert response.json()["certified"] is False
