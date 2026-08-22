"""Tests for F11 bridge runtime certification."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from fastapi.testclient import TestClient

from app.domain.runtime_certification import evaluate_certification
from app.domain.runtime_execution import RuntimeExecutableDescriptor, RuntimeExecutableKind, RuntimeRequirementBinding
from app.domain.stage_runtime import StageRuntimeBinding
from app.api.routes.runtime_certification import get_certification_service
from app.main import app
from app.repositories.models import MigrationRunModel, MigrationStageModel, RuntimeCertificationModel
from app.repositories.session import session_scope
from app.services.runtime_certification_service import RuntimeCertificationError, RuntimeCertificationService


NOW = datetime.now(UTC)
client = TestClient(app)


def _descriptor(kind, version, runtime_id):
    from app.domain.runtime_execution import RuntimeExecutableDescriptor, RuntimeExecutableKind

    return RuntimeExecutableDescriptor(
        kind=RuntimeExecutableKind(kind),
        executable_name=kind,
        resolved_path=f"/opt/node/{version}/bin/{kind}",
        version_exact=version,
        sha256="a" * 64,
        operating_system="linux",
        architecture="amd64",
        installation_root=f"/opt/node/{version}",
        source="nvm",
        runtime_id=runtime_id,
        probed_at=NOW,
    )


def test_evaluate_certification_matches_validated_profile():
    node = _descriptor("node", "18.20.8", "v18.20.8")
    npm = _descriptor("npm", "10.8.2", "v18.20.8")
    decision = evaluate_certification(
        run_id="run", stage_id="stage", source_family="angular-18.x", target_family="angular-19.x",
        node_descriptor=node, npm_descriptor=npm,
        catalogue_validated_profiles=(("18.20.8", "10.8.2"),),
        catalogue_version="catalog-v3", resolved_at=NOW,
    )
    assert decision.certified is True
    assert decision.allowed is True
    assert decision.classification == "EXACT_CERTIFIED"
    assert decision.runtime_id == "v18.20.8"


def test_evaluate_certification_rejects_unmatched_profile():
    node = _descriptor("node", "20.20.2", "v20.20.2")
    npm = _descriptor("npm", "10.8.2", "v20.20.2")
    decision = evaluate_certification(
        run_id="run", stage_id="stage", source_family="angular-18.x", target_family="angular-19.x",
        node_descriptor=node, npm_descriptor=npm,
        catalogue_validated_profiles=(("18.20.8", "10.8.2"),),
        catalogue_version="catalog-v3", resolved_at=NOW,
    )
    assert decision.certified is False
    assert decision.allowed is False
    assert decision.classification == "UNSUPPORTED"


def test_evaluate_certification_allows_governed_range_compatible_runtime_without_certifying_it():
    decision = evaluate_certification(
        run_id="run", stage_id="stage", source_family="angular-18.x", target_family="angular-19.x",
        node_descriptor=_descriptor("node", "22.23.1", "v22.23.1"),
        npm_descriptor=_descriptor("npm", "10.9.8", "v22.23.1"),
        npx_descriptor=_descriptor("npx", "10.9.8", "v22.23.1"),
        catalogue_validated_profiles=(("18.20.8", "10.8.2"),),
        source_node_ranges=("^18.19.1", "^20.11.1", "^22.0.0"),
        target_node_ranges=("^18.19.1", "^20.11.1", "^22.0.0"),
        catalogue_version="catalog-v3", resolved_at=NOW,
    )
    assert decision.allowed is True
    assert decision.certified is False
    assert decision.classification == "RANGE_COMPATIBLE"


def test_evaluate_certification_requires_npm_and_npx_for_range_compatibility():
    decision = evaluate_certification(
        run_id="run", stage_id="stage", source_family="angular-18.x", target_family="angular-19.x",
        node_descriptor=_descriptor("node", "22.23.1", "v22.23.1"), npm_descriptor=None,
        npx_descriptor=_descriptor("npx", "10.9.8", "v22.23.1"),
        catalogue_validated_profiles=(("18.20.8", "10.8.2"),),
        source_node_ranges=("^18.19.1", "^20.11.1", "^22.0.0"),
        target_node_ranges=("^18.19.1", "^20.11.1", "^22.0.0"),
        catalogue_version="catalog-v3", resolved_at=NOW,
    )
    assert decision.allowed is False
    assert decision.classification == "UNSUPPORTED"


def test_evaluate_certification_allows_range_compatible_profile_without_exact_certification():
    decision = evaluate_certification(
        run_id="run", stage_id="stage", source_family="angular-11.x", target_family="angular-12.x",
        node_descriptor=_descriptor("node", "12.14.0", "v12.14.0"),
        npm_descriptor=_descriptor("npm", "6.14.0", "v12.14.0"),
        npx_descriptor=_descriptor("npx", "6.14.0", "v12.14.0"),
        catalogue_validated_profiles=(),
        source_node_ranges=("^10.13.0", "^12.11.0"),
        target_node_ranges=("^12.14.0", "^14.15.0"),
        catalogue_version="catalog-v3", resolved_at=NOW,
    )
    assert decision.certified is False
    assert decision.allowed is True
    assert decision.classification == "RANGE_COMPATIBLE"


def test_12_to_13_node_16_bridge_is_range_compatible():
    decision = evaluate_certification(
        run_id="run", stage_id="stage", source_family="angular-12.x", target_family="angular-13.x",
        node_descriptor=_descriptor("node", "16.20.2", "v16.20.2"),
        npm_descriptor=_descriptor("npm", "8.19.4", "v16.20.2"),
        npx_descriptor=_descriptor("npx", "8.19.4", "v16.20.2"),
        catalogue_validated_profiles=(),
        source_node_ranges=("^12.14.0", "^14.15.0", "^16.10.0"),
        target_node_ranges=("^12.20.0", "^14.15.0", "^16.10.0"),
        catalogue_version="catalog-v3", resolved_at=NOW,
    )

    assert decision.allowed is True
    assert decision.certified is False
    assert decision.classification == "RANGE_COMPATIBLE"


def _seed(stage_id: str, source: str, target: str) -> str:
    run_id = f"run-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized", created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(id=stage_id, run_id=run_id, stage_order=1,
                                        source_version_family=source, target_version_family=target,
                                        status="planned", created_at=NOW))
        session.commit()
    return run_id


class _CertifiedRuntimeStageService:
    def __init__(self):
        from app.services.stage_runtime_service import StageRuntimeApplicationService

        self._delegate = StageRuntimeApplicationService()

    def stage_version_families(self, stage_id):
        return self._delegate.stage_version_families(stage_id)

    def resolve_stage(self, stage_id, source_family, target_family):
        requirement = self._delegate.derive_requirement(stage_id, source_family, target_family)
        descriptors = {
            RuntimeExecutableKind.NODE: _descriptor("node", "18.20.8", "v18.20.8"),
            RuntimeExecutableKind.NPM: _descriptor("npm", "10.8.2", "v18.20.8"),
            RuntimeExecutableKind.NPX: _descriptor("npx", "10.8.2", "v18.20.8"),
        }
        bindings = tuple(RuntimeRequirementBinding(requirement=item, descriptor=descriptors[item.kind]) for item in requirement.requirements)
        return StageRuntimeBinding(stage_id=stage_id, requirement=requirement, bindings=bindings, status="bound", resolved_at=NOW).bind_checksum()


def test_certify_certified_transition_stage(tmp_path: Path):
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id, "angular-18.x", "angular-19.x")
    service = RuntimeCertificationService(stage_runtime_service=_CertifiedRuntimeStageService())
    decision = service.certify_stage(stage_id)
    assert decision.certified is True
    assert decision.runtime_id is not None

    with session_scope() as session:
        assert session.query(RuntimeCertificationModel).filter_by(stage_id=stage_id, certified=True).count() == 1


def test_certify_experimental_transition_is_not_certified(tmp_path: Path):
    stage_id = f"stage-{uuid4().hex[:8]}"
    _seed(stage_id, "angular-11.x", "angular-12.x")
    service = RuntimeCertificationService()
    decision = service.certify_stage(stage_id)
    assert decision.certified is False
    assert "runtime could not be resolved" in decision.reason


def test_enforce_gate_fails_closed_on_experimental_transition(tmp_path: Path):
    stage_id = f"stage-{uuid4().hex[:8]}"
    _seed(stage_id, "angular-11.x", "angular-12.x")
    service = RuntimeCertificationService()
    with pytest.raises(RuntimeCertificationError) as exc:
        service.enforce_stage_certification(stage_id)
    assert exc.value.code == "RUNTIME_NOT_CERTIFIED"


def test_enforce_gate_passes_on_certified_transition(tmp_path: Path):
    stage_id = f"stage-{uuid4().hex[:8]}"
    _seed(stage_id, "angular-18.x", "angular-19.x")
    service = RuntimeCertificationService(stage_runtime_service=_CertifiedRuntimeStageService())
    decision = service.enforce_stage_certification(stage_id)
    assert decision.certified is True


def test_certification_api_certify_and_list(tmp_path: Path):
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id, "angular-18.x", "angular-19.x")
    service = RuntimeCertificationService(stage_runtime_service=_CertifiedRuntimeStageService())
    app.dependency_overrides[get_certification_service] = lambda: service
    certified = client.post(f"/runs/{run_id}/stages/{stage_id}/runtime/certify")
    assert certified.status_code == 200
    assert certified.json()["certified"] is True

    gate = client.post(f"/runs/{run_id}/stages/{stage_id}/runtime/gate")
    assert gate.status_code == 200
    assert gate.json()["certified"] is True

    listed = client.get(f"/runs/{run_id}/stages/{stage_id}/runtime/certifications")
    assert listed.status_code == 200
    assert len(listed.json()["certifications"]) == 1
    app.dependency_overrides.pop(get_certification_service, None)


def test_certification_api_gate_fails_on_experimental(tmp_path: Path):
    stage_id = f"stage-{uuid4().hex[:8]}"
    run_id = _seed(stage_id, "angular-11.x", "angular-12.x")
    gate = client.post(f"/runs/{run_id}/stages/{stage_id}/runtime/gate")
    assert gate.status_code == 409
    assert gate.json()["error_code"] == "RUNTIME_NOT_CERTIFIED"
