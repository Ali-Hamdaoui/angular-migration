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


def _synthetic_descriptor(runtime_id, kind, node_version, npm_version):
    version = node_version if kind is RuntimeExecutableKind.NODE else npm_version
    return RuntimeExecutableDescriptor(
        kind=kind,
        executable_name=kind.value,
        resolved_path=f"C:/synthetic/{runtime_id}/{kind.value}",
        version_exact=version,
        sha256=(runtime_id + kind.value).encode().hex().ljust(64, "0")[:64],
        operating_system="windows",
        architecture="amd64",
        installation_root=f"C:/synthetic/{runtime_id}",
        source="synthetic",
        runtime_id=runtime_id,
        probed_at=NOW,
    )


class _SyntheticAuthority:
    def __init__(self, profiles):
        self.descriptors = [
            descriptor
            for runtime_id, node, npm in profiles
            for descriptor in (
                _synthetic_descriptor(runtime_id, RuntimeExecutableKind.NODE, node, npm),
                _synthetic_descriptor(runtime_id, RuntimeExecutableKind.NPM, node, npm),
                _synthetic_descriptor(runtime_id, RuntimeExecutableKind.NPX, node, npm),
            )
        ]

    def resolve(self, requirements):
        result = []
        for requirement in requirements:
            match = next(
                (
                    descriptor
                    for descriptor in self.descriptors
                    if descriptor.runtime_id == requirement.runtime_id
                    and requirement.satisfied_by(descriptor)
                ),
                None,
            )
            result.append(RuntimeRequirementBinding(requirement=requirement, descriptor=match, blocked_reason=None if match else "missing synthetic runtime"))
        return tuple(result)


class _StaticCatalogueProvider:
    def __init__(self, catalogue):
        self.catalogue = catalogue

    def load(self, version=None):
        return self.catalogue


def _seed_families(source, target):
    run_id = f"run-stage-{uuid4().hex[:8]}"
    stage_id = f"stage-stage-{uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized", created_at=NOW, updated_at=NOW))
        session.add(MigrationStageModel(
            id=stage_id, run_id=run_id, stage_order=1,
            source_version_family=source, target_version_family=target,
            source_angular_version=source.removeprefix("angular-").removesuffix(".x") + ".0.0",
            target_angular_version=target.removeprefix("angular-").removesuffix(".x") + ".0.0",
            status="planned", created_at=NOW,
        ))
        session.commit()
    return run_id, stage_id


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


def test_derive_requirement_does_not_invent_an_npm_major_policy_for_legacy_stage():
    service = make_service(Path("/tmp"))
    requirement = service.derive_requirement("stage-1", "angular-11.x", "angular-12.x")
    npm = requirement.requirement_for(RuntimeExecutableKind.NPM)
    npx = requirement.requirement_for(RuntimeExecutableKind.NPX)
    assert npm is not None and npm.allowed_major_versions == ()
    assert npx is not None and npx.allowed_major_versions == ()


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


def test_synthetic_stages_bind_different_governed_runtimes():
    _, stage11 = _seed_families("angular-11.x", "angular-12.x")
    _, stage18 = _seed_families("angular-18.x", "angular-19.x")
    authority = _SyntheticAuthority((
        ("node12", "12.22.12", "8.19.4"),
        ("node18", "18.20.8", "10.8.2"),
    ))
    service = StageRuntimeApplicationService(authority=authority)

    first = service.resolve_stage(stage11, "angular-11.x", "angular-12.x")
    second = service.resolve_stage(stage18, "angular-18.x", "angular-19.x")

    assert first.status == second.status == "bound"
    assert first.descriptor_for(RuntimeExecutableKind.NODE).runtime_id == "node12"
    assert second.descriptor_for(RuntimeExecutableKind.NODE).runtime_id == "node18"


def test_valid_baseline_reused_when_no_exact_profile_is_trusted():
    _, stage_id = _seed_families("angular-18.x", "angular-19.x")
    current = CompatibilityCatalogueProvider().load()
    entry = current.entry_for("angular-18.x", "angular-19.x").model_copy(update={"validated_runtime_profiles": (), "proven_runtime_profiles": ()})
    provider = _StaticCatalogueProvider(CompatibilityCatalogueProvider().load().model_copy(update={"entries": (entry,)}))
    profile = {"profile_id": "baseline-node22", "checksum": "sha256:" + "b" * 64, "node_exact": "22.23.1", "package_manager_exact": "10.9.8", "npx_exact": "10.9.8"}
    with session_scope() as session:
        stage = session.get(MigrationStageModel, stage_id)
        run_id = stage.run_id
        session.add(ExecutionProfileModel(
            id=f"profile-baseline-{uuid4().hex[:8]}", run_id=run_id, idempotency_key="baseline",
            request_checksum="request", policy_version="v2", status="resolved", source_angular_exact="18.0.0",
            selected_profile_id=profile["profile_id"], selected_checksum=profile["checksum"], profiles=[profile],
            blockers=[], guidance=[], artifact_ids=[], state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW,
        ))
        session.commit()
    service = StageRuntimeApplicationService(
        authority=_SyntheticAuthority((("node22", "22.23.1", "10.9.8"),)),
        catalogue_provider=provider,
    )
    binding = service.resolve_stage(stage_id, "angular-18.x", "angular-19.x")
    assert binding.status == "bound"
    assert binding.descriptor_for(RuntimeExecutableKind.NODE).runtime_id == "node22"


