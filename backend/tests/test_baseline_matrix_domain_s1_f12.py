import json

import pytest

from app.domain.baseline_matrix import BaselineTargetDiscoveryService, BaselineTargetKind, BaselineTargetStatus, BaselineMatrixError, normalize_command_result


def test_discovers_production_build_and_configured_script_targets(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8")
    (tmp_path / "angular.json").write_text(json.dumps({"projects": {"app": {"architect": {"build": {"builder": "@angular-devkit/build-angular:application", "configurations": {"production": {}}}}}}}), encoding="utf-8")

    inventory = BaselineTargetDiscoveryService().discover(tmp_path)

    build = next(item for item in inventory.targets if item.kind is BaselineTargetKind.BUILD)
    assert build.arguments == ("ng", "build", "app", "--configuration", "production")
    assert any(item.target_id == "script:test" for item in inventory.targets)


def test_missing_lint_is_explicitly_not_configured(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    inventory = BaselineTargetDiscoveryService().discover(tmp_path)
    lint = next(item for item in inventory.targets if item.kind is BaselineTargetKind.LINT)

    result = normalize_command_result(lint, exit_code=None, duration_ms=0)
    assert result.status is BaselineTargetStatus.SKIPPED_NOT_CONFIGURED


def test_unsupported_custom_target_is_blocked(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "angular.json").write_text(json.dumps({"projects": {"app": {"architect": {"build": {"builder": "vendor:custom"}}}}}), encoding="utf-8")

    inventory = BaselineTargetDiscoveryService().discover(tmp_path)
    target = next(item for item in inventory.targets if item.kind is BaselineTargetKind.BUILD)
    assert normalize_command_result(target, exit_code=None, duration_ms=None).status is BaselineTargetStatus.BLOCKED


def test_invalid_package_metadata_fails_closed(tmp_path):
    (tmp_path / "package.json").write_text("not json", encoding="utf-8")
    with pytest.raises(BaselineMatrixError, match="PACKAGE_JSON_INVALID"):
        BaselineTargetDiscoveryService().discover(tmp_path)
