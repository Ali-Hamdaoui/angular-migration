import json

import pytest

from app.services.project_planning_resolver import ProjectPlanningResolver, ProjectPlanningResolutionError


def _workspace(tmp_path, angular, scripts=None, lockfile="package-lock.json"):
    (tmp_path / "angular.json").write_text(json.dumps(angular), encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"scripts": scripts or {}}), encoding="utf-8")
    (tmp_path / lockfile).write_text("{}", encoding="utf-8")
    return tmp_path


def test_resolves_application_target_without_inventing_project_or_configuration(tmp_path):
    result = ProjectPlanningResolver().resolve(_workspace(tmp_path, {
        "projects": {"portal": {"projectType": "application", "architect": {
            "build": {"builder": "@angular-devkit/build-angular:application", "configurations": {"production": {}}},
            "test": {"builder": "@angular-devkit/build-angular:karma"},
        }}}
    }, {"build": "ng build portal", "test": "ng test portal"}))

    assert result.build_targets[0].project == "portal"
    assert result.build_targets[0].configuration == "production"
    assert result.build_targets[0].builder.endswith(":application")
    assert result.test_targets[0].project == "portal"


def test_resolves_library_target_and_does_not_create_lint_command_when_absent(tmp_path):
    result = ProjectPlanningResolver().resolve(_workspace(tmp_path, {
        "projects": {"shared": {"projectType": "library", "targets": {
            "build": {"builder": "@angular-devkit/build-angular:ng-packagr"}
        }}}
    }))

    assert result.build_targets[0].kind == "library"
    assert result.lint_targets == ()
    assert "LINT_NOT_CONFIGURED" in result.findings


def test_rejects_unsupported_package_manager_before_commands_are_generated(tmp_path):
    with pytest.raises(ProjectPlanningResolutionError, match="UNSUPPORTED_PACKAGE_MANAGER"):
        ProjectPlanningResolver().resolve(_workspace(tmp_path, {"projects": {}}, lockfile="pnpm-lock.yaml"))
