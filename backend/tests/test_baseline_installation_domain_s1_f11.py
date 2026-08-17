"""Focused domain tests for S1-F11-I01."""

import json
from datetime import UTC, datetime

from app.domain.baseline_installation import BaselineInstallPrerequisites, BaselineInstallationError, FrozenBaselineCommandPolicy, FrozenBaselineInspectionService
from app.domain.contracts import CommandStatus


def test_frozen_command_has_exact_npm_ci_shape() -> None:
    command = FrozenBaselineCommandPolicy().create()
    request = command.request(run_id="run-1", runtime_profile_id="profile-1", timeout_seconds=60, idempotency_key="install-1", actor="operator", requested_at=datetime.now(UTC))
    assert request.command_id == "npm-ci-bootstrap"
    assert request.executable == "npm"
    assert request.arguments == ["ci"]
    assert request.shell is False
    assert request.working_directory_alias == "BASELINE_SANDBOX"
    assert request.network_profile == "approved-registries-only"


def test_success_requires_unchanged_inputs_and_dependency_tree(tmp_path) -> None:
    sandbox = tmp_path / "baseline"
    (sandbox / "node_modules").mkdir(parents=True)
    (sandbox / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    (sandbox / "package-lock.json").write_text('{"lockfileVersion":3}', encoding="utf-8")
    (sandbox / "node_modules" / ".package-lock.json").write_text(json.dumps({"packages": {"": {}, "node_modules/a": {}}}), encoding="utf-8")
    service = FrozenBaselineInspectionService()
    before_package, before_lockfile = service.inspect_before(sandbox)
    result = service.inspect_after(sandbox, before_package_json=before_package, before_lockfile=before_lockfile, command_status=CommandStatus.SUCCEEDED)
    assert result.status == "succeeded"
    assert result.reconstruction_required is False
    assert result.dependency_tree is not None
    assert result.dependency_tree.status == "verified"
    assert result.dependency_tree.package_count == 1


def test_npm6_manifest_inventory_verifies_without_hidden_package_lock(tmp_path) -> None:
    sandbox = tmp_path / "baseline"
    package = sandbox / "node_modules" / "example"
    package.mkdir(parents=True)
    (sandbox / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    (sandbox / "package-lock.json").write_text('{"lockfileVersion":1}', encoding="utf-8")
    (package / "package.json").write_text('{"name":"example","version":"1.2.3"}', encoding="utf-8")
    service = FrozenBaselineInspectionService()

    before_package, before_lockfile = service.inspect_before(sandbox)
    result = service.inspect_after(sandbox, before_package_json=before_package, before_lockfile=before_lockfile, command_status=CommandStatus.SUCCEEDED)

    assert result.status == "succeeded"
    assert result.reconstruction_required is False
    assert result.dependency_tree is not None
    assert result.dependency_tree.status == "verified"
    assert result.dependency_tree.package_count == 1


def test_changed_lockfile_blocks_and_requires_reconstruction(tmp_path) -> None:
    sandbox = tmp_path / "baseline"
    sandbox.mkdir()
    (sandbox / "package.json").write_text('{}', encoding="utf-8")
    (sandbox / "package-lock.json").write_text('{}', encoding="utf-8")
    service = FrozenBaselineInspectionService()
    before_package, before_lockfile = service.inspect_before(sandbox)
    (sandbox / "package-lock.json").write_text('{"changed":true}', encoding="utf-8")
    result = service.inspect_after(sandbox, before_package_json=before_package, before_lockfile=before_lockfile, command_status=CommandStatus.SUCCEEDED)
    assert result.status == "blocked"
    assert result.reconstruction_required is True
    assert result.blockers == ("PACKAGE_LOCK_CHANGED_AFTER_INSTALL",)


def test_npm_shrinkwrap_is_accepted_as_the_frozen_lockfile(tmp_path) -> None:
    sandbox = tmp_path / "baseline"
    sandbox.mkdir()
    (sandbox / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    (sandbox / "npm-shrinkwrap.json").write_text('{"lockfileVersion":3}', encoding="utf-8")
    service = FrozenBaselineInspectionService()

    before_package, before_lockfile = service.inspect_before(sandbox)
    result = service.inspect_after(sandbox, before_package_json=before_package, before_lockfile=before_lockfile, command_status=CommandStatus.FAILED)

    assert before_lockfile.path.endswith("npm-shrinkwrap.json")
    assert result.lockfile.path.endswith("npm-shrinkwrap.json")
    assert result.lockfile.present is True
def test_missing_install_prerequisite_fails_closed() -> None:
    prerequisites = BaselineInstallPrerequisites(True, True, True, False, True)
    try:
        prerequisites.validate()
    except BaselineInstallationError as error:
        assert error.code == "BASELINE_INSTALL_AUTHORIZATION_REQUIRED"
    else:
        raise AssertionError("missing install authorization must be rejected")
