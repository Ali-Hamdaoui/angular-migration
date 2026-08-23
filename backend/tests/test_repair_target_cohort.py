from __future__ import annotations

import json

import pytest

from app.services.repair_application_service import RepairApplicationError, RepairApplicationService


SERVICE = RepairApplicationService(scope=lambda: None)

COHORT = {
    "@angular/core": "12.2.17",
    "@angular/cli": "12.2.18",
    "typescript": "4.3.5",
    "zone.js": "0.11.8",
    "rxjs": "6.6.7",
}

CONTEXT = {
    "stage_id": "angular-11-to-12--63318c89dd5317b8",
    "source_exact": "11.0.4",
    "source_family": "angular-11.x",
    "target_family": "angular-12.x",
    "target_exact": "12.2.17",
    "target_cli_exact": "12.2.18",
    "target_cohort": COHORT,
}


def test_repair_proposal_receives_target_cohort_context():
    segment = SERVICE._stage_target_context(CONTEXT)

    assert segment["segment"] == "stage_target_cohort"
    assert segment["stage"] == "angular-11-to-12--63318c89dd5317b8"
    assert segment["source_angular"] == "11.0.4"
    assert segment["target_angular"] == "12.2.17"
    assert segment["target_cli"] == "12.2.18"
    assert segment["allowed_transition"] == "angular-11.x -> 12.2.17"
    assert "Never propose source package versions" in segment["rule"]
    assert segment["target_cohort"] == COHORT


def test_wrong_source_version_transition_target_rejected():
    proposal = {
        "operations": [
            {
                "operation": "dependency_transition",
                "target_state": {"package": "@angular/core", "target_version": "11.0.4"},
            }
        ]
    }

    with pytest.raises(RepairApplicationError) as error:
        SERVICE.validate_repair_target_cohort(CONTEXT, proposal)

    assert error.value.code == "TARGET_COHORT_MISMATCH"
    assert "11.0.4" in error.value.message
    assert "12.2.17" in error.value.message


def test_correct_cohort_transition_target_accepted():
    proposal = {
        "operations": [
            {
                "operation": "dependency_transition",
                "target_state": {"package": "typescript", "target_version": "4.3.5"},
            }
        ]
    }

    SERVICE.validate_repair_target_cohort(CONTEXT, proposal)


def test_correct_cohort_normalization_accepted():
    proposal = {
        "operations": [
            {
                "operation": "dependency_manifest_normalization",
                "new_text": json.dumps(
                    {
                        "dependencies": {
                            "@angular/core": "12.2.17",
                            "rxjs": "6.6.7",
                            "zone.js": "0.11.8",
                        },
                        "devDependencies": {"typescript": "4.3.5", "@angular/cli": "12.2.18"},
                    }
                ),
            }
        ]
    }

    SERVICE.validate_repair_target_cohort(CONTEXT, proposal)


def test_source_version_normalization_rejected():
    proposal = {
        "operations": [
            {
                "operation": "dependency_manifest_normalization",
                "new_text": json.dumps(
                    {
                        "dependencies": {"@angular/core": "~11.0.4"},
                        "devDependencies": {"typescript": "4.3.2"},
                    }
                ),
            }
        ]
    }

    with pytest.raises(RepairApplicationError) as error:
        SERVICE.validate_repair_target_cohort(CONTEXT, proposal)

    assert error.value.code == "TARGET_COHORT_MISMATCH"