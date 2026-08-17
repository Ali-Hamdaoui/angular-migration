import json
from pathlib import Path

import pytest

from app.services.next_stage_materializer_service import (
    NextStageMaterializerError,
    NextStageMaterializerService,
)


def _context(sealed: Path):
    return {
        "run_id": "run-1",
        "sealed_path": str(sealed),
        "sealed_fingerprint": "sha256:" + "1" * 64,
        "current_target_exact": "19.2.0",
        "remaining_route": [
            {
                "source_family": "angular-19.x",
                "target_family": "angular-20.x",
                "stage_id": "stage-19-to-20",
                "target_angular_exact": "20.3.0",
                "target_cli_exact": "20.3.0",
            }
        ],
        "catalogue_version": "catalog-v1",
        "execution_profile_id": "profile-node22",
        "execution_profile_checksum": "sha256:" + "2" * 64,
        "resolved_scripts": {"build": "build", "test": "test"},
        "project_targets": {},
        "builder": "@angular-devkit/build-angular:application",
        "validation_policy_id": "angular-stage-standard-v2",
        "recovery_policy_id": "safe-boundary-v1",
        "repair_policy_id": "proposer-reviewer-human-v1",
        "plan_version": 1,
    }


def test_next_stage_is_derived_from_sealed_exact_version_without_agents(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"@angular/core":"^19.2.0"}}', encoding="utf-8"
    )
    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/@angular/core": {"version": "19.2.0"}
                }
            }
        ),
        encoding="utf-8",
    )

    plan = NextStageMaterializerService().materialize(_context(tmp_path))

    assert plan.source_exact == "19.2.0"
    assert plan.target_exact == "20.3.0"
    assert plan.input_workspace_fingerprint == "sha256:" + "1" * 64


def test_next_stage_blocks_when_sealed_package_and_lock_disagree(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"@angular/core":"19.2.0"}}', encoding="utf-8"
    )
    (tmp_path / "package-lock.json").write_text(
        '{"packages":{"node_modules/@angular/core":{"version":"19.2.1"}}}',
        encoding="utf-8",
    )

    with pytest.raises(NextStageMaterializerError, match="disagree"):
        NextStageMaterializerService().materialize(_context(tmp_path))


def test_next_stage_reads_v1_sealed_lockfile(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"@angular/core":"^19.2.0"}}', encoding="utf-8"
    )
    (tmp_path / "package-lock.json").write_text(
        '{"lockfileVersion":1,"dependencies":{"@angular/core":{"version":"19.2.0"}}}',
        encoding="utf-8",
    )

    plan = NextStageMaterializerService().materialize(_context(tmp_path))
    assert plan.source_exact == "19.2.0"
