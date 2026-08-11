"""Bounded compatibility evidence for the removed Jest Angular bootstrap."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


LEGACY_JEST_BOOTSTRAPS = (
    "import 'jest-preset-angular/setup-jest';",
    "import 'jest-preset-angular/setup-jest.js';",
)
MODERN_JEST_BOOTSTRAP = (
    "import { setupZoneTestEnv } from 'jest-preset-angular/setup-env/zone';\n"
    "\n"
    "setupZoneTestEnv();\n"
)


class JestBootstrapCompatibilityError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class JestBootstrapCompatibilityMigration:
    old_text: str
    new_text: str
    preimage_sha256: str
    package_version: str
    package_manifest_sha256: str
    replacement_javascript_sha256: str
    replacement_types_sha256: str

    def operation(self) -> dict[str, object]:
        return {
            "operation": "replace_text",
            "path": "setup-jest.ts",
            "old_text": self.old_text,
            "new_text": self.new_text,
            "provenance": [
                {"key": "jest_preset_angular_version", "value": self.package_version},
                {"key": "obsolete_bootstrap_available", "value": "false"},
                {"key": "replacement_bootstrap", "value": "setup-env/zone"},
            ],
        }

    def evidence(self) -> dict[str, object]:
        return {
            "schema_version": "jest-bootstrap-compatibility.v1",
            "setup_path": "setup-jest.ts",
            "setup_preimage_sha256": self.preimage_sha256,
            "installed_package": "jest-preset-angular",
            "installed_version": self.package_version,
            "package_manifest_sha256": self.package_manifest_sha256,
            "obsolete_entries": {"setup-jest": False, "setup-jest.js": False},
            "replacement_entry": "setup-env/zone",
            "replacement_javascript_sha256": self.replacement_javascript_sha256,
            "replacement_types_sha256": self.replacement_types_sha256,
            "replacement_api": "setupZoneTestEnv",
            "decision": "migrate",
        }


class JestBootstrapCompatibilityService:
    """Detect one exact package-capability transition without guessing."""

    def detect(
        self, workspace_path: str | Path, run_root: str | Path
    ) -> JestBootstrapCompatibilityMigration | None:
        workspace = Path(workspace_path).resolve(strict=True)
        root = Path(run_root).resolve(strict=True)
        try:
            workspace.relative_to(root)
        except ValueError as error:
            raise JestBootstrapCompatibilityError(
                "JEST_BOOTSTRAP_WORKSPACE_ESCAPE",
                "Jest bootstrap compatibility workspace escapes the authoritative run root",
            ) from error

        setup = workspace / "setup-jest.ts"
        if not setup.exists():
            return None
        if setup.is_symlink() or not setup.is_file():
            raise JestBootstrapCompatibilityError(
                "JEST_BOOTSTRAP_PREIMAGE_INVALID",
                "setup-jest.ts must be a regular workspace file",
            )
        try:
            with setup.open("r", encoding="utf-8", newline="") as handle:
                source = handle.read()
        except (OSError, UnicodeError) as error:
            raise JestBootstrapCompatibilityError(
                "JEST_BOOTSTRAP_PREIMAGE_INVALID",
                "setup-jest.ts is not readable UTF-8 text",
            ) from error
        if source.replace("\r\n", "\n") == MODERN_JEST_BOOTSTRAP:
            return None
        legacy_preimage = source
        if legacy_preimage.endswith("\r\n"):
            legacy_preimage = legacy_preimage[:-2]
        elif legacy_preimage.endswith("\n"):
            legacy_preimage = legacy_preimage[:-1]
        if legacy_preimage not in LEGACY_JEST_BOOTSTRAPS:
            return None

        package_root = workspace / "node_modules" / "jest-preset-angular"
        manifest = package_root / "package.json"
        if not manifest.is_file() or manifest.is_symlink():
            return None
        try:
            manifest_bytes = manifest.read_bytes()
            package = json.loads(manifest_bytes.decode("utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as error:
            raise JestBootstrapCompatibilityError(
                "JEST_BOOTSTRAP_PACKAGE_EVIDENCE_INVALID",
                "Installed jest-preset-angular package metadata is invalid",
            ) from error
        version = package.get("version") if isinstance(package, dict) else None
        if package.get("name") != "jest-preset-angular" or not isinstance(version, str):
            raise JestBootstrapCompatibilityError(
                "JEST_BOOTSTRAP_PACKAGE_EVIDENCE_INVALID",
                "Installed jest-preset-angular package identity is invalid",
            )
        if any((package_root / entry).exists() for entry in ("setup-jest", "setup-jest.js")):
            return None

        replacement_javascript = package_root / "setup-env" / "zone" / "index.js"
        replacement_types = package_root / "setup-env" / "zone" / "index.d.ts"
        if any(path.is_symlink() or not path.is_file() for path in (replacement_javascript, replacement_types)):
            raise JestBootstrapCompatibilityError(
                "JEST_BOOTSTRAP_REPLACEMENT_UNAVAILABLE",
                "Installed jest-preset-angular removed setup-jest but does not provide setup-env/zone",
            )
        try:
            javascript_bytes = replacement_javascript.read_bytes()
            types_bytes = replacement_types.read_bytes()
            javascript = javascript_bytes.decode("utf-8")
            types = types_bytes.decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise JestBootstrapCompatibilityError(
                "JEST_BOOTSTRAP_REPLACEMENT_UNAVAILABLE",
                "Installed setup-env/zone evidence is not readable UTF-8 text",
            ) from error
        direct_types_export = re.search(
            r"export\s+declare\s+const\s+setupZoneTestEnv\b", types
        )
        commonjs_types_export = (
            re.search(
                r"declare\s+const\s+_default\s*:\s*\{[^}]*\bsetupZoneTestEnv\s*:",
                types,
                re.DOTALL,
            )
            and re.search(r"export\s*=\s*_default\s*;", types)
        )
        if (
            "setupZoneTestEnv" not in javascript
            or "module.exports" not in javascript
            or not (direct_types_export or commonjs_types_export)
        ):
            raise JestBootstrapCompatibilityError(
                "JEST_BOOTSTRAP_REPLACEMENT_UNAVAILABLE",
                "Installed setup-env/zone does not prove the setupZoneTestEnv API",
            )

        digest = lambda value: "sha256:" + hashlib.sha256(value).hexdigest()
        return JestBootstrapCompatibilityMigration(
            old_text=source,
            new_text=(MODERN_JEST_BOOTSTRAP.replace("\n", "\r\n") if source.endswith("\r\n") else MODERN_JEST_BOOTSTRAP),
            preimage_sha256=digest(setup.read_bytes()),
            package_version=version,
            package_manifest_sha256=digest(manifest_bytes),
            replacement_javascript_sha256=digest(javascript_bytes),
            replacement_types_sha256=digest(types_bytes),
        )
