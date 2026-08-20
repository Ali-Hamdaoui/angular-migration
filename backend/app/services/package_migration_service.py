"""Package-level migrate-only discovery for V2.2 P5.

Discovers changed direct dependencies that own ng-update migrations.
Always considers @angular/core and @angular/cli when their versions changed.
For other changed direct dependencies, inspects installed node_modules/<package>/package.json
and selects only packages declaring valid ng-update.migrations.
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


_VERSION = re.compile(r"(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)")


def _extract_version(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    m = _VERSION.search(value)
    return m.group(1) if m else None


def _read_package_json(root: Path) -> dict | None:
    try:
        return json.loads((root / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _changed_direct_packages(checkpoint: dict, workspace: dict) -> dict[str, tuple[str | None, str | None]]:
    """Return {package: (from_raw, to_raw)} for direct deps where raw version string changed."""
    ck_deps = {**(checkpoint.get("dependencies") or {}), **(checkpoint.get("devDependencies") or {})}
    ws_deps = {**(workspace.get("dependencies") or {}), **(workspace.get("devDependencies") or {})}
    # Consider union of direct deps from both
    all_pkgs = set(ck_deps) | set(ws_deps)
    changed: dict[str, tuple[str | None, str | None]] = {}
    for pkg in all_pkgs:
        ck_raw = ck_deps.get(pkg)
        ws_raw = ws_deps.get(pkg)
        # normalize to string for comparison
        if ck_raw != ws_raw:
            # Only report as changed if at least one side declares a version
            # Missing vs present is a change as well
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
    # valid string path, treat as declaring
    return True, migrations.strip()


class PackageMigrationService:
    """Discovery of package-level migrate-only requests."""

    def discover(self, checkpoint_path: Path, workspace_path: Path) -> tuple[PackageMigrationRequest, ...]:
        ck_root = Path(checkpoint_path)
        ws_root = Path(workspace_path)
        checkpoint_pkg = _read_package_json(ck_root)
        workspace_pkg = _read_package_json(ws_root)
        if checkpoint_pkg is None or workspace_pkg is None:
            return ()
        changed = _changed_direct_packages(checkpoint_pkg, workspace_pkg)
        if not changed:
            return ()
        results: list[PackageMigrationRequest] = []
        # Always consider these
        priority_packages = {"@angular/core", "@angular/cli"}
        for pkg, (from_raw, to_raw) in sorted(changed.items()):
            from_ver = _extract_version(from_raw) if from_raw is not None else None
            to_ver = _extract_version(to_raw) if to_raw is not None else None
            # Need exact versions on both sides to construct a range
            if from_ver is None or to_ver is None:
                continue
            if from_ver == to_ver:
                continue
            if pkg in priority_packages:
                declares, collection = _declares_migrations(ws_root, pkg)
                # Always include even if declares is False? Spec says always consider
                # but ledger should reflect declares. We include regardless.
                # If not declares, still mark but migration_collection None
                results.append(
                    PackageMigrationRequest(
                        package=pkg,
                        from_version=from_ver,
                        to_version=to_ver,
                        declares_migrations=declares,
                        migration_collection=collection,
                    )
                )
                continue
            # For other changed direct dependencies, only if they declare migrations
            declares, collection = _declares_migrations(ws_root, pkg)
            if not declares:
                continue
            results.append(
                PackageMigrationRequest(
                    package=pkg,
                    from_version=from_ver,
                    to_version=to_ver,
                    declares_migrations=True,
                    migration_collection=collection,
                )
            )
        return tuple(results)


# Functional alias for imports that expect a plain function
def discover(checkpoint_path: Path, workspace_path: Path) -> tuple[PackageMigrationRequest, ...]:
    return PackageMigrationService().discover(checkpoint_path, workspace_path)
