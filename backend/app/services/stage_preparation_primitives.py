"""Safe, deterministic filesystem primitives for stage preparation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil


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
        if not target.is_relative_to(source) and target == source:
            raise ValueError("stage sandbox target must be distinct from source")
        target.mkdir(parents=True, exist_ok=True)
        excluded: list[str] = []
        copied = 0
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
        return SandboxCopyReport(str(source), str(target), copied, tuple(sorted(set(excluded))), self.fingerprint(target))

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
