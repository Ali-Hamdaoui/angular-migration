from pathlib import Path

import pytest

from app.delivery import DeliveryConflictPolicy, DeliveryError, DeliveryService
from app.snapshots import SnapshotService, SourceIntegrityVerifier, SourceManifestBuilder, WorkspacePathError
from app.workspaces import WorkspaceService


def _write_fixture_source(source_root: Path) -> None:
    (source_root / "src" / "app").mkdir(parents=True)
    (source_root / "src" / "app" / "app.component.ts").write_text("export const app = 'fixture';\n", encoding="utf-8")
    (source_root / "package.json").write_text('{"dependencies":{"@angular/core":"18.2.0"}}\n', encoding="utf-8")


def test_fixture_manifest_snapshot_workspace_and_delivery_flow(tmp_path: Path) -> None:
    source_root = tmp_path / "fixture-angular-18"
    target_root = tmp_path / "target"
    _write_fixture_source(source_root)

    manifest_builder = SourceManifestBuilder()
    manifest = manifest_builder.build(source_root)
    snapshot = SnapshotService(target_root / ".migration-factory" / "snapshots", manifest_builder).create_snapshot(
        source_root,
        "snapshot-001",
    )
    workspace = WorkspaceService(target_root / ".migration-factory" / "workspaces").create_workspace_from_snapshot(
        run_id="run-001",
        snapshot_root=snapshot.snapshot_root,
        source_root=source_root,
    )
    delivery = DeliveryService(target_root)

    assert manifest.entries
    assert manifest.checksum.startswith("sha256:")
    assert (snapshot.snapshot_root / "source-manifest.json").is_file()
    assert (workspace.repository_path / "package.json").is_file()
    assert not (source_root / ".migration-factory").exists()
    assert SourceIntegrityVerifier(manifest_builder).verify(source_root, snapshot.manifest)

    (workspace.repository_path / "MIGRATED.md").write_text("mock migrated output\n", encoding="utf-8")
    manifest_record = delivery.publish_mock_delivery(
        run_id="run-001",
        source_root=source_root,
        source_manifest=snapshot.manifest,
        workspace_repository=workspace.repository_path,
        run_status="COMPLETED",
        conflict_policy=DeliveryConflictPolicy.FAIL,
    )

    final_output = target_root / "migrated-app"
    assert final_output.is_dir()
    assert (final_output / "MIGRATED.md").read_text(encoding="utf-8") == "mock migrated output\n"
    assert manifest_record.status == "published"
    assert manifest_record.manifest_checksum is not None
    assert (target_root / "delivery-manifest.json").is_file()
    assert not list(target_root.glob(".migrated-app.run-001.tmp"))


def test_source_integrity_verification_detects_source_mutation(tmp_path: Path) -> None:
    source_root = tmp_path / "fixture-angular-18"
    _write_fixture_source(source_root)
    builder = SourceManifestBuilder()
    manifest = builder.build(source_root)

    (source_root / "package.json").write_text('{"dependencies":{"@angular/core":"18.3.0"}}\n', encoding="utf-8")

    assert SourceIntegrityVerifier(builder).verify(source_root, manifest) is False


def test_workspace_and_delivery_paths_must_not_overlap_source(tmp_path: Path) -> None:
    source_root = tmp_path / "fixture-angular-18"
    _write_fixture_source(source_root)

    with pytest.raises(WorkspacePathError):
        SnapshotService(source_root / ".migration-factory" / "snapshots").create_snapshot(
            source_root,
            "snapshot-overlap",
        )


def test_existing_output_conflict_requires_explicit_policy(tmp_path: Path) -> None:
    source_root = tmp_path / "fixture-angular-18"
    target_root = tmp_path / "target"
    _write_fixture_source(source_root)
    snapshot = SnapshotService(target_root / ".migration-factory" / "snapshots").create_snapshot(source_root, "snapshot-001")
    workspace = WorkspaceService(target_root / ".migration-factory" / "workspaces").create_workspace_from_snapshot(
        run_id="run-001",
        snapshot_root=snapshot.snapshot_root,
        source_root=source_root,
    )
    (target_root / "migrated-app").mkdir(parents=True)

    with pytest.raises(DeliveryError):
        DeliveryService(target_root).publish_mock_delivery(
            run_id="run-001",
            source_root=source_root,
            source_manifest=snapshot.manifest,
            workspace_repository=workspace.repository_path,
            run_status="COMPLETED",
        )


def test_failed_and_cancelled_runs_do_not_publish_output(tmp_path: Path) -> None:
    source_root = tmp_path / "fixture-angular-18"
    target_root = tmp_path / "target"
    _write_fixture_source(source_root)
    snapshot = SnapshotService(target_root / ".migration-factory" / "snapshots").create_snapshot(source_root, "snapshot-001")
    workspace = WorkspaceService(target_root / ".migration-factory" / "workspaces").create_workspace_from_snapshot(
        run_id="run-001",
        snapshot_root=snapshot.snapshot_root,
        source_root=source_root,
    )
    service = DeliveryService(target_root)

    for status in ("FAILED", "CANCELLED"):
        manifest = service.publish_mock_delivery(
            run_id=f"run-{status.lower()}",
            source_root=source_root,
            source_manifest=snapshot.manifest,
            workspace_repository=workspace.repository_path,
            run_status=status,
        )
        assert manifest.status == "blocked"
        assert not (target_root / "migrated-app").exists()
