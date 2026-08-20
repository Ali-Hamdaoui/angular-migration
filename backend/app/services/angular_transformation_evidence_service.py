"""Deterministic Angular version proof and changed-file migration ledger."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.services.lockfile_compatibility_service import LockfileCompatibilityService

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class AngularTransformationEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AngularTransformationEvidenceService:
    _semver = re.compile(r"(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)")
    _excluded = frozenset({"node_modules", ".angular", ".git", "dist", "build", ".cache"})

    def build(
        self,
        workspace_path: str,
        checkpoint_path: str,
        *,
        target_core: str,
        target_cli: str,
        ng_version_output: str,
        angular_execution_id: str,
        expected_pre_fingerprint: str | None = None,
        expected_post_fingerprint: str | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        workspace = Path(workspace_path).resolve(strict=True)
        checkpoint = Path(checkpoint_path).resolve(strict=True)
        package = self._json(workspace / "package.json")
        lock = self._json(workspace / "package-lock.json")
        installed_core = self._json(workspace / "node_modules" / "@angular" / "core" / "package.json")
        installed_cli = self._json(workspace / "node_modules" / "@angular" / "cli" / "package.json")
        dependencies = {**(package.get("dependencies") or {}), **(package.get("devDependencies") or {})}
        core_sources = {
            "package_json": self._version(dependencies.get("@angular/core")),
            "package_lock": self._version(LockfileCompatibilityService.resolve_root_package_version(lock, "@angular/core")),
            "installed_metadata": self._version(installed_core.get("version")),
            "ng_version": self._line_version(ng_version_output, "Angular:"),
        }
        cli_sources = {
            "package_json": self._version(dependencies.get("@angular/cli")),
            "package_lock": self._version(LockfileCompatibilityService.resolve_root_package_version(lock, "@angular/cli")),
            "installed_metadata": self._version(installed_cli.get("version")),
            "ng_version": self._line_version(ng_version_output, "Angular CLI:"),
        }
        mismatches = {}
        for label, sources, target in (
            ("core", core_sources, target_core),
            ("cli", cli_sources, target_cli),
        ):
            target_major = self._major(target)
            declared = sources["package_json"]
            resolved = [sources[name] for name in ("package_lock", "installed_metadata", "ng_version")]
            if not declared or self._major(declared) != target_major:
                mismatches[f"{label}.package_json"] = declared
            if not resolved or any(value is None or value != resolved[0] or self._major(value) != target_major for value in resolved):
                for name in ("package_lock", "installed_metadata", "ng_version"):
                    if sources[name] is None or sources[name] != resolved[0] or self._major(sources[name]) != target_major:
                        mismatches[f"{label}.{name}"] = sources[name]
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
            "resolved_core": core_sources["package_lock"],
            "resolved_cli": cli_sources["package_lock"],
            "core_sources": core_sources,
            "cli_sources": cli_sources,
        }
        ledger = self.migration_ledger(
            checkpoint,
            workspace,
            angular_execution_id=angular_execution_id,
            expected_pre_fingerprint=expected_pre_fingerprint,
            expected_post_fingerprint=expected_post_fingerprint,
        )
        return version_evidence, ledger

    def migration_ledger(
        self,
        checkpoint_path: str | Path,
        workspace_path: str | Path,
        *,
        angular_execution_id: str,
        expected_pre_fingerprint: str | None = None,
        expected_post_fingerprint: str | None = None,
    ) -> dict[str, object]:
        checkpoint = Path(checkpoint_path).resolve(strict=True)
        workspace = Path(workspace_path).resolve(strict=True)
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
        if (
            not changed
            and expected_pre_fingerprint
            and expected_post_fingerprint
            and expected_pre_fingerprint != expected_post_fingerprint
        ):
            raise AngularTransformationEvidenceError(
                "MIGRATION_LEDGER_ZERO_CHANGE_CONTRADICTION",
                "Pre/post workspace fingerprints differ but the migration ledger is empty.",
            )
        ledger = {
            "status": "recorded",
            "changed_file_count": len(changed),
            "changed_files": changed,
            "unattributed_files": [],
            "before_fingerprint": self._manifest_fingerprint(before),
            "after_fingerprint": self._manifest_fingerprint(after),
        }
        return ledger

    def migration_ledger_multi(
        self,
        checkpoint_path: str | Path,
        workspace_path: str | Path,
        *,
        migration_executions: tuple[dict[str, object], ...] | list[dict[str, object]] = (),
        expected_pre_fingerprint: str | None = None,
        expected_post_fingerprint: str | None = None,
    ) -> dict[str, object]:
        checkpoint = Path(checkpoint_path).resolve(strict=True)
        workspace = Path(workspace_path).resolve(strict=True)
        before = self._manifest(checkpoint)
        after = self._manifest(workspace)
        paths = sorted(set(before) | set(after))
        # normalize executions to compact records
        compact: list[dict[str, object]] = []
        for entry in migration_executions:
            if isinstance(entry, dict):
                compact.append(
                    {
                        "package": entry.get("package"),
                        "from_exact": entry.get("from_exact") or entry.get("from_version"),
                        "to_exact": entry.get("to_exact") or entry.get("to_version"),
                        "declares_migrations": entry.get("declares_migrations"),
                        "migration_collection": entry.get("migration_collection"),
                        "command_execution_id": entry.get("command_execution_id") or entry.get("execution_id"),
                        "command_status": entry.get("command_status") or entry.get("status"),
                        "output_artifact_refs": entry.get("output_artifact_refs") or entry.get("artifact_ids") or [],
                    }
                )
            else:
                # object with attributes
                compact.append(
                    {
                        "package": getattr(entry, "package", None),
                        "from_exact": getattr(entry, "from_exact", None) or getattr(entry, "from_version", None),
                        "to_exact": getattr(entry, "to_exact", None) or getattr(entry, "to_version", None),
                        "declares_migrations": getattr(entry, "declares_migrations", None),
                        "migration_collection": getattr(entry, "migration_collection", None),
                        "command_execution_id": getattr(entry, "command_execution_id", None) or getattr(entry, "execution_id", None),
                        "command_status": getattr(entry, "command_status", None) or getattr(entry, "status", None),
                        "output_artifact_refs": getattr(entry, "output_artifact_refs", None) or getattr(entry, "artifact_ids", None) or [],
                    }
                )
        # attribute files to first execution if available
        primary_id = compact[0].get("command_execution_id") if compact else None
        changed = [
            {
                "path": path,
                "change": "added" if path not in before else "deleted" if path not in after else "modified",
                "before_checksum": before.get(path),
                "after_checksum": after.get(path),
                "attributed_execution_id": primary_id,
            }
            for path in paths
            if before.get(path) != after.get(path)
        ]
        if (
            not changed
            and expected_pre_fingerprint
            and expected_post_fingerprint
            and expected_pre_fingerprint != expected_post_fingerprint
        ):
            raise AngularTransformationEvidenceError(
                "MIGRATION_LEDGER_ZERO_CHANGE_CONTRADICTION",
                "Pre/post workspace fingerprints differ but the migration ledger is empty.",
            )
        ledger = {
            "status": "recorded",
            "changed_file_count": len(changed),
            "changed_files": changed,
            "unattributed_files": [],
            "before_fingerprint": self._manifest_fingerprint(before),
            "after_fingerprint": self._manifest_fingerprint(after),
            "migration_executions": compact,
            "migration_execution_count": len(compact),
        }
        return ledger

    def build_multi(
        self,
        workspace_path: str,
        checkpoint_path: str,
        *,
        target_core: str,
        target_cli: str,
        ng_version_output: str,
        migration_executions: tuple[dict[str, object], ...] | list[dict[str, object]] = (),
        expected_pre_fingerprint: str | None = None,
        expected_post_fingerprint: str | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        # reuse four-source verification from build() without duplicating attribution logic
        workspace = Path(workspace_path).resolve(strict=True)
        checkpoint = Path(checkpoint_path).resolve(strict=True)
        package = self._json(workspace / "package.json")
        lock = self._json(workspace / "package-lock.json")
        installed_core = self._json(workspace / "node_modules" / "@angular" / "core" / "package.json")
        installed_cli = self._json(workspace / "node_modules" / "@angular" / "cli" / "package.json")
        dependencies = {**(package.get("dependencies") or {}), **(package.get("devDependencies") or {})}
        core_sources = {
            "package_json": self._version(dependencies.get("@angular/core")),
            "package_lock": self._version(LockfileCompatibilityService.resolve_root_package_version(lock, "@angular/core")),
            "installed_metadata": self._version(installed_core.get("version")),
            "ng_version": self._line_version(ng_version_output, "Angular:"),
        }
        cli_sources = {
            "package_json": self._version(dependencies.get("@angular/cli")),
            "package_lock": self._version(LockfileCompatibilityService.resolve_root_package_version(lock, "@angular/cli")),
            "installed_metadata": self._version(installed_cli.get("version")),
            "ng_version": self._line_version(ng_version_output, "Angular CLI:"),
        }
        mismatches = {}
        for label, sources, target in (
            ("core", core_sources, target_core),
            ("cli", cli_sources, target_cli),
        ):
            target_major = self._major(target)
            declared = sources["package_json"]
            resolved = [sources[name] for name in ("package_lock", "installed_metadata", "ng_version")]
            if not declared or self._major(declared) != target_major:
                mismatches[f"{label}.package_json"] = declared
            if not resolved or any(value is None or value != resolved[0] or self._major(value) != target_major for value in resolved):
                for name in ("package_lock", "installed_metadata", "ng_version"):
                    if sources[name] is None or sources[name] != resolved[0] or self._major(sources[name]) != target_major:
                        mismatches[f"{label}.{name}"] = sources[name]
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
            "resolved_core": core_sources["package_lock"],
            "resolved_cli": cli_sources["package_lock"],
            "core_sources": core_sources,
            "cli_sources": cli_sources,
        }
        ledger = self.migration_ledger_multi(
            checkpoint,
            workspace,
            migration_executions=tuple(migration_executions) if isinstance(migration_executions, list) else migration_executions,
            expected_pre_fingerprint=expected_pre_fingerprint,
            expected_post_fingerprint=expected_post_fingerprint,
        )
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

    @staticmethod
    def _major(value: str | None) -> int | None:
        try:
            return int(value.split(".", 1)[0]) if value else None
        except (AttributeError, ValueError):
            return None

    def _line_version(self, output: str, label: str) -> str | None:
        clean_output = _ANSI_ESCAPE.sub("", output)

        key = label.rstrip(":").strip()
        pattern = re.compile(
            rf"^\s*{re.escape(key)}\s*:\s*(?P<value>.+?)\s*$"
        )

        for line in clean_output.splitlines():
            match = pattern.match(line)
            if match is not None:
                return self._version(match.group("value"))

        return None

    def _manifest(self, root: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root)
            if any(part in self._excluded for part in relative.parts):
                continue
            result[relative.as_posix()] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    @staticmethod
    def _manifest_fingerprint(manifest: dict[str, str]) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
