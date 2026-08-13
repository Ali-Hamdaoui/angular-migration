from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.baseline_repair_contracts import BaselineRepairRequest
from app.services.baseline_repair_application_service import BaselineRepairApplicationService, RECIPE_ID, SPEC_CONTENT, SPEC_PATH
from app.services.patch_apply_service import PatchApplyService
from app.services.workspace_fingerprint import SOURCE_CONFIG_FINGERPRINT_PROFILE


def test_baseline_test_recipe_is_exact_and_patch_engine_applies_it(tmp_path: Path):
    workspace = tmp_path / "baseline"
    artifact_root = tmp_path / "artifacts" / "run-1"
    (workspace / "src" / "app").mkdir(parents=True)
    artifact_root.mkdir(parents=True)
    (workspace / "src" / "app" / "app.component.ts").write_text("export class AppComponent {}\n", encoding="utf-8")
    proposal = BaselineRepairApplicationService._proposal("run-1", "attempt-1", "sha256:" + "a" * 64)

    PatchApplyService().apply(
        proposal=proposal, workspace_path=str(workspace),
        expected_fingerprint=SOURCE_CONFIG_FINGERPRINT_PROFILE.fingerprint(workspace),
        run_id="run-1", stage_id=None, artifact_root=str(artifact_root), attempt_id="attempt-1",
    )

    assert proposal["recipe_id"] == RECIPE_ID
    assert proposal["operations"] == [{"operation": "create_text_file", "path": SPEC_PATH, "content": SPEC_CONTENT}]
    assert (workspace / SPEC_PATH).read_text(encoding="utf-8") == SPEC_CONTENT


def test_baseline_repair_contract_rejects_unproven_recipe():
    with pytest.raises(ValidationError):
        BaselineRepairRequest(
            expected_state_version=1, idempotency_key="repair", actor="operator",
            recipe_id="SOMETHING-ELSE", g03_package_checksum="sha256:" + "a" * 64,
        )


def test_approved_source_fingerprint_ignores_snapshot_metadata_but_detects_source_change(tmp_path: Path):
    snapshot, baseline = tmp_path / "snapshot", tmp_path / "baseline"
    for root in (snapshot, baseline):
        (root / "src").mkdir(parents=True)
        (root / "src" / "main.ts").write_text("stable\n", encoding="utf-8")
    (snapshot / "source-manifest.json").write_text("{}", encoding="utf-8")
    (snapshot / "snapshot-fingerprint.json").write_text("{}", encoding="utf-8")

    assert BaselineRepairApplicationService._approved_source_fingerprint(snapshot) == BaselineRepairApplicationService._approved_source_fingerprint(baseline)
    (baseline / "src" / "main.ts").write_text("changed\n", encoding="utf-8")
    assert BaselineRepairApplicationService._approved_source_fingerprint(snapshot) != BaselineRepairApplicationService._approved_source_fingerprint(baseline)
