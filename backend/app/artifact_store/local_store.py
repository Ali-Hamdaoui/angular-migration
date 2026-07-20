"""Local filesystem artifact store used by Sprint 0 backend workflows."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

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
    "global",
    "stages",
    "repair_attempts",
    "final_assurance",
    "delivery",
    "final_report",
)

ARTIFACT_SCHEMA_VERSION = 1
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ARTIFACT_ID_PATTERN = re.compile(r"^artifact-[A-Za-z0-9._-]+$")


class ArtifactStoreError(ValueError):
    """Raised when a requested artifact path is invalid or cannot be resolved."""


class ArtifactNotFoundError(FileNotFoundError):
    """Raised when an artifact is not present in the local filesystem store."""


@dataclass(frozen=True)
class ArtifactEnvelope:
    """Immutable metadata sidecar for one stored artifact version."""

    schema_version: int
    artifact_id: str
    run_id: str
    stage_id: str | None
    attempt_id: str | None
    producer: str
    artifact_type: ArtifactType
    content_type: str
    input_hashes: dict[str, str]
    policy_version: str
    content_hash: str
    relative_path: str
    created_at: datetime


@dataclass(frozen=True)
class StoredArtifact:
    """Backend-owned artifact payload and its persisted metadata."""

    ref: ArtifactRefDto
    content: str
    created_by: str | None = None
    envelope: ArtifactEnvelope | None = None


class LocalFilesystemArtifactStore:
    """Write, list, and read immutable artifacts within the configured artifact root."""

    def __init__(self, artifact_root: Path, *, fixed_run_root: Path | None = None) -> None:
        self._artifact_root = artifact_root
        self._fixed_run_root = fixed_run_root.resolve() if fixed_run_root else None

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
        attempt_id: str | None = None,
        created_by: str = "backend",
        created_at: datetime | None = None,
        content_type: str | None = None,
        input_hashes: dict[str, str] | None = None,
        policy_version: str = "sprint0",
    ) -> StoredArtifact:
        """Persist a text artifact version, checksum, and metadata sidecar atomically."""
        normalized = self._normalize_relative_path(relative_path)
        artifact_path = self._resolve_available_artifact_path(run_id, normalized)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)

        payload = content.encode("utf-8")
        content_hash = self._checksum(payload)
        created_at = created_at or datetime.now(UTC)
        stored_relative_path = artifact_path.relative_to(self._resolve_run_root(run_id)).as_posix()
        artifact_id = self._new_artifact_id()
        ref = ArtifactRefDto(
            artifact_id=artifact_id,
            run_id=run_id,
            stage_id=stage_id or self._stage_id_from_relative_path(stored_relative_path),
            artifact_type=artifact_type,
            relative_path=stored_relative_path,
            created_at=created_at,
            checksum=content_hash,
        )
        envelope = ArtifactEnvelope(
            schema_version=ARTIFACT_SCHEMA_VERSION,
            artifact_id=artifact_id,
            run_id=run_id,
            stage_id=ref.stage_id,
            attempt_id=attempt_id,
            producer=created_by,
            artifact_type=artifact_type,
            content_type=content_type or self._content_type_for_artifact(artifact_type),
            input_hashes=input_hashes or {},
            policy_version=policy_version,
            content_hash=content_hash,
            relative_path=stored_relative_path,
            created_at=created_at,
        )
        self._atomic_write_bytes(artifact_path, payload)
        self._write_metadata_sidecar(artifact_path, envelope)
        return StoredArtifact(ref=ref, content=content, created_by=created_by, envelope=envelope)

    def list_artifacts(self, run_id: str) -> list[ArtifactRefDto]:
        """List all stored artifacts for a run, ordered by relative path."""
        run_root = self._resolve_run_root(run_id)
        if not run_root.exists():
            return []

        artifacts: list[ArtifactRefDto] = []
        for sidecar_path in sorted(run_root.rglob("*.meta.json")):
            artifact_path = self._artifact_from_sidecar(sidecar_path)
            if artifact_path.is_file():
                metadata = self._read_metadata(artifact_path)
                artifacts.append(metadata.ref)
        return artifacts

    def read_artifact(self, run_id: str, relative_path: str) -> StoredArtifact:
        """Read a stored artifact by run-scoped relative path."""
        normalized = self._normalize_relative_path(relative_path)
        artifact_path = self._resolve_existing_artifact_path(run_id, normalized)
        return self._read_metadata(artifact_path)

    def read_artifact_by_id(self, artifact_id: str) -> StoredArtifact:
        """Read a stored artifact by immutable artifact ID."""
        self._validate_artifact_id(artifact_id)
        if not self._artifact_root.exists():
            raise ArtifactNotFoundError(artifact_id)
        for sidecar_path in self._artifact_root.rglob("*.meta.json"):
            artifact_path = self._artifact_from_sidecar(sidecar_path)
            if not artifact_path.is_file():
                continue
            metadata = self._read_metadata(artifact_path)
            if metadata.ref.artifact_id == artifact_id:
                return metadata
        raise ArtifactNotFoundError(artifact_id)

    def _resolve_run_root(self, run_id: str) -> Path:
        self._validate_run_id(run_id)
        return self._fixed_run_root if self._fixed_run_root is not None else (self._artifact_root / run_id).resolve()

    def _resolve_available_artifact_path(self, run_id: str, relative_path: str) -> Path:
        run_root = self.ensure_run_layout(run_id)
        candidate = self._contained_path(run_root, relative_path)
        self._reject_symlink_escape(candidate, run_root)
        if not candidate.exists() and not self._metadata_sidecar(candidate).exists():
            return candidate
        stem = candidate.stem
        suffix = candidate.suffix
        parent = candidate.parent
        version = 2
        while True:
            next_candidate = parent / f"{stem}__v{version}{suffix}"
            self._reject_symlink_escape(next_candidate, run_root)
            if not next_candidate.exists() and not self._metadata_sidecar(next_candidate).exists():
                return next_candidate
            version += 1

    def _resolve_existing_artifact_path(self, run_id: str, relative_path: str) -> Path:
        run_root = self._resolve_run_root(run_id)
        artifact_path = self._contained_path(run_root, relative_path)
        self._reject_symlink_escape(artifact_path, run_root)
        if not artifact_path.is_file():
            raise ArtifactNotFoundError(str(artifact_path))
        return artifact_path

    def _contained_path(self, run_root: Path, relative_path: str) -> Path:
        artifact_path = (run_root / Path(relative_path)).resolve()
        try:
            artifact_path.relative_to(run_root)
        except ValueError as exc:
            raise ArtifactStoreError("Artifact path escapes the run root") from exc
        return artifact_path

    def _reject_symlink_escape(self, artifact_path: Path, run_root: Path) -> None:
        current = artifact_path.parent
        while current != run_root and current != current.parent:
            if current.exists() and current.is_symlink():
                resolved = current.resolve()
                try:
                    resolved.relative_to(run_root)
                except ValueError as exc:
                    raise ArtifactStoreError("Artifact path traverses a symlink outside the run root") from exc
            current = current.parent

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

    def _validate_artifact_id(self, artifact_id: str) -> None:
        if not _ARTIFACT_ID_PATTERN.fullmatch(artifact_id):
            raise ArtifactStoreError("Artifact IDs must be simple filesystem-safe names")

    def _metadata_sidecar(self, artifact_path: Path) -> Path:
        return artifact_path.with_name(f"{artifact_path.name}.meta.json")

    def _artifact_from_sidecar(self, sidecar_path: Path) -> Path:
        if not sidecar_path.name.endswith(".meta.json"):
            raise ArtifactStoreError("Invalid artifact metadata sidecar")
        return sidecar_path.with_name(sidecar_path.name.removesuffix(".meta.json"))

    def _write_metadata_sidecar(self, artifact_path: Path, envelope: ArtifactEnvelope) -> None:
        metadata = {
            "schema_version": envelope.schema_version,
            "artifact_id": envelope.artifact_id,
            "run_id": envelope.run_id,
            "stage_id": envelope.stage_id,
            "attempt_id": envelope.attempt_id,
            "producer": envelope.producer,
            "artifact_type": envelope.artifact_type.value,
            "content_type": envelope.content_type,
            "input_hashes": envelope.input_hashes,
            "policy_version": envelope.policy_version,
            "content_hash": envelope.content_hash,
            "relative_path": envelope.relative_path,
            "created_at": envelope.created_at.isoformat(),
            "created_by": envelope.producer,
            "checksum": envelope.content_hash,
        }
        payload = json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8")
        self._atomic_write_bytes(self._metadata_sidecar(artifact_path), payload)

    def _read_metadata(self, artifact_path: Path) -> StoredArtifact:
        raw_metadata = json.loads(self._metadata_sidecar(artifact_path).read_text(encoding="utf-8"))
        actual_checksum = self._checksum(artifact_path.read_bytes())
        expected_checksum = raw_metadata.get("content_hash") or raw_metadata.get("checksum")
        if expected_checksum != actual_checksum:
            raise ArtifactStoreError("Artifact checksum mismatch")
        artifact_type = ArtifactType(raw_metadata["artifact_type"])
        created_at = datetime.fromisoformat(raw_metadata["created_at"])
        envelope = ArtifactEnvelope(
            schema_version=raw_metadata.get("schema_version", ARTIFACT_SCHEMA_VERSION),
            artifact_id=raw_metadata["artifact_id"],
            run_id=raw_metadata["run_id"],
            stage_id=raw_metadata.get("stage_id"),
            attempt_id=raw_metadata.get("attempt_id"),
            producer=raw_metadata.get("producer") or raw_metadata.get("created_by") or "backend",
            artifact_type=artifact_type,
            content_type=raw_metadata.get("content_type") or self._content_type_for_artifact(artifact_type),
            input_hashes=raw_metadata.get("input_hashes") or {},
            policy_version=raw_metadata.get("policy_version") or "sprint0",
            content_hash=raw_metadata.get("content_hash") or raw_metadata["checksum"],
            relative_path=raw_metadata["relative_path"],
            created_at=created_at,
        )
        ref = ArtifactRefDto(
            artifact_id=envelope.artifact_id,
            run_id=envelope.run_id,
            stage_id=envelope.stage_id,
            artifact_type=envelope.artifact_type,
            relative_path=envelope.relative_path,
            created_at=envelope.created_at,
            checksum=envelope.content_hash,
        )
        return StoredArtifact(
            ref=ref,
            content=artifact_path.read_text(encoding="utf-8"),
            created_by=envelope.producer,
            envelope=envelope,
        )

    def _atomic_write_bytes(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        temp_path.write_bytes(payload)
        os.replace(temp_path, path)

    def _new_artifact_id(self) -> str:
        return f"artifact-{uuid4().hex}"

    def _checksum(self, payload: bytes) -> str:
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"

    def _stage_id_from_relative_path(self, relative_path: str) -> str | None:
        parts = PurePosixPath(relative_path).parts
        if len(parts) >= 2 and parts[0] == "stages":
            return parts[1]
        return parts[0] if parts and parts[0] in ARTIFACT_LAYOUT else None

    def _content_type_for_artifact(self, artifact_type: ArtifactType) -> str:
        return {
            ArtifactType.JSON: "application/json",
            ArtifactType.YAML: "application/yaml",
            ArtifactType.MARKDOWN: "text/markdown",
            ArtifactType.TEXT_LOG: "text/plain",
            ArtifactType.COMMAND_LOG: "application/json",
            ArtifactType.PATCH: "text/x-patch",
            ArtifactType.DIFF: "text/x-diff",
            ArtifactType.REPORT: "text/markdown",
        }[artifact_type]
