import json
from types import SimpleNamespace

from app.domain.baseline_matrix import BaselineTargetDiscoveryService, BaselineTargetKind, BaselineTargetStatus, normalize_command_result
from app.services.baseline_validation_application_service import BaselineValidationApplicationService


def test_discovery_is_read_only_and_does_not_execute_package_scripts(tmp_path):
    package = {"scripts": {"build": "echo SAFE", "test": "node -e \"require('fs').writeFileSync('mutated', 'no')\""}}
    package_path = tmp_path / "package.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    inventory = BaselineTargetDiscoveryService().discover(tmp_path)

    assert not (tmp_path / "mutated").exists()
    assert package_path.read_text(encoding="utf-8") == json.dumps(package)
    assert inventory.package_json_checksum.startswith("sha256:")


def test_custom_builder_is_blocked_and_never_becomes_an_executable_command(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "angular.json").write_text(json.dumps({"projects": {"app": {"architect": {"build": {"builder": "untrusted:builder"}}}}}), encoding="utf-8")

    target = next(item for item in BaselineTargetDiscoveryService().discover(tmp_path).targets if item.kind is BaselineTargetKind.BUILD)
    result = normalize_command_result(target, exit_code=None, duration_ms=None)

    assert target.supported is False
    assert target.executable == ""
    assert result.status is BaselineTargetStatus.BLOCKED


def test_missing_lint_is_not_a_successful_validation(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")

    lint = next(item for item in BaselineTargetDiscoveryService().discover(tmp_path).targets if item.kind is BaselineTargetKind.LINT)
    result = normalize_command_result(lint, exit_code=0, duration_ms=0)

    assert result.status is BaselineTargetStatus.SKIPPED_NOT_CONFIGURED


def test_runtime_environment_passes_only_a_valid_explicit_chrome_binary(tmp_path, monkeypatch):
    chrome = tmp_path / "chrome.exe"
    chrome.write_bytes(b"")
    monkeypatch.setenv("CHROME_BIN", str(chrome))
    selected = {
        "profile_id": "node12-npm8", "checksum": "sha256:runtime",
        "node_executable": str(tmp_path / "node.exe"),
        "package_manager_executable": str(tmp_path / "npm.cmd"),
        "npx_executable": str(tmp_path / "npx.cmd"),
    }
    profile = SimpleNamespace(
        selected_profile_id="node12-npm8", selected_checksum="sha256:runtime", profiles=[selected],
    )

    environment = BaselineValidationApplicationService._runtime_environment(profile)

    assert environment["CHROME_BIN"] == str(chrome)
