import json
from datetime import UTC, datetime
from pathlib import Path

from app.domain.baseline import (
    BaselinePrequalificationService,
    DependencySource,
    LifecycleClassification,
    LockfilePrequalificationService,
    PackageMetadataInspector,
    PackageSourceInventory,
    LifecycleScriptAuditor,
)
from app.domain.execution_profile import RuntimeCandidate, RuntimeResolutionRequest, SourceRuntimeResolver


def _profile(**changes):
    candidate = RuntimeCandidate(
        profile_id="node-20",
        node_executable=r"C:\Tools\node\node.exe",
        node_exact="20.11.1",
        npm_executable=r"C:\Tools\node\npm.cmd",
        npm_exact="10.2.4",
        npx_executable=r"C:\Tools\node\npx.cmd",
        npx_exact="10.2.4",
        **changes,
    )
    result = SourceRuntimeResolver().resolve(RuntimeResolutionRequest(source_angular_exact="18.2.3", source_typescript_exact="5.5.4", source_rxjs_exact="7.8.1", candidates=(candidate,), validated_at=datetime(2026, 7, 15, tzinfo=UTC)))
    assert result.selected_profile is not None
    return result.selected_profile


def _package(root: Path, *, dependency="1.0.0", locked="1.0.0", script=None):
    (root / "package.json").write_text(json.dumps({
        "name": "fixture",
        "dependencies": {"example": dependency},
        "scripts": {"postinstall": script} if script else {},
    }), encoding="utf-8")
    (root / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {"": {"dependencies": {"example": locked}}, "node_modules/example": {"version": locked}},
    }), encoding="utf-8")


def test_lockfile_mismatch_is_blocked_without_rewriting_metadata(tmp_path: Path):
    _package(tmp_path, locked="2.0.0")
    package_before = (tmp_path / "package.json").read_bytes()
    lockfile_before = (tmp_path / "package-lock.json").read_bytes()

    package = PackageMetadataInspector().inspect(tmp_path)
    result = LockfilePrequalificationService().inspect(tmp_path, package)

    assert result.status == "blocked"
    assert "NPM_LOCKFILE_VERSION_MISMATCH:example" in result.blockers
    assert (tmp_path / "package.json").read_bytes() == package_before
    assert (tmp_path / "package-lock.json").read_bytes() == lockfile_before


def test_legacy_v1_lockfile_resolves_root_dependencies(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"example": "^1.0.0"}}), encoding="utf-8")
    (tmp_path / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 1,
        "requires": True,
        "dependencies": {"example": {"version": "1.2.3", "resolved": "https://registry.npmjs.org/example/-/example-1.2.3.tgz"}},
    }), encoding="utf-8")

    package = PackageMetadataInspector().inspect(tmp_path)
    result = LockfilePrequalificationService().inspect(tmp_path, package)

    assert result.status == "valid"
    assert result.lockfile_version == 1
    assert result.blockers == ()


def test_source_inventory_classifies_non_registry_sources(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {
        "git-dep": "git+https://example.test/repo.git",
        "local-dep": "file:../local-dep",
        "tar-dep": "https://example.test/pkg.tgz",
        "regular": "^1.0.0",
    }}), encoding="utf-8")
    package = PackageMetadataInspector().inspect(tmp_path)
    entries = PackageSourceInventory().inspect(package)

    assert {entry.name: entry.source for entry in entries} == {
        "git-dep": DependencySource.GIT,
        "local-dep": DependencySource.LOCAL_FILE,
        "tar-dep": DependencySource.TARBALL,
        "regular": DependencySource.PUBLIC_REGISTRY,
    }


def test_sensitive_lifecycle_script_requires_review_or_is_blocked(tmp_path: Path):
    _package(tmp_path, script="node scripts/setup.js")
    package = PackageMetadataInspector().inspect(tmp_path)
    audit = LifecycleScriptAuditor().inspect(package)
    assert audit[0].classification is LifecycleClassification.RESTRICTED

    _package(tmp_path, script="powershell -Command Invoke-WebRequest https://example.test")
    package = PackageMetadataInspector().inspect(tmp_path)
    audit = LifecycleScriptAuditor().inspect(package)
    assert audit[0].classification is LifecycleClassification.BLOCKED


def test_prequalification_requires_execution_profile_before_install_authorization(tmp_path: Path):
    _package(tmp_path)
    result = BaselinePrequalificationService().qualify(tmp_path)
    assert result.status == "blocked"
    assert "EXECUTION_PROFILE_REQUIRED" in result.blockers
    assert not result.install_authorized


def test_direct_public_registry_without_proxy_is_qualified(tmp_path: Path):
    _package(tmp_path)
    result = BaselinePrequalificationService().qualify(tmp_path, execution_profile=_profile(proxy_configured=False))
    assert result.status == "qualified"
    assert result.registry.proxy_configured is False


def test_approved_proxy_is_qualified(tmp_path: Path):
    _package(tmp_path)
    result = BaselinePrequalificationService().qualify(tmp_path, execution_profile=_profile(proxy_configured=True))
    assert result.status == "qualified"


def test_required_proxy_missing_is_blocked(tmp_path: Path):
    _package(tmp_path)
    profile = _profile(proxy_configured=False).model_copy(update={"proxy_profile": "required"})
    result = BaselinePrequalificationService().qualify(tmp_path, execution_profile=profile)
    assert result.status == "blocked"
    assert "REGISTRY_PROXY_UNAVAILABLE" in result.blockers


def test_invalid_registry_certificate_is_blocked(tmp_path: Path):
    _package(tmp_path)
    profile = _profile().model_copy(update={"certificate_profile": "invalid"})
    result = BaselinePrequalificationService().qualify(tmp_path, execution_profile=profile)
    assert result.status == "blocked"
    assert "REGISTRY_CERTIFICATE_INVALID" in result.blockers
