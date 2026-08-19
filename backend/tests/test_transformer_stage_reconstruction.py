from pathlib import Path

import pytest

from app.services.transformer_stage_service import (
    StageSandboxCopier,
    TransformerStageError,
    TransformerStageService,
)


def test_reconstruct_workspace_allows_immutable_artifact_checkpoint(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts" / "run-1"
    stage_root = tmp_path / "stage-sandboxes"
    snapshot = artifact_root / "checkpoints" / "stage-1" / "pre-angular-update"
    workspace = stage_root / "stage-1"
    snapshot.mkdir(parents=True)
    (snapshot / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    workspace.mkdir(parents=True)
    (workspace / "package.json").write_text('{"name":"mutated"}', encoding="utf-8")

    expected = StageSandboxCopier.fingerprint(snapshot)
    observed = TransformerStageService.reconstruct_workspace(
        str(snapshot),
        str(workspace),
        str(stage_root),
        expected,
        str(artifact_root),
    )

    assert observed == expected
    assert StageSandboxCopier.fingerprint(workspace) == expected


def test_reconstruct_workspace_rejects_checkpoint_outside_governed_roots(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts" / "run-1"
    stage_root = tmp_path / "stage-sandboxes"
    outside_root = tmp_path / "untrusted"
    snapshot = outside_root / "checkpoint"
    workspace = stage_root / "stage-1"
    snapshot.mkdir(parents=True)
    workspace.mkdir(parents=True)
    (snapshot / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")

    expected = StageSandboxCopier.fingerprint(snapshot)
    with pytest.raises(TransformerStageError, match="governed roots"):
        TransformerStageService.reconstruct_workspace(
            str(snapshot),
            str(workspace),
            str(stage_root),
            expected,
            str(artifact_root),
        )
