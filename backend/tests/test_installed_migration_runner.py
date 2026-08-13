from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_runner_coerces_historical_angular_migration_versions(tmp_path: Path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not available")

    workspace = tmp_path / "workspace"
    core = workspace / "node_modules" / "@angular" / "core"
    tools = workspace / "node_modules" / "@angular-devkit" / "schematics"
    semver = workspace / "node_modules" / "semver"
    core.mkdir(parents=True)
    tools.mkdir(parents=True)
    semver.mkdir(parents=True)
    (workspace / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    (core / "package.json").write_text(
        json.dumps({"ng-update": {"migrations": "./migrations.json"}}),
        encoding="utf-8",
    )
    (core / "migrations.json").write_text(
        json.dumps(
            {
                "schematics": {
                    "historical": {"version": "9-beta", "factory": "./historical"},
                    "target": {"version": "12.0.0", "factory": "./target"},
                }
            }
        ),
        encoding="utf-8",
    )
    (semver / "index.js").write_text(
        """
function parts(value) { return String(value).split('.').map((part) => Number.parseInt(part, 10) || 0); }
function number(value) { const p = parts(value); return p[0] * 1000000 + p[1] * 1000 + p[2]; }
exports.valid = (value) => /^\\d+\\.\\d+\\.\\d+/.test(String(value)) ? value : null;
exports.coerce = (value) => { const match = String(value).match(/\\d+/); return match ? `${match[0]}.0.0` : null; };
exports.gt = (left, right) => number(left) > number(right);
exports.lte = (left, right) => number(left) <= number(right);
exports.compare = (left, right) => number(left) - number(right);
""",
        encoding="utf-8",
    )
    (tools / "tools.js").write_text(
        """
class NodeWorkflow {
  constructor() { this.reporter = { subscribe() {} }; }
  execute({ schematic }) { return { subscribe(observer) { console.log(`EXECUTED ${schematic}`); observer.complete(); } }; }
}
module.exports = { NodeWorkflow };
""",
        encoding="utf-8",
    )

    runner = Path(__file__).parents[1] / "app" / "command_execution" / "run_installed_migrations.cjs"
    result = subprocess.run(
        [node, str(runner), "@angular/core", "11.0.0", "12.2.17"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "EXECUTED target" in result.stdout
    assert "EXECUTED historical" not in result.stdout
    assert "MIGRATION_COMPLETE @angular/core 1" in result.stdout
