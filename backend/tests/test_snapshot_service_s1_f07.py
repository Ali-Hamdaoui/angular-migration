from pathlib import Path

import pytest

from app.snapshots import (
    SnapshotIntegrityError,
    SnapshotLinkError,
    SnapshotService,
)


def _source(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.ts").write_text("export const app = true;\n", encoding="utf-8")
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "node_modules" / "pkg" / "generated.js").write_text("generated", encoding="utf-8")
    (root / "dist").mkdir()
    (root / "dist" / "bundle.js").write_text("bundle", encoding="utf-8")


def test_snapshot_records_policy_exclusions_fingerprint_and_can_be_inspected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _source(source)
    service = SnapshotService(tmp_path / "output" / ".migration-factory" / "runs" / "run-1" / "source-snapshot")

    created = service.create_snapshot(source, "snapshot-1")
    inspected = service.inspect_snapshot("snapshot-1")

    assert created.fingerprint.startswith("sha256:")
    assert inspected.fingerprint == created.fingerprint
    assert [entry.relative_path for entry in inspected.manifest.entries] == ["src/app.ts"]
    assert {item.relative_path for item in inspected.manifest.exclusions} == {"dist", "node_modules"}
    assert not (created.snapshot_root / "node_modules").exists()
    assert (created.snapshot_root / "source-manifest.json").is_file()


def test_snapshot_rejects_links_and_never_leaves_incomplete_copy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "real.txt").write_text("safe", encoding="utf-8")
    link = source / "link.txt"
    try:
        link.symlink_to(source / "real.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable")
    service = SnapshotService(tmp_path / "snapshots")
    with pytest.raises(SnapshotLinkError):
        service.create_snapshot(source, "snapshot-1")
    assert not (tmp_path / "snapshots" / "snapshot-1").exists()
    assert not list((tmp_path / "snapshots").glob(".*.copying-*"))


def test_snapshot_detects_source_change_during_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("before", encoding="utf-8")
    service = SnapshotService(tmp_path / "snapshots")
    original = service._manifest_builder.build
    calls = 0

    def build_with_change(root: Path, *, generated_at=None):
        nonlocal calls
        calls += 1
        result = original(root, generated_at=generated_at)
        if calls == 1:
            (root / "file.txt").write_text("after", encoding="utf-8")
        return result

    monkeypatch.setattr(service._manifest_builder, "build", build_with_change)
    with pytest.raises(SnapshotIntegrityError):
        service.create_snapshot(source, "snapshot-1")
    assert not (tmp_path / "snapshots" / "snapshot-1").exists()
