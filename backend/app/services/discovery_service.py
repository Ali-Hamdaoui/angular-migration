"""Read-only, deterministic discovery coordinator.

This module deliberately has no database, event, or route implementation.  Those
adapters belong to S2-F01-I02; I01 owns the application contract and scanner logic.
"""

from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.domain.discovery import DiscoveryEvidenceDraft, DiscoveryFinding, ScannerFinding


class DiscoveryService:
    policy_version = "discovery-v1"
    _max_input_bytes = 1_000_000

    def discover(self, workspace: Path) -> tuple[tuple[ScannerFinding, ...], tuple[DiscoveryEvidenceDraft, ...]]:
        root = workspace.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("DISCOVERY_WORKSPACE_INVALID")
        scanners = (
            ("workspace", self._workspace),
            ("dependencies", self._dependencies),
            ("builders", self._builders),
            ("test_lint", self._test_lint),
            ("ssr_pwa_i18n", self._ssr_pwa_i18n),
            ("ui_theme", self._ui_theme),
            ("state_management", self._state_management),
        )
        with ThreadPoolExecutor(max_workers=len(scanners)) as executor:
            results = tuple(executor.map(lambda entry: self._scan(entry[0], entry[1], root), scanners))
        ordered = tuple(sorted(results, key=lambda result: result.scanner))
        drafts = tuple(self._evidence(result) for result in ordered)
        return ordered, drafts

    def _workspace(self, root: Path) -> ScannerFinding:
        angular = self._json(root / "angular.json")
        if angular is None:
            return self._unknown("workspace", "ANGULAR_JSON_MISSING")
        projects = angular.get("projects") if isinstance(angular, dict) else None
        if not isinstance(projects, dict):
            return self._unknown("workspace", "ANGULAR_PROJECTS_UNKNOWN", "angular.json")
        project_items = sorted((name, value) for name, value in projects.items() if isinstance(value, dict))
        apps = [name for name, item in project_items if item.get("projectType") == "application"]
        libraries = [name for name, item in project_items if item.get("projectType") == "library"]
        if (root / "nx.json").is_file():
            topology = "nx_workspace"
        elif len(apps) == 1 and not libraries:
            topology = "single_application_cli_workspace"
        elif len(apps) > 1:
            topology = "multi_application_cli_workspace"
        elif libraries:
            topology = "application_with_local_libraries" if apps else "publishable_library_workspace"
        else:
            topology = "unknown_workspace"
        return ScannerFinding(scanner="workspace", status="completed", findings=(
            self._fact("topology", topology, "angular.json"),
            self._fact("projects", apps, "angular.json"),
            self._fact("libraries", libraries, "angular.json"),
        ))

    def _dependencies(self, root: Path) -> ScannerFinding:
        package = self._json(root / "package.json")
        if package is None:
            return self._unknown("dependencies", "PACKAGE_JSON_MISSING")
        dependencies: dict[str, str] = {}
        for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            values = package.get(field, {}) if isinstance(package, dict) else {}
            if isinstance(values, dict):
                dependencies.update({str(name): self._redact(str(version)) for name, version in values.items()})
        private = sorted(name for name in dependencies if name.startswith("@") and not name.startswith("@angular/"))
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        lifecycle = sorted(name for name in scripts if name in {"preinstall", "install", "postinstall", "prepare"}) if isinstance(scripts, dict) else []
        return ScannerFinding(scanner="dependencies", status="completed", findings=(
            self._fact("inventory", dict(sorted(dependencies.items())), "package.json"),
            self._fact("private_package_candidates", private, "package.json"),
            self._fact("lifecycle_scripts", lifecycle, "package.json"),
        ))

    def _builders(self, root: Path) -> ScannerFinding:
        angular = self._json(root / "angular.json")
        if angular is None:
            return self._unknown("builders", "ANGULAR_JSON_MISSING")
        inventory: list[dict[str, str]] = []
        projects = angular.get("projects", {}) if isinstance(angular, dict) else {}
        if not isinstance(projects, dict):
            return self._unknown("builders", "ANGULAR_PROJECTS_UNKNOWN", "angular.json")
        for project, config in sorted(projects.items()):
            targets = config.get("architect", config.get("targets", {})) if isinstance(config, dict) else {}
            if isinstance(targets, dict):
                for target, target_config in sorted(targets.items()):
                    if isinstance(target_config, dict):
                        inventory.append({"project": str(project), "target": str(target), "builder": str(target_config.get("builder", "unknown"))})
        return ScannerFinding(scanner="builders", status="completed", findings=(self._fact("inventory", inventory, "angular.json"),))

    def _test_lint(self, root: Path) -> ScannerFinding:
        package = self._json(root / "package.json")
        if package is None:
            return self._unknown("test_lint", "PACKAGE_JSON_MISSING")
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        if not isinstance(scripts, dict):
            return self._unknown("test_lint", "PACKAGE_SCRIPTS_UNKNOWN", "package.json")
        selected = {name: self._redact(str(command)) for name, command in sorted(scripts.items()) if name in {"test", "lint", "e2e"} or name.startswith(("test:", "lint:"))}
        return ScannerFinding(scanner="test_lint", status="completed", findings=(self._fact("scripts", selected, "package.json"),))

    def _ssr_pwa_i18n(self, root: Path) -> ScannerFinding:
        package = self._json(root / "package.json")
        angular = self._json(root / "angular.json")
        if package is None:
            return self._unknown("ssr_pwa_i18n", "PACKAGE_JSON_MISSING")
        if angular is None:
            return self._unknown("ssr_pwa_i18n", "ANGULAR_JSON_MISSING")
        dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})} if isinstance(package, dict) else {}
        dependency_names = set(dependencies) if isinstance(dependencies, dict) else set()
        serialized = json.dumps(angular, sort_keys=True)
        inventory = {
            "ssr": "@angular/ssr" in dependency_names or "@nguniversal/express-engine" in dependency_names,
            "pwa": "@angular/pwa" in dependency_names or (root / "ngsw-config.json").is_file(),
            "i18n": "@angular/localize" in dependency_names or "localize" in serialized.lower(),
        }
        return ScannerFinding(scanner="ssr_pwa_i18n", status="completed", findings=(self._fact("inventory", inventory, "package.json", "angular.json"),))

    def _ui_theme(self, root: Path) -> ScannerFinding:
        package = self._json(root / "package.json")
        if package is None:
            return self._unknown("ui_theme", "PACKAGE_JSON_MISSING")
        dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})} if isinstance(package, dict) else {}
        names = set(dependencies) if isinstance(dependencies, dict) else set()
        inventory = {"ui_libraries": sorted(name for name in names if name in {"@angular/material", "primeng", "ng-zorro-antd", "bootstrap"}), "theme_configuration": "unknown"}
        return ScannerFinding(scanner="ui_theme", status="completed", findings=(self._fact("inventory", inventory, "package.json"),))

    def _state_management(self, root: Path) -> ScannerFinding:
        package = self._json(root / "package.json")
        if package is None:
            return self._unknown("state_management", "PACKAGE_JSON_MISSING")
        dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})} if isinstance(package, dict) else {}
        names = set(dependencies) if isinstance(dependencies, dict) else set()
        inventory = {"libraries": sorted(name for name in names if name.startswith("@ngrx/") or name in {"akita", "@angular-redux/store"})}
        return ScannerFinding(scanner="state_management", status="completed", findings=(self._fact("inventory", inventory, "package.json"),))

    def _evidence(self, result: ScannerFinding) -> DiscoveryEvidenceDraft:
        content = result.model_dump_json(indent=2)
        return DiscoveryEvidenceDraft(name=f"{result.scanner}_inventory.json", content=content, checksum=self._checksum(content))

    def _unknown(self, scanner: str, code: str, *references: str) -> ScannerFinding:
        return ScannerFinding(scanner=scanner, status="unknown", unknowns=(code,), findings=(), warnings=(),)

    def _scan(self, name: str, scanner: object, root: Path) -> ScannerFinding:
        try:
            return scanner(root)  # type: ignore[operator]
        except Exception as error:
            return ScannerFinding(scanner=name, status="blocked", unknowns=("SCANNER_RESULT_UNAVAILABLE",), warnings=(f"SCANNER_FAILED:{type(error).__name__}",))

    @staticmethod
    def _redact(value: str) -> str:
        return re.sub(r"(?i)((?:token|password|secret|authorization|api[_-]?key)\s*(?:=|:|\s)\s*)(?:Bearer\s+)?([^\s'\"]+)", r"\1[REDACTED]", value)

    @staticmethod
    def _fact(key: str, value: object, *references: str) -> DiscoveryFinding:
        return DiscoveryFinding(key=key, value=value, source_references=tuple(references))

    def _json(self, path: Path) -> dict | None:
        try:
            if not path.is_file() or path.stat().st_size > self._max_input_bytes:
                return None
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _checksum(content: str) -> str:
        return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
