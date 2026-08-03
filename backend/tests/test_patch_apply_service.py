import hashlib
import json
import os
from pathlib import Path

import pytest
from app.artifact_store import LocalFilesystemArtifactStore
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


def test_dependency_change_applies_as_an_explicit_text_replacement(tmp_path: Path):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    package = workspace / "package.json"
    package.parent.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    package.write_text('{"dependencies":{"x":"1.0.0"}}', encoding="utf-8")
    proposal = {
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "dependency_change",
                "path": "package.json",
                "preimage_sha256": "sha256:" + hashlib.sha256(package.read_bytes()).hexdigest(),
                "old_text": '"x":"1.0.0"',
                "new_text": '"x":"2.0.0"',
            }
        ],
        "unified_diff": None,
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

    assert json.loads(package.read_text(encoding="utf-8"))["dependencies"]["x"] == "2.0.0"


def test_unknown_operation_is_rejected(tmp_path: Path):
    target = tmp_path / "src" / "app.ts"
    target.parent.mkdir(parents=True)
    target.write_text("old", encoding="utf-8")

    with pytest.raises(RepairApplicationError) as error:
        PatchApplyService()._prepare_operations(
            [
                {
                    "operation": "unknown",
                    "path": "src/app.ts",
                    "preimage_sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest(),
                    "old_text": "old",
                    "new_text": "new",
                }
            ],
            tmp_path,
        )

    assert error.value.code == "REPAIR_OPERATION_INVALID"


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
    attempted = False

    def noncooperating_writer(fd, size):
        nonlocal attempted
        if attempted:
            return original_ftruncate(fd, size)
        attempted = True
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


def test_all_target_locks_remain_held_until_apply_finishes(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    first = workspace / "src" / "first.ts"
    second = workspace / "src" / "second.ts"
    first.parent.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    first.write_text("first-old\n", encoding="utf-8")
    second.write_text("second-old\n", encoding="utf-8")
    proposal = {
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/first.ts",
                "old_text": "first-old",
                "new_text": "first-new",
                "preimage_sha256": "sha256:" + hashlib.sha256(first.read_bytes()).hexdigest(),
            },
            {
                "operation": "replace_text",
                "path": "src/second.ts",
                "old_text": "second-old",
                "new_text": "second-new",
                "preimage_sha256": "sha256:" + hashlib.sha256(second.read_bytes()).hexdigest(),
            },
        ],
        "unified_diff": None,
    }
    original_ftruncate = os.ftruncate
    calls = 0

    def mutate_processed_target(fd, size):
        nonlocal calls
        calls += 1
        if calls == 2:
            first.write_text("concurrent\n", encoding="utf-8")
        return original_ftruncate(fd, size)

    monkeypatch.setattr("os.ftruncate", mutate_processed_target)
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
    assert first.read_text(encoding="utf-8") == "first-old\n"
    assert second.read_text(encoding="utf-8") == "second-old\n"


