import hashlib
import os
from pathlib import Path

import pytest
from app.services.patch_apply_service import PatchApplyService
from app.services.repair_application_service import RepairApplicationError
from app.services.stage_preparation_primitives import StageSandboxCopier


def test_operations_apply_atomically_with_preimage_and_ledger(tmp_path: Path):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    target = workspace / "src" / "app.ts"
    target.parent.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    target.write_text("const value = 'old';\n", encoding="utf-8")
    preimage = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    proposal = {
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/app.ts",
                "preimage_sha256": preimage,
                "old_text": "'old'",
                "new_text": "'new'",
            }
        ],
        "unified_diff": None,
    }

    _prepared, ledger, fingerprint = PatchApplyService().apply(
        proposal=proposal,
        workspace_path=str(workspace),
        expected_fingerprint=StageSandboxCopier.fingerprint(workspace),
        run_id="run-1",
        stage_id="stage-1",
        artifact_root=str(artifacts),
        attempt_id="repair-1",
    )

    assert target.read_text(encoding="utf-8") == "const value = 'new';\n"
    assert ledger.ref.checksum
    assert fingerprint == StageSandboxCopier.fingerprint(workspace)


def test_unified_diff_apply_accepts_header_like_hunk_content(tmp_path: Path):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    target = workspace / "src" / "app.ts"
    target.parent.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    target.write_text("-- text\n", encoding="utf-8")
    proposal = {
        "proposal_format": "unified_diff",
        "operations": [],
        "unified_diff": (
            "--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1 +1 @@\n--- text\n+++ text\n"
        ),
    }

    PatchApplyService().apply(
        proposal=proposal,
        workspace_path=str(workspace),
        expected_fingerprint=StageSandboxCopier.fingerprint(workspace),
        run_id="run-1",
        stage_id="stage-1",
        artifact_root=str(artifacts),
        attempt_id="repair-1",
    )

    assert target.read_text(encoding="utf-8") == "++ text\n"


def test_unified_diff_apply_normalizes_timestamped_headers(tmp_path: Path):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    target = workspace / "src" / "app.ts"
    target.parent.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    proposal = {
        "proposal_format": "unified_diff",
        "operations": [],
        "unified_diff": (
            "--- a/src/app.ts\t2026-08-01 12:00:00 +0000\n"
            "+++ b/src/app.ts\t2026-08-01 12:00:01 +0000\n"
            "@@ -1 +1 @@\n-old\n+new\n"
        ),
    }

    PatchApplyService().apply(
        proposal=proposal,
        workspace_path=str(workspace),
        expected_fingerprint=StageSandboxCopier.fingerprint(workspace),
        run_id="run-1",
        stage_id="stage-1",
        artifact_root=str(artifacts),
        attempt_id="repair-1",
    )

    assert target.read_text(encoding="utf-8") == "new\n"


def test_apply_rechecks_preimage_after_prepare_before_replace(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    target = workspace / "src" / "app.ts"
    target.parent.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    proposal = {
        "proposal_format": "operations",
        "operations": [{"operation": "replace_text", "path": "src/app.ts", "old_text": "old", "new_text": "new", "preimage_sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()}],
        "unified_diff": None,
    }
    original = PatchApplyService._prepare_operations

    def mutate_after_prepare(self, operations, root):
        changes = original(self, operations, root)
        target.write_text("concurrent\n", encoding="utf-8")
        return changes

    monkeypatch.setattr(PatchApplyService, "_prepare_operations", mutate_after_prepare)
    with pytest.raises(RepairApplicationError, match="preimage changed"):
        PatchApplyService().apply(
            proposal=proposal,
            workspace_path=str(workspace),
            expected_fingerprint=StageSandboxCopier.fingerprint(workspace),
            run_id="run-1",
            stage_id="stage-1",
            artifact_root=str(artifacts),
            attempt_id="repair-1",
        )
    assert target.read_text(encoding="utf-8") == "concurrent\n"


def test_target_lock_rejects_noncooperating_writer_before_mutation(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    target = workspace / "src" / "app.ts"
    target.parent.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    preimage = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    proposal = {
        "proposal_format": "operations",
        "operations": [{
            "operation": "replace_text",
            "path": "src/app.ts",
            "old_text": "old",
            "new_text": "new",
            "preimage_sha256": preimage,
        }],
        "unified_diff": None,
    }
    original_ftruncate = os.ftruncate

    def noncooperating_writer(fd, size):
        target.write_text("newer\n", encoding="utf-8")
        return original_ftruncate(fd, size)

    monkeypatch.setattr("os.ftruncate", noncooperating_writer)
    with pytest.raises(PermissionError):
        PatchApplyService().apply(
            proposal=proposal,
            workspace_path=str(workspace),
            expected_fingerprint=StageSandboxCopier.fingerprint(workspace),
            run_id="run-1",
            stage_id="stage-1",
            artifact_root=str(artifacts),
            attempt_id="repair-1",
        )
    assert target.read_text(encoding="utf-8") == "old\n"
