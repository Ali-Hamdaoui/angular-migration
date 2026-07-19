"""Deterministic rules for S3-F14 stage copy-forward operations.

This module defines:
- StageCopyForwardService for copying artifacts between stages
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StageCopyForwardError(ValueError):
    """Raised when copy-forward inputs or preconditions are invalid."""


class CopyForwardStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class CopyForwardItem:
    """A single item to copy forward to the next stage."""
    source_path: str
    target_path: str
    checksum: str | None = None
    size_bytes: int = 0
    copied: bool = False
    error: str | None = None


@dataclass(frozen=True)
class CopyForwardManifest:
    """Complete manifest of a copy-forward operation."""
    manifest_id: str
    run_id: str
    source_stage_id: str
    target_stage_id: str
    items: tuple[CopyForwardItem, ...] = ()
    status: CopyForwardStatus = CopyForwardStatus.PENDING
    total_bytes: int = 0
    total_items: int = 0
    copied_items: int = 0
    failed_items: int = 0
    checksum: str | None = None
    artifact_ids: tuple[str, ...] = ()


class StageCopyForwardService:
    """Orchestrates copy-forward operations between stages.

    This service determines what needs to be copied and produces manifests.
    Actual file I/O is delegated to the application service layer.
    """

    def __init__(self):
        self._default_copy_paths: tuple[str, ...] = (
            "package.json",
            "package-lock.json",
            "angular.json",
            "tsconfig.json",
            "tsconfig.app.json",
            ".browserslistrc",
            "proxy.conf.json",
        )

    def resolve_copy_manifest(
        self,
        manifest_id: str,
        run_id: str,
        source_stage_id: str,
        target_stage_id: str,
        source_sandbox: str,
        target_sandbox: str,
        extra_paths: tuple[str, ...] = (),
    ) -> CopyForwardManifest:
        """Resolve the list of files to copy forward between stages."""
        import hashlib
        import os

        items: list[CopyForwardItem] = []
        paths = self._default_copy_paths + extra_paths

        for path in paths:
            source_full = os.path.join(source_sandbox, path)
            if os.path.isfile(source_full):
                try:
                    content = open(source_full, "rb").read()
                    checksum = hashlib.sha256(content).hexdigest()
                    size = len(content)
                    items.append(CopyForwardItem(
                        source_path=path,
                        target_path=path,
                        checksum=checksum,
                        size_bytes=size,
                    ))
                except OSError as e:
                    items.append(CopyForwardItem(
                        source_path=path,
                        target_path=path,
                        error=str(e),
                    ))

        total_bytes = sum(i.size_bytes for i in items if i.error is None)
        return CopyForwardManifest(
            manifest_id=manifest_id,
            run_id=run_id,
            source_stage_id=source_stage_id,
            target_stage_id=target_stage_id,
            items=tuple(items),
            status=CopyForwardStatus.PENDING,
            total_bytes=total_bytes,
            total_items=len(items),
        )

    def aggregate_copy_summary(self, manifest: CopyForwardManifest) -> dict[str, Any]:
        """Produce a summary dict from a completed or failed manifest."""
        return {
            "manifest_id": manifest.manifest_id,
            "source_stage_id": manifest.source_stage_id,
            "target_stage_id": manifest.target_stage_id,
            "status": manifest.status.value,
            "total_items": manifest.total_items,
            "copied_items": manifest.copied_items,
            "failed_items": manifest.failed_items,
            "total_bytes": manifest.total_bytes,
            "checksum": manifest.checksum,
        }
