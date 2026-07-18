import json
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
