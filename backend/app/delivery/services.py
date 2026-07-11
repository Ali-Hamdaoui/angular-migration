"""Atomic delivery publication services for Sprint 0."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from app.snapshots.services import SourceIntegrityVerifier, SourceManifest, ensure_non_overlapping_paths


class DeliveryConflictPolicy(str, Enum):
    FAIL = "fail"
    REPLACE = "replace"


class DeliveryError(RuntimeError):
    """Raised when delivery cannot safely publish output."""


@dataclass(frozen=True)
class DeliveryManifest:
    run_id: str
    status: str
    delivery_path: str | None
    manifest_checksum: str | None
    published_at: datetime | None


class DeliveryService:
    """Publish completed workspace output to a final migrated-app directory."""

    _BLOCKED_RUN_STATUSES = {"FAILED", "CANCELLED", "CANCELLING", "DIAGNOSTIC_HOLD"}

    def __init__(self, delivery_root: Path, integrity_verifier: SourceIntegrityVerifier | None = None) -> None:
        self._delivery_root = delivery_root
        self._integrity_verifier = integrity_verifier or SourceIntegrityVerifier()

    @property
    def delivery_root(self) -> Path:
        return self._delivery_root

    def publish_mock_delivery(
        self,
        *,
        run_id: str,
        source_root: Path,
        source_manifest: SourceManifest,
        workspace_repository: Path,
        run_status: str,
        conflict_policy: DeliveryConflictPolicy = DeliveryConflictPolicy.FAIL,
    ) -> DeliveryManifest:
        final_path = (self._delivery_root / "migrated-app").resolve()
        temp_path = (self._delivery_root / f".migrated-app.{run_id}.tmp").resolve()
        source_root = source_root.resolve()
        workspace_repository = workspace_repository.resolve()
        ensure_non_overlapping_paths(source_root, workspace_repository, final_path)

        if run_status in self._BLOCKED_RUN_STATUSES:
            return DeliveryManifest(run_id, "blocked", None, None, None)
        if not self._integrity_verifier.verify(source_root, source_manifest):
            raise DeliveryError("source integrity verification failed before delivery")
        if not workspace_repository.is_dir():
            raise FileNotFoundError(f"workspace repository does not exist: {workspace_repository}")
        if final_path.exists() and conflict_policy is DeliveryConflictPolicy.FAIL:
            raise DeliveryError("migrated-app already exists; explicit replacement policy is required")

        self._delivery_root.mkdir(parents=True, exist_ok=True)
        if temp_path.exists():
            shutil.rmtree(temp_path)
        shutil.copytree(workspace_repository, temp_path)
        if final_path.exists():
            shutil.rmtree(final_path)
        os.replace(temp_path, final_path)

        published_at = datetime.now(UTC)
        checksum = _directory_checksum(final_path)
        manifest = DeliveryManifest(
            run_id=run_id,
            status="published",
            delivery_path=str(final_path),
            manifest_checksum=checksum,
            published_at=published_at,
        )
        (self._delivery_root / "delivery-manifest.json").write_text(
            json.dumps(_manifest_payload(manifest), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return manifest


def _directory_checksum(root: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(file_path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(file_path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _manifest_payload(manifest: DeliveryManifest) -> dict[str, str | None]:
    payload = asdict(manifest)
    payload["published_at"] = manifest.published_at.isoformat() if manifest.published_at else None
    return payload
