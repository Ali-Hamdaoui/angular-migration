from pathlib import Path

import pytest

from app.services.migration_workspace_layout_service import MigrationWorkspaceLayoutService, WorkspaceLayoutError


def test_layout_derives_every_runtime_alias_under_external_output(tmp_path: Path) -> None:
    repository = tmp_path / "platform"
    output = tmp_path / "migration-results" / "Customer Portal-angular-21"
    layout = MigrationWorkspaceLayoutService(platform_repository_root=repository).for_run(output, "run-123")

    assert layout.migrated_app == output / "migrated-app"
    assert layout.artifact_root == output / ".migration-factory" / "runs" / "run-123" / "artifacts"
    assert layout.log_root.parent == layout.run_root
    assert layout.report_root.parent == layout.run_root
    assert layout.temporary_root.parent == layout.run_root
    assert all(Path(path).is_relative_to(output) for path in layout.aliases().values())


def test_layout_rejects_platform_repository_overlap(tmp_path: Path) -> None:
    service = MigrationWorkspaceLayoutService(platform_repository_root=tmp_path / "platform")
    with pytest.raises(WorkspaceLayoutError, match="platform repository"):
        service.for_run(tmp_path / "platform" / "output", "run-123")

