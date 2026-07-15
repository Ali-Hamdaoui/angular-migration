"""Deterministic, immutable source snapshot domain services."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Iterable


class WorkspacePathError(ValueError):
    """Raised when source, snapshot, or workspace paths overlap or escape."""


class SnapshotIntegrityError(RuntimeError):
    """Raised when the source changes while a snapshot is being created."""


class SnapshotLinkError(ValueError):
    """Raised when a source contains a link that cannot be copied safely."""


@dataclass(frozen=True)
class SnapshotPolicy:
    version: str = "source-snapshot-policy-v1"
    excluded_directories: tuple[str, ...] = ("node_modules", ".angular/cache", "dist", "coverage")

    def excludes(self, relative_path: Path) -> bool:
        normalized = PurePosixPath(relative_path.as_posix())
        return any(
            normalized == PurePosixPath(directory)
            or PurePosixPath(directory) in normalized.parents
            for directory in self.excluded_directories
        )


@dataclass(frozen=True)
class SourceManifestEntry:
    relative_path: str
    size_bytes: int
    checksum: str


@dataclass(frozen=True)
class SourceExclusion:
    relative_path: str
    reason: str
    policy_version: str


@dataclass(frozen=True)
class SourceManifest:
    manifest_id: str
    source_root: str
    generated_at: datetime
    entries: tuple[SourceManifestEntry, ...]
    exclusions: tuple[SourceExclusion, ...] = ()
    policy_version: str = "source-snapshot-policy-v1"

    @property
    def checksum(self) -> str:
        payload = json.dumps(
            {
                "entries": [asdict(entry) for entry in self.entries],
                "exclusions": [asdict(item) for item in self.exclusions],
                "policy_version": self.policy_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"


@dataclass(frozen=True)
class GitMetadata:
    available: bool
    head: str | None = None
    branch: str | None = None


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    snapshot_root: Path
    manifest: SourceManifest
    fingerprint: str = ""
    git_metadata: GitMetadata = GitMetadata(available=False)


def ensure_non_overlapping_paths(*paths: Path) -> None:
    resolved = [path.resolve(strict=False) for path in paths]
    for index, left in enumerate(resolved):
        for right in resolved[index + 1:]:
            if left == right or _is_relative_to(left, right) or _is_relative_to(right, left):
                raise WorkspacePathError(f"paths must not overlap: {left} and {right}")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


class SourceManifestBuilder:
    """Build a deterministic manifest using an explicit inclusion policy."""

    def __init__(self, policy: SnapshotPolicy | None = None, *, retries: int = 2) -> None:
        self.policy = policy or SnapshotPolicy()
        self.retries = max(0, retries)

    def build(self, source_root: Path, *, generated_at: datetime | None = None) -> SourceManifest:
        source_root = source_root.resolve(strict=True)
        if not source_root.is_dir():
            raise FileNotFoundError(f"source root does not exist: {source_root}")

        entries: list[SourceManifestEntry] = []
        exclusions: list[SourceExclusion] = []
        for file_path in _walk_source(source_root, self.policy, exclusions):
            relative = file_path.relative_to(source_root)
            if file_path.is_symlink():
                raise SnapshotLinkError(f"source link is not allowed: {relative.as_posix()}")
            size, checksum = _file_evidence(file_path, self.retries)
            entries.append(SourceManifestEntry(relative.as_posix(), size, checksum))

        entries.sort(key=lambda item: (item.relative_path.casefold(), item.relative_path))
        exclusions.sort(key=lambda item: item.relative_path)
        generated_at = generated_at or datetime.now(UTC)
        identity = json.dumps(
            {
                "entries": [asdict(entry) for entry in entries],
                "exclusions": [asdict(item) for item in exclusions],
                "policy_version": self.policy.version,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        manifest_id = f"manifest-{hashlib.sha256(identity).hexdigest()[:16]}"
        return SourceManifest(
            manifest_id=manifest_id,
            source_root=str(source_root),
            generated_at=generated_at,
            entries=tuple(entries),
            exclusions=tuple(exclusions),
            policy_version=self.policy.version,
        )

    def write_manifest(self, manifest: SourceManifest, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(manifest)
        payload["generated_at"] = manifest.generated_at.isoformat()
        payload["checksum"] = manifest.checksum
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return destination


class SourceIntegrityVerifier:
    """Verify that the original source still matches its manifest."""

    def __init__(self, manifest_builder: SourceManifestBuilder | None = None) -> None:
        self._manifest_builder = manifest_builder or SourceManifestBuilder()

    def verify(self, source_root: Path, manifest: SourceManifest) -> bool:
        current = self._manifest_builder.build(source_root, generated_at=manifest.generated_at)
        return _manifest_content(current) == _manifest_content(manifest)


class SnapshotService:
    """Create and inspect immutable source snapshots under a registered root."""

    def __init__(
        self,
        snapshot_root: Path,
        manifest_builder: SourceManifestBuilder | None = None,
        *,
        platform_repository_root: Path | None = None,
    ) -> None:
        self._snapshot_root = snapshot_root.resolve(strict=False)
        self._manifest_builder = manifest_builder or SourceManifestBuilder()
        self._platform_repository_root = (
            platform_repository_root.resolve(strict=False) if platform_repository_root else None
        )
        if self._platform_repository_root and _is_relative_to(
            self._snapshot_root, self._platform_repository_root
        ):
            raise WorkspacePathError("snapshot root must not be inside the platform repository")

    @property
    def snapshot_root(self) -> Path:
        return self._snapshot_root

    def create_snapshot(self, source_root: Path, snapshot_id: str) -> SnapshotRecord:
        source_root = source_root.resolve(strict=True)
        if _is_reparse_point(source_root):
            raise SnapshotLinkError("source root is a reparse point")
        if self._platform_repository_root and _is_relative_to(
            source_root, self._platform_repository_root
        ):
            raise WorkspacePathError("source root must not be inside the platform repository")
        if not snapshot_id or Path(snapshot_id).name != snapshot_id or snapshot_id in {".", ".."}:
            raise ValueError("snapshot ID is not a safe path component")

        snapshot_path = (self._snapshot_root / snapshot_id).resolve(strict=False)
        if not _is_relative_to(snapshot_path, self._snapshot_root):
            raise WorkspacePathError("snapshot destination escapes the registered snapshot root")
        ensure_non_overlapping_paths(source_root, snapshot_path)
        if snapshot_path.exists():
            raise FileExistsError(f"snapshot already exists: {snapshot_path}")

        manifest = self._manifest_builder.build(source_root)
        fingerprint = _snapshot_fingerprint(manifest)
        temporary_path = snapshot_path.with_name(
            f".{snapshot_id}.copying-{os.getpid()}-{time.time_ns()}"
        )
        try:
            temporary_path.mkdir(parents=True, exist_ok=False)
            _copy_filtered_tree(
                source_root,
                temporary_path,
                self._manifest_builder.policy,
                self._manifest_builder.retries,
            )
            after_copy = self._manifest_builder.build(source_root, generated_at=manifest.generated_at)
            if _manifest_content(after_copy) != _manifest_content(manifest):
                raise SnapshotIntegrityError("source changed while snapshot was being copied")
            self._manifest_builder.write_manifest(manifest, temporary_path / "source-manifest.json")
            (temporary_path / "snapshot-fingerprint.json").write_text(
                json.dumps(
                    {"fingerprint": fingerprint, "manifest_checksum": manifest.checksum},
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            _make_read_only(temporary_path)
            temporary_path.replace(snapshot_path)
        except Exception:
            if temporary_path.exists() and _is_relative_to(
                temporary_path.resolve(strict=False), self._snapshot_root
            ):
                shutil.rmtree(temporary_path, ignore_errors=True)
            raise
        return SnapshotRecord(
            snapshot_id=snapshot_id,
            snapshot_root=snapshot_path,
            manifest=manifest,
            fingerprint=fingerprint,
            git_metadata=_read_git_metadata(source_root),
        )

    def inspect_snapshot(self, snapshot_id: str) -> SnapshotRecord:
        if not snapshot_id or Path(snapshot_id).name != snapshot_id:
            raise ValueError("snapshot ID is not a safe path component")
        snapshot_path = (self._snapshot_root / snapshot_id).resolve(strict=False)
        if not _is_relative_to(snapshot_path, self._snapshot_root):
            raise WorkspacePathError("snapshot path escapes the registered snapshot root")
        manifest_path = snapshot_path / "source-manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(str(manifest_path))

        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = SourceManifest(
            manifest_id=payload["manifest_id"],
            source_root=payload["source_root"],
            generated_at=datetime.fromisoformat(payload["generated_at"]),
            entries=tuple(SourceManifestEntry(**entry) for entry in payload["entries"]),
            exclusions=tuple(
                SourceExclusion(**item) for item in payload.get("exclusions", [])
            ),
            policy_version=payload.get("policy_version", "source-snapshot-policy-v1"),
        )
        if payload.get("checksum") != manifest.checksum:
            raise SnapshotIntegrityError("snapshot manifest checksum does not match its contents")
        fingerprint_path = snapshot_path / "snapshot-fingerprint.json"
        if not fingerprint_path.is_file():
            raise FileNotFoundError(str(fingerprint_path))
        fingerprint_payload = json.loads(fingerprint_path.read_text(encoding="utf-8"))
        if fingerprint_payload.get("manifest_checksum") != manifest.checksum:
            raise SnapshotIntegrityError("snapshot fingerprint does not match its manifest")
        for entry in manifest.entries:
            file_path = snapshot_path / Path(entry.relative_path)
            if not file_path.is_file() or _checksum_file(file_path) != entry.checksum:
                raise SnapshotIntegrityError(
                    f"snapshot file checksum does not match its manifest: {entry.relative_path}"
                )
        return SnapshotRecord(
            snapshot_id=snapshot_id,
            snapshot_root=snapshot_path,
            manifest=manifest,
            fingerprint=_snapshot_fingerprint(manifest),
            git_metadata=_read_git_metadata(snapshot_path),
        )


def _walk_source(
    source_root: Path,
    policy: SnapshotPolicy,
    exclusions: list[SourceExclusion],
) -> Iterable[Path]:
    for root, directories, files in os.walk(source_root, topdown=True, followlinks=False):
        root_path = Path(root)
        kept: list[str] = []
        for name in sorted(directories, key=lambda value: (value.casefold(), value)):
            candidate = root_path / name
            relative = candidate.relative_to(source_root)
            if _is_reparse_point(candidate):
                raise SnapshotLinkError(f"source link is not allowed: {relative.as_posix()}")
            if policy.excludes(relative):
                exclusions.append(
                    SourceExclusion(relative.as_posix(), "excluded-directory", policy.version)
                )
            else:
                kept.append(name)
        directories[:] = kept
        for name in sorted(files, key=lambda value: (value.casefold(), value)):
            yield root_path / name


def _copy_filtered_tree(
    source_root: Path,
    destination: Path,
    policy: SnapshotPolicy,
    retries: int,
) -> None:
    for source_path in _walk_source(source_root, policy, []):
        target = destination / source_path.relative_to(source_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(retries + 1):
            try:
                shutil.copy2(source_path, target, follow_symlinks=False)
                break
            except OSError:
                if attempt >= retries:
                    raise
                time.sleep(0.01 * (attempt + 1))


def _file_evidence(path: Path, retries: int) -> tuple[int, str]:
    for attempt in range(retries + 1):
        try:
            before = path.stat()
            checksum = _checksum_file(path)
            after = path.stat()
        except OSError:
            if attempt >= retries:
                raise
            time.sleep(0.01 * (attempt + 1))
            continue
        if before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns:
            return after.st_size, checksum
        if attempt < retries:
            time.sleep(0.01 * (attempt + 1))
    raise SnapshotIntegrityError(f"source file changed while being read: {path}")


def _manifest_content(manifest: SourceManifest) -> tuple[object, ...]:
    return (
        manifest.policy_version,
        tuple(asdict(entry).items() for entry in manifest.entries),
        tuple(asdict(item).items() for item in manifest.exclusions),
    )


def _snapshot_fingerprint(manifest: SourceManifest) -> str:
    value = manifest.checksum.encode("utf-8")
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _read_git_metadata(source_root: Path) -> GitMetadata:
    head = source_root / ".git" / "HEAD"
    if not head.is_file():
        return GitMetadata(False)
    value = head.read_text(encoding="utf-8").strip()
    branch = value.removeprefix("ref: refs/heads/") if value.startswith("ref: ") else None
    return GitMetadata(True, value, branch)


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = path.stat(follow_symlinks=False).st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))

def _make_read_only(root: Path) -> None:
    for path in root.rglob("*"):
        path.chmod(0o444 if path.is_file() else 0o555)
    root.chmod(0o555)
