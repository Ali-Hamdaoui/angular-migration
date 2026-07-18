"""Synthetic Angular fixtures are generated outside the platform repository."""
import json
from pathlib import Path


def create_angular_fixture(root: Path, name: str = "Customer Portal") -> Path:
    source = root / name
    (source / "src" / "app").mkdir(parents=True)
    (source / "package.json").write_text(json.dumps({"name": name, "dependencies": {"@angular/core": "18.2.0", "@angular/cli": "18.2.12"}}, indent=2), encoding="utf-8")
    (source / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3}), encoding="utf-8")
    (source / "angular.json").write_text(json.dumps({"version": 1, "projects": {"app": {"projectType": "application"}}}), encoding="utf-8")
    (source / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"target": "ES2022"}}), encoding="utf-8")
    return source