"""Lockfile compatibility validation and evidence persistence (V2 F08)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.domain.compatibility import CompatibilityCatalogueEntry
from app.domain.execution_profile import Version
from app.domain.lockfile_compatibility import (
    LockfileCompatibilityVerdict,
    LockfileDependencySet,
    evaluate_lockfile_compatibility,
)
from app.repositories.models import LockfileGenerationEvidenceModel, MigrationRunModel, MigrationStageModel
from app.repositories.session import session_scope
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider


class LockfileCompatibilityError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


_DEFAULT_TYPESCRIPT_MINIMUMS: dict[int, str] = {18: "5.4.0", 19: "5.5.0", 20: "5.6.0", 21: "5.7.0"}


class LockfileCompatibilityService:
    """Parse lockfiles, validate them against the catalogue, persist evidence."""

    def __init__(
        self,
        *,
        catalogue_provider: CompatibilityCatalogueProvider | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalogue_provider = catalogue_provider or CompatibilityCatalogueProvider()
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    @staticmethod
    def inspect_lockfile(workspace: Path) -> LockfileDependencySet:
        """Parse package-lock.json into a deterministic dependency set."""
        path = workspace / "package-lock.json"
        if not path.is_file():
            return LockfileDependencySet(checksum="missing")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return LockfileDependencySet(checksum="missing")
        packages = payload.get("packages", {}) if isinstance(payload, dict) else {}
        resolved: dict[str, str] = {}
        if isinstance(packages, dict):
            for key, entry in packages.items():
                if not isinstance(entry, dict) or not key.startswith("node_modules/"):
                    continue
                name = key[len("node_modules/"):]
                # scoped packages use nested paths like node_modules/@scope/name
                if "/" in name and not name.startswith("@"):
                    continue
                version = entry.get("version")
                if isinstance(version, str) and name not in resolved:
                    resolved[name] = version
        root = packages.get("", {}) if isinstance(packages, dict) else {}
        root_deps = root.get("dependencies", {}) if isinstance(root, dict) else {}
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
        return LockfileDependencySet(
            lockfile_version=payload.get("lockfileVersion") if isinstance(payload, dict) and isinstance(payload.get("lockfileVersion"), int) else None,
            root_dependencies={k: v for k, v in root_deps.items() if isinstance(v, str)},
            resolved_packages=resolved,
            checksum=f"sha256:{digest}" if digest else "missing",
        )

    def validate_stage_lockfile(
        self, workspace: Path, source_family: str, target_family: str, catalogue_version: str | None = None
    ) -> LockfileCompatibilityVerdict:
        """Validate a stage workspace lockfile against the catalogue entry."""
        entry = self._catalogue_entry(source_family, target_family, catalogue_version)
        target_major = _target_major(target_family)
        dependency_set = self.inspect_lockfile(workspace)
        expected: dict[str, str | None] = {
            "@angular/core": entry.target_angular_exact,
            "@angular/cli": entry.target_cli_exact,
        }
        if entry.typescript_exact:
            expected["typescript"] = entry.typescript_exact
        if entry.rxjs_exact:
            expected["rxjs"] = entry.rxjs_exact
        if entry.zone_js_exact:
            expected["zone.js"] = entry.zone_js_exact
        minimums: dict[str, str] = {}
        if not entry.typescript_exact:
            minimums["typescript"] = _DEFAULT_TYPESCRIPT_MINIMUMS.get(target_major, "5.0.0")
        if not entry.rxjs_exact:
            minimums["rxjs"] = "6.5.3"
        if not entry.zone_js_exact:
            minimums["zone.js"] = "0.14.0"
        return evaluate_lockfile_compatibility(
            dependency_set,
            source_family=source_family,
            target_family=target_family,
            catalogue_expected=expected,
            catalogue_minimums=minimums,
        )

    def _catalogue_entry(self, source_family: str, target_family: str, catalogue_version: str | None) -> CompatibilityCatalogueEntry:
        catalogue = self._catalogue_provider.load(catalogue_version or CompatibilityCatalogueProvider.CURRENT_VERSION)
        entry = catalogue.entry_for(source_family, target_family)
        if entry is None:
            raise LockfileCompatibilityError(
                "CATALOGUE_ENTRY_MISSING",
                f"No compatibility catalogue entry for {source_family} -> {target_family}",
            )
        return entry

    def record_evidence(
        self,
        *,
        run_id: str,
        stage_id: str,
        workspace: Path,
        verdict: LockfileCompatibilityVerdict,
        node_version: str | None = None,
        npm_version: str | None = None,
        node_sha256: str | None = None,
        npm_sha256: str | None = None,
        execution_id: str | None = None,
        deterministic: bool = True,
    ) -> LockfileGenerationEvidenceModel:
        """Persist lockfile generation evidence bound to the runtime used (F08-04)."""
        dependency_set = self.inspect_lockfile(workspace)
        with self._session_scope() as session:
            if session.get(MigrationRunModel, run_id) is None:
                raise LockfileCompatibilityError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            if session.get(MigrationStageModel, stage_id) is None:
                raise LockfileCompatibilityError("STAGE_NOT_FOUND", f"Migration stage {stage_id} not found")
            evidence_id = _evidence_id(run_id, stage_id, dependency_set.checksum)
            existing = session.get(LockfileGenerationEvidenceModel, evidence_id)
            if existing is not None:
                return existing
            row = LockfileGenerationEvidenceModel(
                id=evidence_id,
                run_id=run_id,
                stage_id=stage_id,
                execution_id=execution_id,
                lockfile_checksum=dependency_set.checksum,
                lockfile_version=dependency_set.lockfile_version,
                source_family=verdict.source_family,
                target_family=verdict.target_family,
                node_version=node_version,
                npm_version=npm_version,
                node_sha256=node_sha256,
                npm_sha256=npm_sha256,
                validation_status=verdict.status,
                blockers=verdict.blockers,
                findings=[finding.model_dump(mode="json") for finding in verdict.findings],
                deterministic=deterministic,
                created_at=self._now_provider(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def list_stage_evidence(self, run_id: str, stage_id: str) -> list[LockfileGenerationEvidenceModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(LockfileGenerationEvidenceModel)
                    .where(
                        LockfileGenerationEvidenceModel.run_id == run_id,
                        LockfileGenerationEvidenceModel.stage_id == stage_id,
                    )
                    .order_by(LockfileGenerationEvidenceModel.created_at.desc())
                ).all()
            )


def _target_major(target_family: str) -> int:
    try:
        return int(target_family.removeprefix("angular-").removesuffix(".x"))
    except ValueError:
        return 0


def _evidence_id(run_id: str, stage_id: str, lockfile_checksum: str) -> str:
    import hashlib

    return "lke-" + hashlib.sha256(f"{run_id}:{stage_id}:{lockfile_checksum}".encode()).hexdigest()[:24]
