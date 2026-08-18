import json
from pathlib import Path

from app.services.dependency_closure_service import (
    compatible_reinstall_bundle,
    compatible_reinstall_version,
    installed_dependency_version,
    verify_dependency_transition_evidence_for_source,
)


def test_installed_dependency_version_reads_npm_v1_lockfile_without_node_modules(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 1,
                "dependencies": {
                    "@angular-devkit/build-angular": {
                        "version": "12.0.5",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    assert (
        installed_dependency_version(workspace, "@angular-devkit/build-angular")
        == "12.0.5"
    )


def test_angular_13_build_tool_transition_binds_peer_compatible_versions(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "package.json").write_text(
        json.dumps(
            {
                "devDependencies": {
                    "@angular-devkit/build-angular": "~12.0.0",
                    "typescript": "~4.2.4",
                }
            }
        ),
        encoding="utf-8",
    )

    assert (
        compatible_reinstall_version("@angular-devkit/build-angular", 13)
        == "13.0.4"
    )
    bundle = compatible_reinstall_bundle(
        "@angular-devkit/build-angular", 13, workspace
    )
    assert [(item.package, item.exact_version) for item in bundle.members] == [
        ("typescript", "4.4.4"),
        ("@angular-devkit/build-angular", "13.0.4"),
    ]


def test_angular_update_peer_evidence_accepts_npm_v1_checkpoint_without_node_modules(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    package = "@angular-devkit/build-angular"
    (workspace / "package.json").write_text(
        json.dumps({"devDependencies": {package: "~12.0.0"}}),
        encoding="utf-8",
    )
    (workspace / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 1,
                "dependencies": {package: {"version": "12.0.5"}},
            }
        ),
        encoding="utf-8",
    )

    verify_dependency_transition_evidence_for_source(
        workspace,
        diagnosis={"kind": "peer_dependency_conflict", "source": None},
        package=package,
        installed_version="12.0.5",
        peer_ranges={"typescript": "~4.4.3"},
    )
