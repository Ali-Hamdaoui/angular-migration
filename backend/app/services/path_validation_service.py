"""Deterministic external source and generated-output validation."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Callable
from uuid import uuid4

from app.core.config import Settings
from app.domain.path_validation import PathRuleResult, PathValidationRequest, PathValidationResult, PathValidationSnapshot


class PathValidationService:
    policy_version = "path-validation-v2-external-output"

    def __init__(self, settings: Settings, *, now_provider: Callable[[], datetime] | None = None) -> None:
        self._settings = settings
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def validate(self, request: PathValidationRequest) -> PathValidationResult:
        captured_at = self._now_provider()
        raw_source = Path(request.source_path.strip())
        raw_parent = Path((request.target_parent_path or request.target_output_path or "").strip())
        source = self._canonical(request.source_path)
        parent = self._canonical(request.target_parent_path or request.target_output_path or "")
        output_name = self._output_name(source.name, request.target_angular_family)
        output = parent / output_name
        blockers: list[str] = []
        warnings: list[str] = []
        rules: list[PathRuleResult] = []
        repo = self._settings.platform_repository_root.resolve()
        target_roots = tuple(root.expanduser().resolve(strict=False) for root in self._settings.allowed_target_roots)
        self._rule(rules, blockers, "SOURCE_PATH_NOT_FOUND", source.exists(), "Source path must exist.")
        self._rule(rules, blockers, "SOURCE_PATH_NOT_DIRECTORY", source.is_dir(), "Source path must be a directory.")
        self._rule(rules, blockers, "SOURCE_PATH_INSIDE_PLATFORM_REPOSITORY", not self._is_relative_to(source, repo), "Source must be external to the platform repository.")
        self._rule(rules, blockers, "TARGET_PARENT_INSIDE_PLATFORM_REPOSITORY", not self._is_relative_to(parent, repo), "Target parent must be external to the platform repository.")
        self._rule(rules, blockers, "TARGET_PARENT_OUTSIDE_ALLOWED_ROOTS", self._is_under_any_root(parent, target_roots), "Target parent must be inside an allowed target root.")
        self._rule(rules, blockers, "OUTPUT_ROOT_OUTSIDE_ALLOWED_ROOTS", self._is_under_any_root(output, target_roots), "Output root must be inside an allowed target root.")
        self._rule(rules, blockers, "OUTPUT_ROOT_INSIDE_PLATFORM_REPOSITORY", not self._is_relative_to(output, repo), "Output root must be external to the platform repository.")
        self._rule(rules, blockers, "SOURCE_TARGET_EQUAL", source != parent, "Source and target parent must differ.")
        self._rule(rules, blockers, "OUTPUT_ROOT_INSIDE_SOURCE", not self._is_relative_to(output, source), "Output root must not be inside source.")
        self._rule(rules, blockers, "SOURCE_INSIDE_OUTPUT_ROOT", not self._is_relative_to(source, output), "Source must not be inside output root.")
        self._rule(rules, blockers, "UNSAFE_REPARSE_POINT", not self._has_reparse_point(raw_source) and not self._has_reparse_point(raw_parent), "Reparse points are not accepted for external intake.")
        self._rule(rules, blockers, "NETWORK_LOCATION_UNSUPPORTED", not self._is_network_path(source) and not self._is_network_path(parent), "Only local paths are supported.")
        nearest = self._nearest_existing_parent(parent)
        writable = nearest is not None and self._is_writable(nearest)
        self._rule(rules, blockers, "TARGET_PARENT_NOT_WRITABLE", writable, "Target parent must be writable.")
        if nearest and shutil.disk_usage(nearest).free < self._settings.minimum_free_disk_bytes:
            self._rule(rules, blockers, "INSUFFICIENT_DISK_SPACE", False, "Target volume has insufficient free space.")
        self._rule(rules, blockers, "OUTPUT_ROOT_ALREADY_EXISTS_UNMANAGED", not output.exists(), "Output root already exists and is not an approved product output.")
        if len(str(output)) > 240:
            warnings.append("PATH_LENGTH_NEAR_WINDOWS_LIMIT")
            rules.append(PathRuleResult(code="PATH_LENGTH_NEAR_WINDOWS_LIMIT", status="warning", message="Resolved output path is close to the Windows limit."))
        status = "blocked" if blockers else ("passed_with_warnings" if warnings else "passed")
        payload = {"validation_id": f"path-validation-{uuid4().hex[:12]}", "captured_at": captured_at, "policy_version": self.policy_version, "status": status, "source_path": str(source), "target_parent_path": str(parent), "generated_output_name": output_name, "resolved_output_root": str(output), "platform_repository_root": str(repo), "target_output_path": str(output), "source_fingerprint": self._fingerprint(source), "rules": [rule.model_dump(mode="json") for rule in rules], "blockers": sorted(set(blockers)), "warnings": sorted(set(warnings)), "target_reservation_eligible": not blockers and writable}
        return PathValidationResult(snapshot=PathValidationSnapshot(**payload, checksum=self._checksum(payload)))

    @staticmethod
    def _canonical(value: str) -> Path: return Path(value.strip()).expanduser().resolve(strict=False)
    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try: path.relative_to(root); return True
        except ValueError: return False
    @staticmethod
    def _is_network_path(path: Path) -> bool: return str(path).startswith(("\\\\", "//"))
    @staticmethod
    def _is_writable(path: Path) -> bool: return path.is_dir() and os.access(path, os.W_OK)
    @staticmethod
    def _nearest_existing_parent(path: Path) -> Path | None:
        while not path.exists() and path != path.parent: path = path.parent
        return path if path.exists() else None
    @staticmethod
    def _has_reparse_point(path: Path) -> bool:
        while path != path.parent:
            if path.is_symlink(): return True
            path = path.parent
        return False
    @staticmethod
    def _is_under_any_root(path: Path, roots: tuple[Path, ...]) -> bool:
        return any(PathValidationService._is_relative_to(path, root) for root in roots)
    @staticmethod
    def _output_name(source_name: str, family: str) -> str:
        major = family.strip().lower().removesuffix(".x")
        stem = re.sub(r"[^a-z0-9]+", "-", source_name.lower()).strip("-.")
        if not major.isdigit() or not stem or stem in {"con", "prn", "aux", "nul", ".", ".."}: raise ValueError("unsafe generated output name")
        return f"{stem}-angular-{major}"
    @staticmethod
    def _fingerprint(source: Path) -> str | None:
        if not source.is_dir(): return None
        rows = []
        for child in sorted(source.iterdir(), key=lambda item: item.name.lower()):
            stat = child.stat(); rows.append(f"{child.name}|{stat.st_size}|{stat.st_mtime_ns}|{child.is_dir()}")
        return "sha256:" + hashlib.sha256("\n".join(rows).encode()).hexdigest()
    @staticmethod
    def _checksum(payload: dict) -> str: return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    @staticmethod
    def _rule(rules: list[PathRuleResult], blockers: list[str], code: str, passed: bool, message: str) -> None:
        rules.append(PathRuleResult(code=code, status="passed" if passed else "blocked", message=message))
        if not passed: blockers.append(code)
