"""Tests for F02 stage runtime requirement and binding."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.domain.runtime_execution import RuntimeExecutableDescriptor, RuntimeExecutableKind, RuntimeRequirement, RuntimeRequirementBinding
from app.domain.stage_runtime import StageRuntimeBinding, StageRuntimeRequirement
from app.repositories.models import ExecutionProfileModel, MigrationRunModel, MigrationStageModel, StageRuntimeBindingModel
from app.repositories.session import session_scope
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.stage_runtime_service import StageRuntimeApplicationService, StageRuntimeError


NOW = datetime.now(UTC)


def make_service(tmp_path: Path) -> StageRuntimeApplicationService:
    return StageRuntimeApplicationService()


def test_stage_runtime_requirement_immutable_and_kind_lookup():
    requirement = StageRuntimeRequirement(
        stage_id="stage-1",
        source_family="angular-18.x",
        target_family="angular-19.x",
        catalogue_version="catalog-v2",
        requirements=(
            RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="node20", minimum_version="20.11.1"),
        ),
    )
    assert requirement.requirement_for(RuntimeExecutableKind.NODE) is not None
    assert requirement.requirement_for(RuntimeExecutableKind.NPX) is None
    with pytest.raises(ValueError):
        requirement.stage_id = "other"


def test_derive_requirement_from_catalogue():
    service = make_service(Path("/tmp"))
    requirement = service.derive_requirement("stage-1", "angular-18.x", "angular-19.x")
    assert requirement.source_family == "angular-18.x"
    assert requirement.target_family == "angular-19.x"
    node = requirement.requirement_for(RuntimeExecutableKind.NODE)
    assert node is not None
    assert node.minimum_version == "18.19.1"
    assert node.runtime_id == "angular-stage-runtime"


def test_derive_requirement_missing_entry_raises():
    service = make_service(Path("/tmp"))
    with pytest.raises(StageRuntimeError) as exc:
        service.derive_requirement("stage-9", "angular-25.x", "angular-26.x")
    assert exc.value.code == "CATALOGUE_ENTRY_MISSING"


def _seed_stage(stage_id: str) -> None:
    run_id = f"run-{stage_id}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(
            id=stage_id, run_id=run_id, stage_order=1,
            source_version_family="angular-18.x", target_version_family="angular-19.x",
            source_angular_version="18.2.0", target_angular_version="19.0.0",
            status="planned", created_at=NOW,
        ))
        session.commit()


def test_resolve_stage_binds_machine_runtime(tmp_path: Path):
    _seed_stage("stage-resolve-1")
    service = make_service(tmp_path)
    binding = service.resolve_stage("stage-resolve-1", "angular-18.x", "angular-19.x")
    assert binding.status == "bound"
    assert binding.checksum.startswith("sha256:")
    node = binding.descriptor_for(RuntimeExecutableKind.NODE)
    assert node is not None
    assert node.runtime_id.startswith("v18") or node.version_exact >= "18.19.1"
    npm = binding.descriptor_for(RuntimeExecutableKind.NPM)
    assert npm is not None and npm.runtime_id == node.runtime_id


def test_resolve_stage_honors_selected_run_profile(tmp_path: Path):
    run_id, stage_id = _seed_run_and_stage()
    profile = {
        "profile_id": "profile-node22",
        "checksum": "sha256:" + "b" * 64,
        "node_exact": "v22.23.1",
        "package_manager_exact": "10.9.8",
        "npx_exact": "10.9.8",
    }
    with session_scope() as session:
        session.add(ExecutionProfileModel(
            id=f"profile-resolution-{uuid4().hex[:8]}", run_id=run_id,
            idempotency_key=f"profile-{uuid4().hex[:8]}", request_checksum="request",
            policy_version="angular-source-runtime-v1", status="resolved",
            source_angular_exact="^18.0.0", selected_profile_id=profile["profile_id"],
            selected_checksum=profile["checksum"], profiles=[profile], blockers=[], guidance=[],
            artifact_ids=[], state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW,
        ))
        session.commit()

    class RecordingAuthority:
        def __init__(self):
            self.requirements = []

        def resolve(self, requirements):
            self.requirements = list(requirements)
            versions = {"node": "22.23.1", "npm": "10.9.8", "npx": "10.9.8"}
            return tuple(
                RuntimeRequirementBinding(
                    requirement=requirement,
                    descriptor=RuntimeExecutableDescriptor(
                        kind=requirement.kind, executable_name=requirement.kind.value,
                        resolved_path=f"C:/nvm/v22.23.1/{requirement.kind.value}",
                        version_exact=versions[requirement.kind.value], sha256="c" * 64,
                        operating_system="windows", architecture="amd64", runtime_id="v22.23.1",
                        source="nvm", probed_at=NOW,
                    ),
                )
                for requirement in requirements
            )

    authority = RecordingAuthority()
    service = StageRuntimeApplicationService(authority=authority)
    binding = service.resolve_stage(stage_id, "angular-18.x", "angular-19.x")

    assert binding.status == "bound"
    assert {item.version_exact for item in authority.requirements} == {"22.23.1", "10.9.8"}


def test_stage_runtime_binding_checksum_immutable():
    requirement = StageRuntimeRequirement(
        stage_id="stage-1", source_family="angular-18.x", target_family="angular-19.x",
        catalogue_version="catalog-v2",
        requirements=(RuntimeRequirement(kind=RuntimeExecutableKind.NODE, runtime_id="node20", minimum_version="20.11.1"),),
    )
    binding = StageRuntimeBinding(
        stage_id="stage-1", requirement=requirement, status="blocked",
        blocked_reason="none", resolved_at=NOW,
    )
    bound = binding.bind_checksum()
    assert bound.checksum.startswith("sha256:")
    with pytest.raises(ValueError):
        bound.stage_id = "other"


def _seed_run_and_stage() -> tuple[str, str]:
    run_id = f"run-f02-{uuid4().hex[:8]}"
    stage_id = f"stage-f02-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(
            id=stage_id, run_id=run_id, stage_order=1,
            source_version_family="angular-18.x", target_version_family="angular-19.x",
            source_angular_version="18.2.0", target_angular_version="19.0.0",
            status="planned", created_at=NOW,
        ))
        session.commit()
    return run_id, stage_id


def test_record_and_list_stage_binding(tmp_path: Path):
    service = make_service(tmp_path)
    run_id, stage_id = _seed_run_and_stage()
    binding = service.resolve_stage(stage_id, "angular-18.x", "angular-19.x")
    rows = service.record_binding(run_id, binding, actor="test")
    assert len(rows) == 3
    assert {row.kind for row in rows} == {"node", "npm", "npx"}
    for row in rows:
        assert row.stage_id == stage_id
        assert row.run_id == run_id
        assert len(row.sha256) == 64

    # idempotent
    again = service.record_binding(run_id, binding, actor="test")
    assert len(again) == 3

    listed = service.list_stage_bindings(stage_id)
    assert len(listed) == 3

    with session_scope() as session:
        rows_db = session.query(StageRuntimeBindingModel).filter_by(stage_id=stage_id).all()
        assert len(rows_db) == 3


def test_record_binding_unknown_stage_raises(tmp_path: Path):
    service = make_service(tmp_path)
    with pytest.raises(StageRuntimeError) as exc:
        service.resolve_stage("stage-missing", "angular-18.x", "angular-19.x")
    assert exc.value.code == "STAGE_NOT_FOUND"


def test_record_binding_unknown_run_raises(tmp_path: Path):
    service = make_service(tmp_path)
    _seed_stage("stage-run-check")
    binding = service.resolve_stage("stage-run-check", "angular-18.x", "angular-19.x")
    with pytest.raises(StageRuntimeError) as exc:
        service.record_binding("run-does-not-exist", binding)
    assert exc.value.code == "RUN_NOT_FOUND"


def test_blocked_resolution_persists_status_only_evidence(tmp_path: Path):
    """A blocked stage binding persists per-kind rows with no descriptors (F02 evidence integrity)."""
    _seed_stage("stage-blocked")
    service = make_service(tmp_path)

    class BlockingAuthority:
        def resolve(self, requirements):
            return tuple(
                RuntimeRequirementBinding(requirement=r, blocked_reason="no compatible install")
                for r in requirements
            )

    service._authority = BlockingAuthority()  # type: ignore[assignment]
    binding = service.resolve_stage("stage-blocked", "angular-18.x", "angular-19.x")
    assert binding.status == "blocked"
    assert binding.blocked_reason is not None

    rows = service.record_binding("run-stage-blocked", binding)
    assert len(rows) == 3
    for row in rows:
        assert row.status == "blocked"
        assert row.sha256 is None
        assert row.resolved_path is None
        assert row.blocked_reason is not None
