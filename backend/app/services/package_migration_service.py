"""Package-level migrate-only discovery for V2.2 P5 — P0-3 exact resolved versions.

Discovers changed direct dependencies that own ng-update migrations.
Always considers @angular/core and @angular/cli when their versions changed.
For other changed direct dependencies, inspects installed node_modules/<package>/package.json
and selects only packages declaring valid ng-update.migrations.

P0-3: Source exact from immutable checkpoint package-lock, target exact from current
verified package-lock, cross-checked against installed node_modules/<package>/package.json.
Never infer exact by stripping ^/~. Fail closed with deterministic blockers.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PackageMigrationRequest:
    package: str
    from_version: str
    to_version: str
    declares_migrations: bool
    migration_collection: str | None


class PackageMigrationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_VERSION = re.compile(r"(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)")


def _read_package_json(root: Path) -> dict | None:
    try:
        return json.loads((root / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_lock_json(root: Path) -> dict | None:
    try:
        return json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _resolve_from_lock(lock_data: dict | None, package: str) -> str | None:
    """Resolve exact version from npm lock v1 (dependencies root only) or modern packages shape.

    P0-4: For direct package under lockfile v1, ONLY lock["dependencies"][package]["version"]
    is authoritative. Do NOT recursively search nested dependency trees for direct dependencies.
    Modern lock: lock["packages"][f"node_modules/{package}"]["version"] remains correct.
    """
    if not isinstance(lock_data, dict) or not package:
        return None
    # modern packages shape: packages["node_modules/<package>"].version
    packages = lock_data.get("packages")
    if isinstance(packages, dict):
        entry = packages.get(f"node_modules/{package}")
        if isinstance(entry, dict) and isinstance(entry.get("version"), str):
            return entry["version"].strip()
    # legacy v1 shape: ONLY root dependencies[package].version, no nested search
    dependencies = lock_data.get("dependencies")
    if isinstance(dependencies, dict):
        entry = dependencies.get(package)
        if isinstance(entry, dict) and isinstance(entry.get("version"), str):
            return entry["version"].strip()
    return None


def _read_installed_version(workspace_path: Path, package: str) -> str | None:
    try:
        installed = json.loads((workspace_path / "node_modules" / package / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(installed, dict):
        return None
    ver = installed.get("version")
    return ver.strip() if isinstance(ver, str) and ver.strip() else None


def _changed_direct_packages(checkpoint: dict, workspace: dict) -> dict[str, tuple[str | None, str | None]]:
    """Return {package: (from_raw, to_raw)} for direct deps where raw version string changed."""
    ck_deps = {**(checkpoint.get("dependencies") or {}), **(checkpoint.get("devDependencies") or {})}
    ws_deps = {**(workspace.get("dependencies") or {}), **(workspace.get("devDependencies") or {})}
    all_pkgs = set(ck_deps) | set(ws_deps)
    changed: dict[str, tuple[str | None, str | None]] = {}
    for pkg in all_pkgs:
        ck_raw = ck_deps.get(pkg)
        ws_raw = ws_deps.get(pkg)
        if ck_raw != ws_raw:
            if isinstance(ck_raw, str) or isinstance(ws_raw, str):
                changed[pkg] = (ck_raw if isinstance(ck_raw, str) else None, ws_raw if isinstance(ws_raw, str) else None)
    return changed


def _declares_migrations(workspace_path: Path, package: str) -> tuple[bool, str | None]:
    """Inspect installed node_modules/<package>/package.json for ng-update.migrations."""
    try:
        installed = json.loads((workspace_path / "node_modules" / package / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, None
    if not isinstance(installed, dict):
        return False, None
    ng_update = installed.get("ng-update")
    if not isinstance(ng_update, dict):
        return False, None
    migrations = ng_update.get("migrations")
    if not isinstance(migrations, str) or not migrations.strip():
        return False, None
    return True, migrations.strip()


class PackageMigrationService:
    """Discovery of package-level migrate-only requests using exact resolved versions."""

    def discover(self, checkpoint_path: Path, workspace_path: Path) -> tuple[PackageMigrationRequest, ...]:
        ck_root = Path(checkpoint_path)
        ws_root = Path(workspace_path)
        checkpoint_pkg = _read_package_json(ck_root)
        workspace_pkg = _read_package_json(ws_root)
        if checkpoint_pkg is None or workspace_pkg is None:
            raise PackageMigrationError(
                "PACKAGE_MIGRATION_EXACT_VERSION_MISSING",
                "Checkpoint or workspace package.json cannot be read",
            )
        changed = _changed_direct_packages(checkpoint_pkg, workspace_pkg)
        if not changed:
            return ()
        # exact authority locks
        ck_lock = _read_lock_json(ck_root)
        ws_lock = _read_lock_json(ws_root)
        # If lock missing entirely we cannot prove exact — fail closed per spec
        if ck_lock is None:
            raise PackageMigrationError(
                "PACKAGE_MIGRATION_EXACT_VERSION_MISSING",
                "Immutable checkpoint package-lock.json missing or unreadable",
            )
        if ws_lock is None:
            raise PackageMigrationError(
                "PACKAGE_MIGRATION_EXACT_VERSION_MISSING",
                "Target package-lock.json missing or unreadable",
            )
        results: list[PackageMigrationRequest] = []
        priority_packages = {"@angular/core", "@angular/cli"}
        for pkg in sorted(changed):
            from_raw, to_raw = changed[pkg]
            # P0-4 C: classify manifest transition
            # ADD: source doesn't exist, target exists -> no migrate-only range
            # REMOVE: source exists, target doesn't -> no migrate after removal
            # REPLACED: old package removed + new added are separate entries, both skipped here
            if from_raw is None and to_raw is not None:
                # ADDED package — no from exact, generic migrate not valid
                continue
            if from_raw is not None and to_raw is None:
                # REMOVED package — do not run generic migrate after removal
                continue
            # For remaining, both raw should be present; require exact resolved for both
            source_exact = _resolve_from_lock(ck_lock, pkg)
            target_exact = _resolve_from_lock(ws_lock, pkg)
            if source_exact is None or target_exact is None:
                # For UPGRADED/DOWNGRADED with both manifest entries, missing lock exact is failure
                # For unchanged spec but lock changed, still need both
                raise PackageMigrationError(
                    "PACKAGE_MIGRATION_EXACT_VERSION_MISSING",
                    f"Exact resolved version missing for {pkg}: source={source_exact!r} target={target_exact!r}",
                )
            if source_exact == target_exact:
                continue
            # P0-4 B: after npm ci, target lock and installed must both exist and equal — no leniency
            installed_exact = _read_installed_version(ws_root, pkg)
            if installed_exact is None:
                raise PackageMigrationError(
                    "PACKAGE_MIGRATION_TARGET_INSTALL_MISSING",
                    f"Installed package.json missing for {pkg} after npm ci: target lock {target_exact}",
                )
            if installed_exact != target_exact:
                raise PackageMigrationError(
                    "PACKAGE_MIGRATION_TARGET_VERSION_MISMATCH",
                    f"Target lock {target_exact} != installed {installed_exact} for {pkg}",
                )
            if pkg in priority_packages:
                declares, collection = _declares_migrations(ws_root, pkg)
                results.append(
                    PackageMigrationRequest(
                        package=pkg,
                        from_version=source_exact,
                        to_version=target_exact,
                        declares_migrations=declares,
                        migration_collection=collection,
                    )
                )
                continue
            declares, collection = _declares_migrations(ws_root, pkg)
            if not declares:
                continue
            results.append(
                PackageMigrationRequest(
                    package=pkg,
                    from_version=source_exact,
                    to_version=target_exact,
                    declares_migrations=True,
                    migration_collection=collection,
                )
            )
        return tuple(results)


# Functional alias for imports that expect a plain function
def discover(checkpoint_path: Path, workspace_path: Path) -> tuple[PackageMigrationRequest, ...]:
    return PackageMigrationService().discover(checkpoint_path, workspace_path)
