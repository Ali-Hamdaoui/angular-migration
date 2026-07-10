"""Local filesystem artifact store used by Sprint 0 backend workflows."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from app.domain.contracts import ArtifactRefDto, ArtifactType

ARTIFACT_LAYOUT = (
    "00_job_setup",
    "01_baseline",
    "02_analysis",
    "03_planning",
    "04_workflow_state",
    "05_sandbox_transform",
    "06_validation",
    "07_repair",
    "08_final",
)

_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ArtifactStoreError(ValueError):
    """Raised when a requested artifact path is invalid or cannot be resolved."""


class ArtifactNotFoundError(FileNotFoundError):
    """Raised when an artifact is not present in the local filesystem store."""


@dataclass(frozen=True)
class StoredArtifact:
    """Backend-owned artifact payload and its persisted metadata."""

    ref: ArtifactRefDto
    content: str
    created_by: str | None = None


class LocalFilesystemArtifactStore:
    """Write, list, and read artifacts within the configured artifact root."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root

    @property
    def artifact_root(self) -> Path:
        return self._artifact_root

    def ensure_run_layout(self, run_id: str) -> Path:
        """Create the canonical run directory tree if it does not exist yet."""
        run_root = self._resolve_run_root(run_id)
        run_root.mkdir(parents=True, exist_ok=True)
        for folder in ARTIFACT_LAYOUT:
            (run_root / folder).mkdir(parents=True, exist_ok=True)
        return run_root

    def write_text_artifact(
        self,
        run_id: str,
        relative_path: str,
        content: str,
        artifact_type: ArtifactType,
        *,
        stage_id: str | None = None,
        created_by: str = "backend",
        created_at: datetime | None = None,
    ) -> StoredArtifact:
        """Persist a text artifact, its checksum, and a metadata sidecar."""
        normalized = self._normalize_relative_path(relative_path)
        artifact_path = self._resolve_artifact_path(run_id, normalized)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(content, encoding="utf-8")

        created_at = created_at or datetime.now(UTC)
        checksum = self._checksum(content.encode("utf-8"))
        ref = ArtifactRefDto(
            artifact_id=self._artifact_id(run_id, normalized),
            run_id=run_id,
            stage_id=stage_id,
            artifact_type=artifact_type,
            relative_path=normalized,
            created_at=created_at,
            checksum=checksum,
        )
        self._write_metadata_sidecar(artifact_path, ref, created_by)
        return StoredArtifact(ref=ref, content=content, created_by=created_by)

    def list_artifacts(self, run_id: str) -> list[ArtifactRefDto]:
        """List all stored artifacts for a run, ordered by relative path."""
        run_root = self._resolve_run_root(run_id)
        if not run_root.exists():
            return []

        artifacts: list[ArtifactRefDto] = []
        for file_path in sorted(p for p in run_root.rglob("*") if p.is_file() and not self._is_metadata_file(p)):
            if self._metadata_sidecar(file_path).exists():
                metadata = self._read_metadata(file_path)
                artifacts.append(metadata.ref)
                continue
            content = file_path.read_bytes()
            relative_path = file_path.relative_to(run_root).as_posix()
            artifacts.append(
                ArtifactRefDto(
                    artifact_id=self._artifact_id(run_id, relative_path),
                    run_id=run_id,
                    stage_id=self._stage_id_from_relative_path(relative_path),
                    artifact_type=self._artifact_type_from_path(file_path),
                    relative_path=relative_path,
                    created_at=datetime.fromtimestamp(file_path.stat().st_mtime, UTC),
                    checksum=self._checksum(content),
                )
            )
        return artifacts

    def read_artifact(self, run_id: str, relative_path: str) -> StoredArtifact:
        """Read a stored artifact and its metadata from the local filesystem."""
        normalized = self._normalize_relative_path(relative_path)
        artifact_path = self._resolve_artifact_path(run_id, normalized)
        if not artifact_path.is_file():
            raise ArtifactNotFoundError(str(artifact_path))

        if self._metadata_sidecar(artifact_path).exists():
            metadata = self._read_metadata(artifact_path)
            content = artifact_path.read_text(encoding="utf-8")
            return StoredArtifact(ref=metadata.ref, content=content, created_by=metadata.created_by)

        content = artifact_path.read_text(encoding="utf-8")
        created_at = datetime.fromtimestamp(artifact_path.stat().st_mtime, UTC)
        ref = ArtifactRefDto(
            artifact_id=self._artifact_id(run_id, normalized),
            run_id=run_id,
            stage_id=self._stage_id_from_relative_path(normalized),
            artifact_type=self._artifact_type_from_path(artifact_path),
            relative_path=normalized,
            created_at=created_at,
            checksum=self._checksum(content.encode("utf-8")),
        )
        return StoredArtifact(ref=ref, content=content, created_by=None)

    def _resolve_run_root(self, run_id: str) -> Path:
        self._validate_run_id(run_id)
        return (self._artifact_root / run_id).resolve()

    def _resolve_artifact_path(self, run_id: str, relative_path: str) -> Path:
        run_root = self.ensure_run_layout(run_id)
        artifact_path = (run_root / Path(relative_path)).resolve()
        try:
            artifact_path.relative_to(run_root)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise ArtifactStoreError("Artifact path escapes the run root") from exc
        return artifact_path

    def _normalize_relative_path(self, relative_path: str) -> str:
        if not relative_path or "\\" in relative_path:
            raise ArtifactStoreError("Artifact paths must use forward slashes and be non-empty")
        path = PurePosixPath(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ArtifactStoreError("Artifact paths must stay within the run folder")
        normalized = path.as_posix()
        if normalized.startswith("./") or normalized == ".":
            raise ArtifactStoreError("Artifact paths must stay within the run folder")
        return normalized

    def _validate_run_id(self, run_id: str) -> None:
        if not _RUN_ID_PATTERN.fullmatch(run_id):
            raise ArtifactStoreError("Run IDs must be simple filesystem-safe names")

    def _metadata_sidecar(self, artifact_path: Path) -> Path:
        return artifact_path.with_name(f"{artifact_path.name}.meta.json")

    def _write_metadata_sidecar(self, artifact_path: Path, ref: ArtifactRefDto, created_by: str) -> None:
        metadata = {
            "artifact_id": ref.artifact_id,
            "run_id": ref.run_id,
            "stage_id": ref.stage_id,
            "artifact_type": ref.artifact_type.value,
            "relative_path": ref.relative_path,
            "created_at": ref.created_at.isoformat(),
            "created_by": created_by,
            "checksum": ref.checksum,
        }
        self._metadata_sidecar(artifact_path).write_text(
            json.dumps(metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _read_metadata(self, artifact_path: Path) -> StoredArtifact:
        raw_metadata = json.loads(self._metadata_sidecar(artifact_path).read_text(encoding="utf-8"))
        ref = ArtifactRefDto(
            artifact_id=raw_metadata["artifact_id"],
            run_id=raw_metadata["run_id"],
            stage_id=raw_metadata["stage_id"],
            artifact_type=ArtifactType(raw_metadata["artifact_type"]),
            relative_path=raw_metadata["relative_path"],
            created_at=datetime.fromisoformat(raw_metadata["created_at"]),
            checksum=raw_metadata["checksum"],
        )
        return StoredArtifact(
            ref=ref,
            content=artifact_path.read_text(encoding="utf-8"),
            created_by=raw_metadata.get("created_by"),
        )

    def _artifact_id(self, run_id: str, relative_path: str) -> str:
        digest = hashlib.sha256(f"{run_id}:{relative_path}".encode("utf-8")).hexdigest()[:16]
        return f"artifact-{digest}"

    def _checksum(self, payload: bytes) -> str:
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"

    def _stage_id_from_relative_path(self, relative_path: str) -> str | None:
        parts = PurePosixPath(relative_path).parts
        return parts[0] if parts and parts[0] in ARTIFACT_LAYOUT else None

    def _artifact_type_from_path(self, artifact_path: Path) -> ArtifactType:
        suffix = artifact_path.suffix.lower()
        if suffix == ".json":
            return ArtifactType.JSON
        if suffix in {".yaml", ".yml"}:
            return ArtifactType.YAML
        if suffix in {".md", ".markdown"}:
            return ArtifactType.MARKDOWN
        if suffix in {".log", ".txt"}:
            return ArtifactType.TEXT_LOG
        if suffix == ".patch":
            return ArtifactType.PATCH
        if suffix == ".diff":
            return ArtifactType.DIFF
        return ArtifactType.TEXT_LOG

    def _is_metadata_file(self, artifact_path: Path) -> bool:
        return artifact_path.name.endswith(".meta.json")
