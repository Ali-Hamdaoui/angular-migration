"""Deterministic Angular version proof and changed-file migration ledger."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType


class AngularTransformationEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AngularTransformationEvidenceService:
    _semver = re.compile(r"(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)")
    _excluded = frozenset({"node_modules", ".angular", "dist", "build", ".cache"})

    def build(
        self,
        workspace_path: str,
        checkpoint_path: str,
        *,
        target_core: str,
        target_cli: str,
        ng_version_output: str,
        angular_execution_id: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        workspace = Path(workspace_path).resolve(strict=True)
        checkpoint = Path(checkpoint_path).resolve(strict=True)
        package = self._json(workspace / "package.json")
        lock = self._json(workspace / "package-lock.json")
        installed_core = self._json(workspace / "node_modules" / "@angular" / "core" / "package.json")
        installed_cli = self._json(workspace / "node_modules" / "@angular" / "cli" / "package.json")
        dependencies = {**(package.get("dependencies") or {}), **(package.get("devDependencies") or {})}
        lock_packages = lock.get("packages") or {}
        core_sources = {
            "package_json": self._version(dependencies.get("@angular/core")),
            "package_lock": self._version((lock_packages.get("node_modules/@angular/core") or {}).get("version")),
            "installed_metadata": self._version(installed_core.get("version")),
            "ng_version": self._line_version(ng_version_output, "Angular:"),
        }
        cli_sources = {
            "package_json": self._version(dependencies.get("@angular/cli")),
            "package_lock": self._version((lock_packages.get("node_modules/@angular/cli") or {}).get("version")),
            "installed_metadata": self._version(installed_cli.get("version")),
            "ng_version": self._line_version(ng_version_output, "Angular CLI:"),
        }
        mismatches = {
            f"core.{name}": value for name, value in core_sources.items() if value != target_core
        } | {
            f"cli.{name}": value for name, value in cli_sources.items() if value != target_cli
        }
        if mismatches:
            raise AngularTransformationEvidenceError(
                "TARGET_VERSION_MISMATCH",
                "Four-source Angular version verification failed: "
                + ", ".join(f"{name}={value or 'missing'}" for name, value in sorted(mismatches.items())),
            )
        version_evidence = {
            "status": "verified",
            "target_core": target_core,
            "target_cli": target_cli,
            "core_sources": core_sources,
            "cli_sources": cli_sources,
        }
        before = self._manifest(checkpoint)
        after = self._manifest(workspace)
        paths = sorted(set(before) | set(after))
        changed = [
            {
                "path": path,
                "change": "added" if path not in before else "deleted" if path not in after else "modified",
                "before_checksum": before.get(path),
                "after_checksum": after.get(path),
                "attributed_execution_id": angular_execution_id,
            }
            for path in paths
            if before.get(path) != after.get(path)
        ]
        ledger = {
            "status": "recorded",
            "changed_file_count": len(changed),
            "changed_files": changed,
            "unattributed_files": [],
        }
        return version_evidence, ledger

    def write(
        self,
        *,
        run_id: str,
        stage_id: str,
        artifact_root: str,
        version_evidence: dict[str, object],
        ledger: dict[str, object],
        now: datetime | None = None,
    ):
        created_at = now or datetime.now(UTC)
        root = Path(artifact_root)
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        version = store.write_text_artifact(
            run_id,
            f"04_workflow_state/stages/{stage_id}/transformation/version-verification.json",
            json.dumps(version_evidence, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=stage_id,
            created_by="transformer",
            created_at=created_at,
            policy_version="four-source-version-v1",
        )
        migration = store.write_text_artifact(
            run_id,
            f"04_workflow_state/stages/{stage_id}/transformation/migration-ledger.json",
            json.dumps(ledger, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=stage_id,
            created_by="transformer",
            created_at=created_at,
            input_hashes={"version_evidence": version.ref.checksum},
            policy_version="migration-ledger-v1",
        )
        return version, migration

    @staticmethod
    def _json(path: Path) -> dict[str, object]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise AngularTransformationEvidenceError(
                "VERSION_EVIDENCE_MISSING", f"Required version source is unavailable: {path.name}"
            ) from error
        if not isinstance(value, dict):
            raise AngularTransformationEvidenceError(
                "VERSION_EVIDENCE_INVALID", f"Required version source is invalid: {path.name}"
            )
        return value

    def _version(self, value: object) -> str | None:
        match = self._semver.search(value) if isinstance(value, str) else None
        return match.group(1) if match else None

    def _line_version(self, output: str, label: str) -> str | None:
        for line in output.splitlines():
            if line.strip().startswith(label):
                return self._version(line)
        return None

    def _manifest(self, root: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root)
            if any(part in self._excluded for part in relative.parts):
                continue
            result[relative.as_posix()] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        return result
