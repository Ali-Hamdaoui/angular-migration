import os
import subprocess
from pathlib import Path

import pytest

from app.snapshots import SnapshotIntegrityError, SnapshotLinkError, SnapshotService, WorkspacePathError


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

    (created.snapshot_root / "app.ts").chmod(0o644)
    (created.snapshot_root / "app.ts").write_text("tampered", encoding="utf-8")

    with pytest.raises(SnapshotIntegrityError, match="snapshot file checksum"):
        service.inspect_snapshot("snapshot-1")


def test_inspection_requires_fingerprint_evidence(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.ts").write_text("original", encoding="utf-8")
    service = SnapshotService(tmp_path / "snapshots")
    created = service.create_snapshot(source, "snapshot-1")
    fingerprint = created.snapshot_root / "snapshot-fingerprint.json"
    fingerprint.chmod(0o644)
    created.snapshot_root.chmod(0o755)
    fingerprint.unlink()

    with pytest.raises(FileNotFoundError, match="snapshot-fingerprint"):
        service.inspect_snapshot("snapshot-1")


def test_snapshot_destination_cannot_escape_registered_root(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.ts").write_text("safe", encoding="utf-8")
    service = SnapshotService(tmp_path / "snapshots")

    with pytest.raises(ValueError):
        service.create_snapshot(source, "../outside")

def test_completed_snapshot_files_are_read_only(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.ts").write_text("original", encoding="utf-8")
    created = SnapshotService(tmp_path / "snapshots").create_snapshot(source, "snapshot-1")

    assert (created.snapshot_root / "app.ts").stat().st_mode & 0o200 == 0
    assert created.snapshot_root.stat().st_mode & 0o200 == 0


def test_long_nested_paths_are_manifested_without_source_mutation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    nested = source
    for index in range(12):
        nested /= f"directory-{index:02d}-with-a-long-name"
    nested.mkdir(parents=True)
    source_file = nested / "application.component.ts"
    source_file.write_text("export const value = true;", encoding="utf-8")

    created = SnapshotService(tmp_path / "snapshots").create_snapshot(source, "snapshot-1")

    relative = source_file.relative_to(source).as_posix()
    assert [entry.relative_path for entry in created.manifest.entries] == [relative]
    assert source_file.read_text(encoding="utf-8") == "export const value = true;"


def test_transient_copy_error_is_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.ts").write_text("safe", encoding="utf-8")
    service = SnapshotService(tmp_path / "snapshots")
    original_copy = __import__("app.snapshots.services", fromlist=["shutil"]).shutil.copy2
    attempts = 0

    def flaky_copy(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("transient sharing violation")
        return original_copy(*args, **kwargs)

    monkeypatch.setattr("app.snapshots.services.shutil.copy2", flaky_copy)
    service.create_snapshot(source, "snapshot-1")

    assert attempts >= 2

@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_windows_junction_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    outside = tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    (outside / "escaped.ts").write_text("outside", encoding="utf-8")
    junction = source / "linked-directory"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"junction creation unavailable: {result.stderr.strip()}")

    with pytest.raises(SnapshotLinkError, match="link|reparse"):
        SnapshotService(tmp_path / "snapshots").create_snapshot(source, "snapshot-1")


def test_manifest_order_is_stable_across_case_variants(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "B.ts").write_text("upper", encoding="utf-8")
    (source / "a.ts").write_text("lower", encoding="utf-8")

    record = SnapshotService(tmp_path / "snapshots").create_snapshot(source, "snapshot-1")

    assert [entry.relative_path for entry in record.manifest.entries] == ["a.ts", "B.ts"]