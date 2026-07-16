"""Creation of the registered, writable baseline sandbox."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

from app.workspaces.services import BaselineBoundaryError


class BaselineCopyCancelled(RuntimeError):
    """Raised when a baseline copy is cancelled before atomic publication."""


@dataclass(frozen=True)
class BaselineSandboxRecord:
    run_id: str
    sandbox_path: Path
    input_fingerprint: str
    fingerprint: str
    excluded_paths: tuple[str, ...] = ()


class BaselineSandboxService:
    """Copy an approved immutable snapshot into a registered baseline alias."""

    def create(
        self,
        *,
        run_id: str,
        snapshot_root: Path,
        baseline_path: Path,
        approved_snapshot_fingerprint: str,
        registered_run_root: Path | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> BaselineSandboxRecord:
        snapshot_root = snapshot_root.resolve(strict=True)
        baseline_path = baseline_path.resolve(strict=False)
        if registered_run_root is not None:
            run_root = registered_run_root.resolve(strict=True)
            for alias_name, alias_path in (("SOURCE_SNAPSHOT", snapshot_root), ("BASELINE_SANDBOX", baseline_path)):
                try:
                    alias_path.relative_to(run_root)
                except ValueError as error:
                    raise BaselineBoundaryError(f"{alias_name} must remain inside the registered run root") from error
        if not approved_snapshot_fingerprint:
            raise BaselineBoundaryError("An approved snapshot fingerprint is required")
        if baseline_path == snapshot_root or baseline_path.is_relative_to(snapshot_root) or snapshot_root.is_relative_to(baseline_path):
            raise BaselineBoundaryError("Baseline sandbox and source snapshot must not overlap")
        if baseline_path.exists():
            raise FileExistsError(f"baseline sandbox already exists: {baseline_path}")

        fingerprint_path = snapshot_root / "snapshot-fingerprint.json"
        if not fingerprint_path.is_file():
            raise BaselineBoundaryError("Snapshot fingerprint evidence is required")
        try:
            evidence = json.loads(fingerprint_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BaselineBoundaryError("Snapshot fingerprint evidence is invalid") from error
        input_fingerprint = evidence.get("fingerprint")
        if input_fingerprint != approved_snapshot_fingerprint:
            raise BaselineBoundaryError("Snapshot fingerprint does not match the approved G02 boundary")

        excluded: list[str] = []
        temporary = baseline_path.with_name(f".{baseline_path.name}.copying-{os.getpid()}")
        try:
            temporary.mkdir(parents=True, exist_ok=False)
            for source in snapshot_root.rglob("*"):
                if cancel_check is not None and cancel_check():
                    raise BaselineCopyCancelled("baseline sandbox copy cancelled before publication")
                relative = source.relative_to(snapshot_root)
                if relative.parts and relative.parts[0] in {"node_modules", ".angular", "dist", "coverage"}:
                    excluded.append(relative.as_posix())
                    continue
                if source.is_symlink():
                    raise BaselineBoundaryError(f"Baseline snapshot contains an unsafe link: {relative.as_posix()}")
                target = temporary / relative
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                elif source.is_file() and relative.name not in {"source-manifest.json", "snapshot-fingerprint.json"}:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    target.chmod(0o644)
            for directory in sorted((path for path in temporary.rglob("*") if path.is_dir()), key=lambda p: len(p.parts), reverse=True):
                directory.chmod(0o755)
            temporary.replace(baseline_path)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
            raise

        return BaselineSandboxRecord(
            run_id=run_id,
            sandbox_path=baseline_path,
            input_fingerprint=input_fingerprint,
            fingerprint=_tree_fingerprint(baseline_path),
            excluded_paths=tuple(sorted(set(excluded))),
        )

    def reconstruct(self, **kwargs) -> BaselineSandboxRecord:
        """Retry a cancelled or failed copy from the immutable snapshot."""
        baseline_path = Path(kwargs["baseline_path"])
        temporary = baseline_path.with_name(f".{baseline_path.name}.copying-{os.getpid()}")
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        if baseline_path.is_symlink():
            raise BaselineBoundaryError("Baseline sandbox reconstruction cannot replace a symbolic link")
        if baseline_path.is_dir():
            shutil.rmtree(baseline_path)
        elif baseline_path.exists():
            baseline_path.unlink()
        return self.create(**kwargs)


def _tree_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(root).as_posix().casefold(),
    ):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return f"sha256:{digest.hexdigest()}"
