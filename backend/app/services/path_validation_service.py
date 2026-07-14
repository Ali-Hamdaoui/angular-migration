"""Deterministic, fail-closed source and target path validation."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Callable
from uuid import uuid4

from app.core.config import Settings
from app.domain.path_validation import (
    PathRuleResult,
    PathValidationRequest,
    PathValidationResult,
    PathValidationSnapshot,
)


class PathValidationService:
    policy_version = "path-validation-v1"

    def __init__(self, settings: Settings, *, now_provider: Callable[[], datetime] | None = None) -> None:
        self._settings = settings
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def validate(self, request: PathValidationRequest) -> PathValidationResult:
        captured_at = self._now_provider()
        source = self._canonical(request.source_path)
        target = self._canonical(request.target_output_path)
        blockers: list[str] = []
        warnings: list[str] = []
        rules: list[PathRuleResult] = []

        self._rule(
            rules, blockers, "NETWORK_LOCATION_UNSUPPORTED",
            not self._is_network_path(source) and not self._is_network_path(target),
            "Source and target must use local filesystem paths.",
        )
        self._rule(rules, blockers, "SOURCE_NOT_DIRECTORY", source.is_dir(), "Source path must be an existing directory.")
        self._rule(rules, blockers, "SOURCE_NOT_READABLE", self._is_readable(source), "Source path must be readable.")
        self._rule(rules, blockers, "SOURCE_TARGET_EQUAL", source != target, "Source and target must be different paths.")
        self._rule(rules, blockers, "TARGET_NESTED_IN_SOURCE", not self._is_relative_to(target, source), "Target must not be nested inside source.")
        self._rule(rules, blockers, "SOURCE_NESTED_IN_TARGET", not self._is_relative_to(source, target), "Source and target must not overlap.")
        self._rule(
            rules, blockers, "SOURCE_INTERNAL_ROOT",
            not any(self._is_relative_to(source, root.resolve()) for root in (self._settings.workspace_root, self._settings.artifact_root, self._settings.sandbox_root)),
            "Source must not be inside an internal application root.",
        )
        self._rule(
            rules, blockers, "SOURCE_OUTSIDE_ALLOWED_ROOT",
            any(self._is_relative_to(source, root.resolve()) for root in self._settings.allowed_source_roots),
            "Source must be inside an allowed source root.",
        )
        self._rule(
            rules, blockers, "TARGET_OUTSIDE_ALLOWED_ROOT",
            any(self._is_relative_to(target, root.resolve()) for root in self._settings.allowed_target_roots),
            "Target must be inside an allowed target root.",
        )

        target_parent = self._nearest_existing_parent(target)
        target_writable = target_parent is not None and self._is_writable(target_parent)
        self._rule(rules, blockers, "TARGET_NOT_WRITABLE", target_writable, "Target or its nearest existing parent must be writable.")
        if target_parent is not None and shutil.disk_usage(target_parent).free < self._settings.minimum_free_disk_bytes:
            blockers.append("DISK_SPACE_BELOW_THRESHOLD")
            rules.append(PathRuleResult(code="DISK_SPACE_BELOW_THRESHOLD", status="blocked", message="Target volume is below the configured free-space threshold."))
        if len(str(source)) > 220 or len(str(target)) > 220:
            warnings.append("PATH_LENGTH_NEAR_WINDOWS_LIMIT")
            rules.append(PathRuleResult(code="PATH_LENGTH_NEAR_WINDOWS_LIMIT", status="warning", message="Path length is near the Windows compatibility limit."))
        if self._has_reparse_point(source) or self._has_reparse_point(target):
            blockers.append("REPARSE_POINT_UNCERTAIN")
            rules.append(PathRuleResult(code="REPARSE_POINT_UNCERTAIN", status="blocked", message="A symlink or reparse point requires explicit review."))

        fingerprint = self._fingerprint(source)
        status = "blocked" if blockers else ("passed_with_warnings" if warnings else "passed")
        payload = {
            "validation_id": f"path-validation-{uuid4().hex[:12]}",
            "captured_at": captured_at,
            "policy_version": self.policy_version,
            "status": status,
            "source_path": str(source),
            "target_output_path": str(target),
            "source_fingerprint": fingerprint,
            "rules": [rule.model_dump(mode="json") for rule in rules],
            "blockers": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
            "target_reservation_eligible": not blockers and target_writable,
        }
        return PathValidationResult(
            snapshot=PathValidationSnapshot(**payload, checksum=self._checksum(payload))
        )

    @staticmethod
    def _canonical(value: str) -> Path:
        return Path(value.strip()).expanduser().resolve(strict=False)

    @staticmethod
    def _is_network_path(path: Path) -> bool:
        return str(path).startswith("\\\\") or str(path).startswith("//")

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_readable(path: Path) -> bool:
        return path.is_dir() and os.access(path, os.R_OK)

    @staticmethod
    def _is_writable(path: Path) -> bool:
        return path.is_dir() and os.access(path, os.W_OK)

    @staticmethod
    def _nearest_existing_parent(path: Path) -> Path | None:
        current = path if path.is_dir() else path.parent
        while current != current.parent:
            if current.exists():
                return current
            current = current.parent
        return current if current.exists() else None

    @staticmethod
    def _has_reparse_point(path: Path) -> bool:
        current = path
        while current != current.parent:
            if current.is_symlink():
                return True
            current = current.parent
        return False

    @staticmethod
    def _fingerprint(source: Path) -> str | None:
        if not source.is_dir():
            return None
        entries: list[str] = []
        for child in sorted(source.iterdir(), key=lambda item: item.name.lower()):
            try:
                stat = child.stat()
            except OSError:
                return None
            entries.append(f"{child.name}|{stat.st_size}|{stat.st_mtime_ns}|{child.is_dir()}")
        payload = "\n".join(entries).encode("utf-8")
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"

    @staticmethod
    def _checksum(payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _rule(rules: list[PathRuleResult], blockers: list[str], code: str, passed: bool, message: str) -> None:
        if passed:
            rules.append(PathRuleResult(code=code, status="passed", message=message))
        else:
            blockers.append(code)
            rules.append(PathRuleResult(code=code, status="blocked", message=message))