from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.dependency_repair_preflight_service import (
    DependencyRepairPreflightError,
    DependencyRepairPreflightService,
)


SOURCE_MANIFEST = {
    "name": "angular-crud-example",
    "dependencies": {
        "@angular/animations": "~11.0.4",
        "@angular/common": "~11.0.4",
        "@angular/compiler": "~11.0.4",
        "@angular/core": "~11.0.4",
        "@angular/forms": "~11.0.4",
        "@angular/platform-browser": "~11.0.4",
        "@angular/platform-browser-dynamic": "~11.0.4",
        "@angular/router": "~11.0.4",
        "rxjs": "~6.5.5",
        "zone.js": "~0.10.2",
    },
    "devDependencies": {
        "@angular/cli": "~11.0.4",
        "@angular/compiler-cli": "~11.0.4",
        "@angular-devkit/build-angular": "~0.1100.4",
        "typescript": "~4.0.2",
    },
}

COHORT_MANIFEST = {
    "name": "angular-crud-example",
    "dependencies": {
        "@angular/animations": "12.2.17",
        "@angular/common": "12.2.17",
        "@angular/compiler": "12.2.17",
        "@angular/core": "12.2.17",
        "@angular/forms": "12.2.17",
        "@angular/platform-browser": "12.2.17",
        "@angular/platform-browser-dynamic": "12.2.17",
        "@angular/router": "12.2.17",
        "rxjs": "6.6.7",
        "zone.js": "0.11.8",
    },
    "devDependencies": {
        "@angular/cli": "12.2.18",
        "@angular/compiler-cli": "12.2.17",
        "@angular-devkit/build-angular": "12.2.18",
        "typescript": "4.3.5",
    },
}

TRANSITION_4_3_5 = {
    "operations": [
        {
            "operation": "dependency_transition",
            "path": "package.json",
            "blocking_dependency": {
                "package": "typescript",
                "installed_version": "4.0.5",
                "required_peer_ranges": [
                    {"package": "typescript", "version_range": "~4.2.3 || ~4.3.2"}
                ],
            },
            "target_state": {
                "package": "typescript",
                "target_version": "4.3.5",
                "angular_major": 12,
            },
        }
    ]
}

TRANSITION_4_3_2 = json.loads(json.dumps(TRANSITION_4_3_5))
TRANSITION_4_3_2["operations"][0]["target_state"]["target_version"] = "4.3.2"


def _normalization(manifest: dict) -> dict:
    return {
        "operations": [
            {
                "operation": "dependency_manifest_normalization",
                "repair_kind": "dependency_manifest_normalization",
                "path": "package.json",
                "new_text": json.dumps(manifest),
            }
        ]
    }


def _workspace(tmp_path: Path, manifest: dict) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    return workspace


def test_transition_passes_when_target_matches_cohort_even_with_source_manifest(tmp_path):
    workspace = _workspace(tmp_path, SOURCE_MANIFEST)

    evidence = DependencyRepairPreflightService().validate(
        workspace=workspace,
        proposal=TRANSITION_4_3_5,
        source_family="angular-11.x",
        target_family="angular-12.x",
    )

    assert evidence["status"] == "passed"
    assert evidence["validation_mode"] == "dependency_transition"
    assert evidence["transition_contract"]["target_version"] == "4.3.5"


def test_transition_rejects_target_outside_cohort(tmp_path):
    workspace = _workspace(tmp_path, SOURCE_MANIFEST)

    with pytest.raises(DependencyRepairPreflightError) as error:
        DependencyRepairPreflightService().validate(
            workspace=workspace,
            proposal=TRANSITION_4_3_2,
            source_family="angular-11.x",
            target_family="angular-12.x",
        )

    assert error.value.code == "REPAIR_DEPENDENCY_PREFLIGHT_FAILED"
    assert "TARGET_COHORT_MISMATCH" in error.value.message
    assert '"proposed_spec": "4.3.2"' in error.value.message
    assert '"expected_exact": "4.3.5"' in error.value.message


def test_normalization_rejects_source_manifest(tmp_path):
    workspace = _workspace(tmp_path, SOURCE_MANIFEST)

    with pytest.raises(DependencyRepairPreflightError) as error:
        DependencyRepairPreflightService().validate(
            workspace=workspace,
            proposal=_normalization(SOURCE_MANIFEST),
            source_family="angular-11.x",
            target_family="angular-12.x",
        )

    assert "TARGET_COHORT_MISMATCH" in error.value.message


def test_normalization_passes_with_full_cohort(tmp_path):
    workspace = _workspace(tmp_path, SOURCE_MANIFEST)

    evidence = DependencyRepairPreflightService().validate(
        workspace=workspace,
        proposal=_normalization(COHORT_MANIFEST),
        source_family="angular-11.x",
        target_family="angular-12.x",
    )

    assert evidence["status"] == "passed"