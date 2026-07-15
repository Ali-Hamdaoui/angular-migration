from pathlib import Path

import pytest

from app.snapshots import SnapshotIntegrityError, SnapshotService, WorkspacePathError


def test_source_inside_platform_repository_is_rejected(tmp_path: Path) -> None:
    platform = tmp_path / "platform"
    source = platform / "checked-out-project"
    source.mkdir(parents=True)
    (source / "app.ts").write_text("safe", encoding="utf-8")

    service = SnapshotService(
        tmp_path / "output" / "runs" / "run-1" / "source-snapshot",
        platform_repository_root=platform,
    )

    with pytest.raises(WorkspacePathError, match="source root"):
        service.create_snapshot(source, "snapshot-1")


def test_inspection_detects_tampered_snapshot_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.ts").write_text("original", encoding="utf-8")
    service = SnapshotService(tmp_path / "snapshots")
    created = service.create_snapshot(source, "snapshot-1")

    (created.snapshot_root / "app.ts").write_text("tampered", encoding="utf-8")

    with pytest.raises(SnapshotIntegrityError, match="snapshot file checksum"):
        service.inspect_snapshot("snapshot-1")


def test_inspection_requires_fingerprint_evidence(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.ts").write_text("original", encoding="utf-8")
    service = SnapshotService(tmp_path / "snapshots")
    created = service.create_snapshot(source, "snapshot-1")
    (created.snapshot_root / "snapshot-fingerprint.json").unlink()

    with pytest.raises(FileNotFoundError, match="snapshot-fingerprint"):
        service.inspect_snapshot("snapshot-1")


def test_snapshot_destination_cannot_escape_registered_root(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.ts").write_text("safe", encoding="utf-8")
    service = SnapshotService(tmp_path / "snapshots")

    with pytest.raises(ValueError):
        service.create_snapshot(source, "../outside")