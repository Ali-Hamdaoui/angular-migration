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


def test_accepts_bom_prefixed_angular_json(tmp_path):
    workspace = _workspace(tmp_path, {
        "projects": {"portal": {"projectType": "application", "targets": {
            "build": {"builder": "@angular-devkit/build-angular:application"},
        }}},
    })
    (workspace / "angular.json").write_bytes(b"\xef\xbb\xbf" + (workspace / "angular.json").read_bytes())

    result = ProjectPlanningResolver().resolve(workspace)

    assert result.build_targets[0].project == "portal"


def test_reports_malformed_angular_json_without_collapsing_the_reader_code(tmp_path):
    workspace = _workspace(tmp_path, {"projects": {}})
    (workspace / "angular.json").write_text('{"projects":', encoding="utf-8")

    with pytest.raises(ProjectPlanningResolutionError, match="WORKSPACE_JSON_SYNTAX_INVALID"):
        ProjectPlanningResolver().resolve(workspace)


@pytest.mark.parametrize(
    ("angular", "message"),
    [
        ({"projects": []}, "ANGULAR_PROJECTS_INVALID"),
        ({"projects": {"portal": []}}, "ANGULAR_PROJECT_INVALID"),
        ({"projects": {"portal": {"architect": []}}}, "ANGULAR_TARGET_INVALID"),
        ({"projects": {"portal": {"architect": {"build": []}}}}, "ANGULAR_TARGET_INVALID"),
    ],
)
def test_rejects_invalid_angular_workspace_shapes(tmp_path, angular, message):
    with pytest.raises(ProjectPlanningResolutionError, match=message):
        ProjectPlanningResolver().resolve(_workspace(tmp_path, angular))


def test_does_not_select_first_project_when_multiple_applications_exist(tmp_path):
    result = ProjectPlanningResolver().resolve(_workspace(tmp_path, {
        "projects": {
            "first": {"projectType": "application", "targets": {"build": {"builder": "builder:first"}}},
            "approved": {"projectType": "application", "targets": {"build": {"builder": "builder:approved"}}},
        },
    }))

    with pytest.raises(ProjectPlanningResolutionError, match="AMBIGUOUS_ANGULAR_PROJECT_SELECTION"):
        result.select_build_target()
    assert result.select_build_target(project_name="approved").builder == "builder:approved"


def test_prefers_the_only_application_over_a_library_regardless_of_json_order(tmp_path):
    result = ProjectPlanningResolver().resolve(_workspace(tmp_path, {
        "projects": {
            "shared": {"projectType": "library", "targets": {"build": {"builder": "@angular-devkit/build-angular:ng-packagr"}}},
            "app": {"projectType": "application", "targets": {"build": {"builder": "@angular-devkit/build-angular:application"}}},
        },
    }))

    assert result.select_build_target().project == "app"
