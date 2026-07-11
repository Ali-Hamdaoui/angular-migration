"""Source manifest, snapshot, and integrity services for Sprint 0."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath


class WorkspacePathError(ValueError):
    """Raised when source, snapshot, workspace, or delivery paths overlap."""


@dataclass(frozen=True)
class SourceManifestEntry:
    relative_path: str
    size_bytes: int
    checksum: str


@dataclass(frozen=True)
class SourceManifest:
    manifest_id: str
    source_root: str
    generated_at: datetime
    entries: tuple[SourceManifestEntry, ...]

    @property
    def checksum(self) -> str:
        payload = json.dumps(
            [asdict(entry) for entry in self.entries],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    snapshot_root: Path
    manifest: SourceManifest


def ensure_non_overlapping_paths(*paths: Path) -> None:
    resolved = [path.resolve() for path in paths]
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if left == right or _is_relative_to(left, right) or _is_relative_to(right, left):
                raise WorkspacePathError(f"paths must not overlap: {left} and {right}")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


class SourceManifestBuilder:
    """Build a deterministic file manifest for an immutable source root."""

    def build(self, source_root: Path, *, generated_at: datetime | None = None) -> SourceManifest:
        source_root = source_root.resolve()
        if not source_root.is_dir():
            raise FileNotFoundError(f"source root does not exist: {source_root}")
        entries = tuple(
            SourceManifestEntry(
                relative_path=file_path.relative_to(source_root).as_posix(),
                size_bytes=file_path.stat().st_size,
                checksum=_checksum_file(file_path),
            )
            for file_path in sorted(path for path in source_root.rglob("*") if path.is_file())
            if _is_safe_relative(file_path.relative_to(source_root))
        )
        generated_at = generated_at or datetime.now(UTC)
        manifest_payload = ":".join(entry.checksum for entry in entries).encode("utf-8")
        manifest_id = f"manifest-{hashlib.sha256(manifest_payload).hexdigest()[:16]}"
        return SourceManifest(
            manifest_id=manifest_id,
            source_root=str(source_root),
            generated_at=generated_at,
            entries=entries,
        )

    def write_manifest(self, manifest: SourceManifest, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "manifest_id": manifest.manifest_id,
            "source_root": manifest.source_root,
            "generated_at": manifest.generated_at.isoformat(),
            "checksum": manifest.checksum,
            "entries": [asdict(entry) for entry in manifest.entries],
        }
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return destination


class SourceIntegrityVerifier:
    """Verify that the original source still matches its manifest."""

    def __init__(self, manifest_builder: SourceManifestBuilder | None = None) -> None:
        self._manifest_builder = manifest_builder or SourceManifestBuilder()

    def verify(self, source_root: Path, manifest: SourceManifest) -> bool:
        current = self._manifest_builder.build(source_root, generated_at=manifest.generated_at)
        expected = [(entry.relative_path, entry.size_bytes, entry.checksum) for entry in manifest.entries]
        actual = [(entry.relative_path, entry.size_bytes, entry.checksum) for entry in current.entries]
        return expected == actual


class SnapshotService:
    """Create immutable source snapshots under the configured snapshot root."""

    def __init__(self, snapshot_root: Path, manifest_builder: SourceManifestBuilder | None = None) -> None:
        self._snapshot_root = snapshot_root
        self._manifest_builder = manifest_builder or SourceManifestBuilder()

    @property
    def snapshot_root(self) -> Path:
        return self._snapshot_root

    def create_snapshot(self, source_root: Path, snapshot_id: str) -> SnapshotRecord:
        source_root = source_root.resolve()
        snapshot_path = (self._snapshot_root / snapshot_id).resolve()
        ensure_non_overlapping_paths(source_root, snapshot_path)
        if snapshot_path.exists():
            raise FileExistsError(f"snapshot already exists: {snapshot_path}")
        manifest = self._manifest_builder.build(source_root)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_root, snapshot_path)
        self._manifest_builder.write_manifest(manifest, snapshot_path / "source-manifest.json")
        return SnapshotRecord(snapshot_id=snapshot_id, snapshot_root=snapshot_path, manifest=manifest)


def _checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _is_safe_relative(relative_path: Path) -> bool:
    posix = PurePosixPath(relative_path.as_posix())
    return not posix.is_absolute() and ".." not in posix.parts