def test_created_target_remains_locked_through_post_fingerprint(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    target = workspace / "src" / "created.ts"
    workspace.mkdir()
    artifacts.mkdir(parents=True)
    proposal = {
        "proposal_format": "operations",
        "operations": [{
            "operation": "create_text_file",
            "path": "src/created.ts",
            "content": "created\n",
        }],
        "unified_diff": None,
    }
    original_fingerprint = __import__(
        "app.services.patch_apply_service", fromlist=["_fingerprint_with_locked_targets"]
    )._fingerprint_with_locked_targets

    def mutate_created(root, locked_targets):
        target.write_text("concurrent\n", encoding="utf-8")
        return original_fingerprint(root, locked_targets)

    monkeypatch.setattr(
        "app.services.patch_apply_service._fingerprint_with_locked_targets",
        mutate_created,
    )
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
    assert not target.exists()


def test_untouched_workspace_change_blocks_apply_and_rolls_back(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    target = workspace / "src" / "target.ts"
    untouched = workspace / "src" / "untouched.ts"
    target.parent.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    untouched.write_text("stable\n", encoding="utf-8")
    proposal = {
        "proposal_format": "operations",
        "operations": [{
            "operation": "replace_text",
            "path": "src/target.ts",
            "old_text": "old",
            "new_text": "new",
            "preimage_sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest(),
        }],
        "unified_diff": None,
    }
    module = __import__("app.services.patch_apply_service", fromlist=["_workspace_manifest"])
    original_manifest = module._workspace_manifest
    calls = 0

    def mutate_untouched(root, locked_targets=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            untouched.write_text("concurrent\n", encoding="utf-8")
        return original_manifest(root, locked_targets)

    monkeypatch.setattr(module, "_workspace_manifest", mutate_untouched)
    with pytest.raises(RepairApplicationError, match="outside the approved repair"):
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
    assert untouched.read_text(encoding="utf-8") == "concurrent\n"


def test_delete_recreate_is_rejected_by_namespace_and_inode_binding(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    target = workspace / "src" / "deleted.ts"
    target.parent.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    proposal = {
        "proposal_format": "operations",
        "operations": [{
            "operation": "delete_text_file",
            "path": "src/deleted.ts",
            "preimage_sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest(),
        }],
        "unified_diff": None,
    }
    module = __import__("app.services.patch_apply_service", fromlist=["_fingerprint_with_locked_targets"])
    original_fingerprint = module._fingerprint_with_locked_targets

    def recreate_before_fingerprint(root, locked_targets):
        target.write_text("recreated\n", encoding="utf-8")
        return original_fingerprint(root, locked_targets)

    monkeypatch.setattr(module, "_fingerprint_with_locked_targets", recreate_before_fingerprint)
    with pytest.raises(RepairApplicationError, match="outside the approved repair"):
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


def test_initial_manifest_is_authority_checked_as_one_snapshot(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    target = workspace / "src" / "target.ts"
    untouched = workspace / "src" / "untouched.ts"
    target.parent.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    untouched.write_text("stable\n", encoding="utf-8")
    proposal = {
        "proposal_format": "operations",
        "operations": [{
            "operation": "replace_text",
            "path": "src/target.ts",
            "old_text": "old",
            "new_text": "new",
            "preimage_sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest(),
        }],
        "unified_diff": None,
    }
    module = __import__("app.services.patch_apply_service", fromlist=["_workspace_manifest"])
    original_manifest = module._workspace_manifest

    def mutate_between_authority_reads(root, locked_targets=None):
        untouched.write_text("changed-before-capture\n", encoding="utf-8")
        return original_manifest(root, locked_targets)

    monkeypatch.setattr(module, "_workspace_manifest", mutate_between_authority_reads)
    with pytest.raises(RepairApplicationError, match="workspace fingerprint changed"):
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


def _ledger_payload(artifacts: Path, ledger):
    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
    return json.loads(store.read_artifact_by_id(ledger.ref.artifact_id).content)


def test_apply_ledger_binds_approved_proposal_artifact_checksum(tmp_path: Path):
    """The apply ledger binds the approved proposal ARTIFACT checksum.

    ``RepairAttemptModel.proposal_checksum`` is the checksum of the stored
    proposal artifact bytes (``json.dumps(..., sort_keys=True, indent=2)``);
    the ledger must record that exact identity, not a canonical re-encoding of
    the parsed dict. RED until the fix: the ledger re-encodes with
    ``separators=(",", ":")`` and therefore differs from the approved checksum.
    """
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    target = workspace / "src" / "app.ts"
    target.parent.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    approved = "sha256:" + "a" * 64
    proposal = {
        "proposal_format": "operations",
        "operations": [{
            "operation": "replace_text",
            "path": "src/app.ts",
            "old_text": "old",
            "new_text": "new",
            "preimage_sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest(),
        }],
        "unified_diff": None,
    }

    _prepared, ledger, _fingerprint = PatchApplyService().apply(
        proposal=proposal,
        workspace_path=str(workspace),
        expected_fingerprint=StageSandboxCopier.fingerprint(workspace),
        run_id="run-1",
        stage_id="stage-1",
        artifact_root=str(artifacts),
        attempt_id="repair-1",
        approved_proposal_checksum=approved,
        proposal_artifact_checksum=approved,
    )

    assert _ledger_payload(artifacts, ledger)["proposal_checksum"] == approved
    assert PatchApplyService._checksum(proposal) != approved


def test_apply_ledger_proposal_checksum_falls_back_to_canonical_encoding(tmp_path: Path):
    """Without an artifact checksum the ledger pins a documented fallback.

    Direct service use (no approved artifact checksum supplied) records the
    canonical re-encoding ``json.dumps(sort_keys=True, separators=(",", ":"))``
    as an explicit, documented fallback; no consumer compares it against the
    stored-artifact checksum.
    """
    workspace = tmp_path / "workspace"
    artifacts = tmp_path / "artifacts" / "run-1"
    target = workspace / "src" / "app.ts"
    target.parent.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    proposal = {
        "proposal_format": "operations",
        "operations": [{
            "operation": "replace_text",
            "path": "src/app.ts",
            "old_text": "old",
            "new_text": "new",
            "preimage_sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest(),
        }],
        "unified_diff": None,
    }

    _prepared, ledger, _fingerprint = PatchApplyService().apply(
        proposal=proposal,
        workspace_path=str(workspace),
        expected_fingerprint=StageSandboxCopier.fingerprint(workspace),
        run_id="run-1",
        stage_id="stage-1",
        artifact_root=str(artifacts),
        attempt_id="repair-1",
    )

    assert _ledger_payload(artifacts, ledger)["proposal_checksum"] == PatchApplyService._checksum(
        proposal
    )
