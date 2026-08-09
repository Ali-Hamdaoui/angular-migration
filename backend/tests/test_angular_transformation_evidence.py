import json
from pathlib import Path

import pytest

from app.services.angular_transformation_evidence_service import (
    AngularTransformationEvidenceError,
    AngularTransformationEvidenceService,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_four_source_version_proof_and_changed_file_ledger(tmp_path: Path):
    before = tmp_path / "before"
    workspace = tmp_path / "workspace"
    before.mkdir()
    workspace.mkdir()
    _write_json(before / "package.json", {"dependencies": {"@angular/core": "18.2.0"}})
    _write_json(
        workspace / "package.json",
        {"dependencies": {"@angular/core": "^19.2.0", "@angular/cli": "~19.2.0"}},
    )
    _write_json(
        workspace / "package-lock.json",
        {
            "packages": {
                "node_modules/@angular/core": {"version": "19.2.0"},
                "node_modules/@angular/cli": {"version": "19.2.0"},
            }
        },
    )
    _write_json(workspace / "node_modules/@angular/core/package.json", {"version": "19.2.0"})
    _write_json(workspace / "node_modules/@angular/cli/package.json", {"version": "19.2.0"})

    versions, ledger = AngularTransformationEvidenceService().build(
        str(workspace),
        str(before),
        target_core="19.2.0",
        target_cli="19.2.0",
        ng_version_output="Angular CLI: 19.2.0\nAngular: 19.2.0\n",
        angular_execution_id="execution-angular",
    )

    assert versions["status"] == "verified"
    assert set(versions["core_sources"]) == {
        "package_json", "package_lock", "installed_metadata", "ng_version"
    }
    assert ledger["changed_file_count"] == 2
    assert all(
        item["attributed_execution_id"] == "execution-angular"
        for item in ledger["changed_files"]
    )
    assert not any(item["path"].startswith("node_modules/") for item in ledger["changed_files"])


def test_four_source_version_proof_rejects_one_mismatch(tmp_path: Path):
    workspace = tmp_path / "workspace"
    before = tmp_path / "before"
    workspace.mkdir()
    before.mkdir()
    _write_json(
        workspace / "package.json",
        {"dependencies": {"@angular/core": "19.2.0", "@angular/cli": "19.2.0"}},
    )
    _write_json(
        workspace / "package-lock.json",
        {
            "packages": {
                "node_modules/@angular/core": {"version": "19.2.0"},
                "node_modules/@angular/cli": {"version": "19.2.0"},
            }
        },
    )
    _write_json(workspace / "node_modules/@angular/core/package.json", {"version": "19.1.0"})
    _write_json(workspace / "node_modules/@angular/cli/package.json", {"version": "19.2.0"})

    with pytest.raises(AngularTransformationEvidenceError, match="installed_metadata"):
        AngularTransformationEvidenceService().build(
            str(workspace),
            str(before),
            target_core="19.2.0",
            target_cli="19.2.0",
            ng_version_output="Angular CLI: 19.2.0\nAngular: 19.2.0\n",
            angular_execution_id="execution-angular",
        )


def test_ng_version_output_with_aligned_columns_parses_cli_and_core(tmp_path: Path):
    before = tmp_path / "before"
    workspace = tmp_path / "workspace"
    before.mkdir()
    workspace.mkdir()
    _write_json(
        workspace / "package.json",
        {"dependencies": {"@angular/core": "^21.2.19", "@angular/cli": "~21.2.20"}},
    )
    _write_json(
        workspace / "package-lock.json",
        {
            "packages": {
                "node_modules/@angular/core": {"version": "21.2.19"},
                "node_modules/@angular/cli": {"version": "21.2.20"},
            }
        },
    )
    _write_json(workspace / "node_modules/@angular/core/package.json", {"version": "21.2.19"})
    _write_json(workspace / "node_modules/@angular/cli/package.json", {"version": "21.2.20"})

    versions, _ = AngularTransformationEvidenceService().build(
        str(workspace),
        str(before),
        target_core="21.2.19",
        target_cli="21.2.20",
        ng_version_output=(
            "\x1b[1mAngular CLI       \x1b[22m: "
            "\x1b[36m21.2.20\x1b[39m\n"
            "\x1b[1mAngular           \x1b[22m: "
            "\x1b[36m21.2.19\x1b[39m\n"
        ),
        angular_execution_id="execution-angular",
    )

    assert versions["core_sources"]["ng_version"] == "21.2.19"
    assert versions["cli_sources"]["ng_version"] == "21.2.20"
