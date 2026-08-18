import json
from pathlib import Path

from app.services.dependency_closure_service import installed_dependency_version


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
