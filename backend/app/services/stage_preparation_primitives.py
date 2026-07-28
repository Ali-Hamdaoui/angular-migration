"""Safe, deterministic filesystem primitives for stage preparation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
from uuid import uuid4


@dataclass(frozen=True)
class SandboxCopyReport:
    source: str
    target: str
    copied_files: int
    excluded_paths: tuple[str, ...]
    fingerprint: str


class StageSandboxCopier:
    excluded_names = frozenset({"node_modules", ".angular", ".cache", "dist", "build", "logs", "reports", "tmp", ".pytest_cache"})

    def copy(self, source: Path, target: Path, *, registered_root: Path | None = None) -> SandboxCopyReport:
        source = Path(source).resolve(strict=True)
        target = Path(target).resolve(strict=False)
        root = Path(registered_root or source.parent).resolve(strict=True)
        try:
            target.relative_to(root)
        except ValueError as error:
            raise ValueError("stage sandbox containment check failed") from error
        if target == source or target.is_relative_to(source) or source.is_relative_to(target):
            raise ValueError("stage sandbox target must be distinct from and outside the source workspace")
        if target.exists():
            raise ValueError("stage sandbox target already exists")
        for item in source.rglob("*"):
            if item.is_symlink():
                raise ValueError("unsupported symlink in source workspace")
        excluded: list[str] = []
        copied = 0
        target.mkdir(parents=True)
        try:
            for item in source.rglob("*"):
                relative = item.relative_to(source)
                if any(part in self.excluded_names for part in relative.parts):
                    excluded.append(relative.as_posix())
                    continue
                destination = target / relative
                if item.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                elif item.is_file():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, destination)
                    copied += 1
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return SandboxCopyReport(str(source), str(target), copied, tuple(sorted(set(excluded))), self.fingerprint(target))

    def copy_atomically(self, source: Path, target: Path, *, registered_root: Path) -> SandboxCopyReport:
        """Copy through a contained temporary sibling and atomically finalize it.

        The final destination is never visible until copying and fingerprinting
        have completed.  Any failed copy or rename removes its temporary
        residue before the caller can persist an authoritative success state.
        """
        root = Path(registered_root).resolve(strict=True)
        final_target = Path(target).resolve(strict=False)
        try:
            final_target.relative_to(root)
        except ValueError as error:
            raise ValueError("stage sandbox containment check failed") from error
        if final_target.exists():
            raise ValueError("stage sandbox target already exists")
        temporary_target = root / f".{final_target.name}.preparing-{uuid4().hex}"
        try:
            report = self.copy(source, temporary_target, registered_root=root)
            temporary_target.replace(final_target)
        except Exception:
            shutil.rmtree(temporary_target, ignore_errors=True)
            raise
        return SandboxCopyReport(
            source=report.source,
            target=str(final_target),
            copied_files=report.copied_files,
            excluded_paths=report.excluded_paths,
            fingerprint=report.fingerprint,
        )

    @staticmethod
    def fingerprint(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix().encode()
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            content = path.read_bytes()
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
        return "sha256:" + digest.hexdigest()
