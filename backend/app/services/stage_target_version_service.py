"""Verify the Angular target represented by a stage workspace."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.lockfile_compatibility_service import LockfileCompatibilityService


class StageTargetVersionError(ValueError):
    """Raised when package and lockfile do not prove the approved target major."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StageTargetVersionService:
    """Single authority for target-version evidence at seal boundaries."""

    _VERSION = re.compile(r"(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)")

    _CRITICAL_PACKAGES = (
        "@angular/core",
        "@angular/cli",
        "@angular/compiler-cli",
        "@angular-devkit/build-angular",
    )

    def verify(self, workspace: Path, target_exact: str | None) -> str:
        if not target_exact:
            raise StageTargetVersionError(
                "STAGE_TARGET_VERSION_MISSING",
                "Approved stage target version is missing",
            )
        try:
            package = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
            lockfile = json.loads((workspace / "package-lock.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StageTargetVersionError(
                "STAGE_TARGET_VERSION_EVIDENCE_INVALID",
                "Sealed workspace package or lockfile cannot be read",
            ) from error

        expected = self._version(target_exact)
        if not expected:
            raise StageTargetVersionError(
                "STAGE_TARGET_VERSION_EVIDENCE_INVALID",
                "Sealed package.json and package-lock.json lack Angular core version evidence",
            )
        expected_major = expected.split(".", 1)[0]
        locked_core: str | None = None
        for pkg in self._CRITICAL_PACKAGES:
            declared_value = (
                (package.get("dependencies") or {}).get(pkg)
                or (package.get("devDependencies") or {}).get(pkg)
            )
            if declared_value is None:
                continue
            declared = self._version(declared_value)
            locked = self._version(
                LockfileCompatibilityService.resolve_root_package_version(lockfile, pkg)
            )
            if not declared or not locked:
                raise StageTargetVersionError(
                    "STAGE_TARGET_VERSION_EVIDENCE_INVALID",
                    f"Sealed package.json and package-lock.json lack {pkg} version evidence",
                )
            declared_text = str(declared_value)
            declared_matches_lock = (
                declared.split(".", 1)[0] == locked.split(".", 1)[0]
                if declared_text.startswith(("^", "~"))
                else declared == locked
            )
            if not declared_matches_lock:
                raise StageTargetVersionError(
                    "STAGE_TARGET_VERSION_EVIDENCE_INVALID",
                    f"Sealed package.json and package-lock.json disagree on {pkg}",
                )
            if declared.split(".", 1)[0] != expected_major:
                raise StageTargetVersionError(
                    "STAGE_TARGET_VERSION_MISMATCH",
                    f"Sealed package.json does not match the completed stage target for {pkg}",
                )
            if locked.split(".", 1)[0] != expected_major:
                raise StageTargetVersionError(
                    "STAGE_TARGET_VERSION_MISMATCH",
                    f"Sealed package-lock.json does not match the completed stage target for {pkg}",
                )
            if pkg == "@angular/core":
                locked_core = locked
        # fallback: if core was not present (should not happen), verify core separately
        if locked_core is None:
            declared_value = (
                (package.get("dependencies") or {}).get("@angular/core")
                or (package.get("devDependencies") or {}).get("@angular/core")
            )
            declared = self._version(declared_value)
            locked = self._version(
                LockfileCompatibilityService.resolve_root_package_version(lockfile, "@angular/core")
            )
            if not declared or not locked:
                raise StageTargetVersionError(
                    "STAGE_TARGET_VERSION_EVIDENCE_INVALID",
                    "Sealed package.json and package-lock.json lack Angular core version evidence",
                )
            declared_text = str(declared_value)
            declared_matches_lock = (
                declared.split(".", 1)[0] == locked.split(".", 1)[0]
                if declared_text.startswith(("^", "~"))
                else declared == locked
            )
            if not declared_matches_lock:
                raise StageTargetVersionError(
                    "STAGE_TARGET_VERSION_EVIDENCE_INVALID",
                    "Sealed package.json and package-lock.json disagree on @angular/core",
                )
            if declared.split(".", 1)[0] != expected_major:
                raise StageTargetVersionError(
                    "STAGE_TARGET_VERSION_MISMATCH",
                    "Sealed package.json does not match the completed stage target",
                )
            if locked.split(".", 1)[0] != expected_major:
                raise StageTargetVersionError(
                    "STAGE_TARGET_VERSION_MISMATCH",
                    "Sealed package-lock.json does not match the completed stage target",
                )
            return locked
        return locked_core

    def _version(self, value) -> str | None:
        match = self._VERSION.search(str(value or ""))
        return match.group("version") if match else None