def test_exact_trusted_profile_outranks_range_baseline():
    _, stage_id = _seed_families("angular-18.x", "angular-19.x")
    profile = {"profile_id": "baseline-node22", "checksum": "sha256:" + "d" * 64, "node_exact": "22.23.1", "package_manager_exact": "10.9.8", "npx_exact": "10.9.8"}
    with session_scope() as session:
        run_id = session.get(MigrationStageModel, stage_id).run_id
        session.add(ExecutionProfileModel(
            id=f"profile-precedence-{uuid4().hex[:8]}", run_id=run_id, idempotency_key="precedence",
            request_checksum="request", policy_version="v2", status="resolved", source_angular_exact="18.0.0",
            selected_profile_id=profile["profile_id"], selected_checksum=profile["checksum"], profiles=[profile],
            blockers=[], guidance=[], artifact_ids=[], state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW,
        ))
        session.commit()
    binding = StageRuntimeApplicationService(
        authority=_SyntheticAuthority((("node18", "18.20.8", "10.8.2"), ("node22", "22.23.1", "10.9.8"))),
    ).resolve_stage(stage_id, "angular-18.x", "angular-19.x")
    assert binding.status == "bound"
    assert binding.descriptor_for(RuntimeExecutableKind.NODE).runtime_id == "node18"


def test_incompatible_baseline_is_ignored_for_later_stage():
    _, stage_id = _seed_families("angular-11.x", "angular-12.x")
    profile = {"profile_id": "baseline-node22", "checksum": "sha256:" + "c" * 64, "node_exact": "22.23.1", "package_manager_exact": "10.9.8", "npx_exact": "10.9.8"}
    with session_scope() as session:
        run_id = session.get(MigrationStageModel, stage_id).run_id
        session.add(ExecutionProfileModel(
            id=f"profile-incompatible-{uuid4().hex[:8]}", run_id=run_id, idempotency_key="incompatible",
            request_checksum="request", policy_version="v2", status="resolved", source_angular_exact="11.0.0",
            selected_profile_id=profile["profile_id"], selected_checksum=profile["checksum"], profiles=[profile],
            blockers=[], guidance=[], artifact_ids=[], state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW,
        ))
        session.commit()
    binding = StageRuntimeApplicationService(
        authority=_SyntheticAuthority((("node12", "12.22.12", "8.19.4"), ("node22", "22.23.1", "10.9.8"))),
    ).resolve_stage(stage_id, "angular-11.x", "angular-12.x")
    assert binding.status == "bound"
    assert binding.descriptor_for(RuntimeExecutableKind.NODE).runtime_id == "node12"


def test_missing_stage_runtime_blocks():
    _, stage_id = _seed_families("angular-11.x", "angular-12.x")
    binding = StageRuntimeApplicationService(
        authority=_SyntheticAuthority((("node22", "22.23.1", "10.9.8"),)),
    ).resolve_stage(stage_id, "angular-11.x", "angular-12.x")
    assert binding.status == "blocked"


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
        assert row.operating_system == "windows"
        assert row.architecture == "amd64"
        assert row.installation_root

    # idempotent
    again = service.record_binding(run_id, binding, actor="test")
    assert len(again) == 3

    listed = service.list_stage_bindings(stage_id)
    assert len(listed) == 3

    with session_scope() as session:
        rows_db = session.query(StageRuntimeBindingModel).filter_by(stage_id=stage_id).all()
        assert len(rows_db) == 3


def test_record_binding_persists_runtime_descriptor_metadata():
    run_id, stage_id = _seed_run_and_stage()
    service = StageRuntimeApplicationService(
        authority=_SyntheticAuthority((("node22", "22.23.1", "8.19.4"),))
    )
    binding = service.resolve_stage(stage_id, "angular-18.x", "angular-19.x")
    rows = service.record_binding(run_id, binding, actor="test")
    assert {row.operating_system for row in rows} == {"windows"}
    assert {row.architecture for row in rows} == {"amd64"}
    assert {row.installation_root for row in rows} == {"C:/synthetic/node22"}


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
    available_authority = _SyntheticAuthority((("angular-stage-runtime", "22.23.1", "10.9.8"),))

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

    service._authority = available_authority
    recovered = service.resolve_stage("stage-blocked", "angular-18.x", "angular-19.x")
    assert recovered.status == "bound"
    rows = service.record_binding("run-stage-blocked", recovered)
    assert {row.status for row in rows} == {"bound"}
    assert all(row.resolved_path and row.sha256 for row in rows)
