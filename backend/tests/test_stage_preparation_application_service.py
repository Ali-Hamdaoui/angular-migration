from pathlib import Path

import pytest

from app.services.stage_preparation_application_service import StagePreparationApplicationService, StagePreparationError


def test_prepare_copies_baseline_and_returns_bound_stage_alias(tmp_path: Path):
    baseline = tmp_path / "baseline"
    stage_root = tmp_path / "stage-root"
    baseline.mkdir()
    (baseline / "package.json").write_text("{}", encoding="utf-8")

    result = StagePreparationApplicationService().prepare(
        {"BASELINE_SANDBOX": str(baseline), "STAGE_SANDBOX": str(stage_root)},
        "angular-18-to-19",
    )

    assert result.workspace_alias == "STAGE_WORKSPACE_ANGULAR_18_TO_19"
    assert Path(result.workspace_path).is_dir()
    assert result.fingerprint.startswith("sha256:")
    assert result.created is True
    assert (Path(result.workspace_path) / "package.json").exists()


def test_prepare_rejects_missing_registered_workspace_aliases(tmp_path: Path):
    with pytest.raises(StagePreparationError, match="aliases are required"):
        StagePreparationApplicationService().prepare({"BASELINE_SANDBOX": str(tmp_path / "baseline")}, "angular-18-to-19")

    assert not (tmp_path / "stage-root").exists()


def test_prepare_replays_an_existing_stage_workspace_without_copying_again(tmp_path: Path):
    baseline = tmp_path / "baseline"
    stage_root = tmp_path / "stage-root"
    baseline.mkdir()
    (baseline / "package.json").write_text("{}", encoding="utf-8")
    service = StagePreparationApplicationService()
    aliases = {"BASELINE_SANDBOX": str(baseline), "STAGE_SANDBOX": str(stage_root)}

    first = service.prepare(aliases, "angular-18-to-19")
    replay = service.prepare(aliases, "angular-18-to-19")

    assert replay.workspace_path == first.workspace_path
    assert replay.fingerprint == first.fingerprint
    assert replay.created is False
