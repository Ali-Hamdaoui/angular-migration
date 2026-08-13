import json

from app.services.workspace_integrity_service import WorkspaceIntegrityError, WorkspaceIntegrityService
from app.services.workspace_fingerprint import LEGACY_STAGE_COMPLETE_FINGERPRINT_PROFILE
from app.workspaces.baseline import BaselineSandboxService


def test_unchanged_workspace_matches_approved_fingerprint(tmp_path):
    (tmp_path / "angular.json").write_text("{}", encoding="utf-8")
    expected = WorkspaceIntegrityService.fingerprint(tmp_path)

    result = WorkspaceIntegrityService().verify(tmp_path, expected_fingerprint=expected)

    assert result.actual_fingerprint == expected


def test_changed_workspace_is_rejected_before_planning_reads_it(tmp_path):
    (tmp_path / "angular.json").write_text("{}", encoding="utf-8")
    expected = WorkspaceIntegrityService.fingerprint(tmp_path)
    (tmp_path / "angular.json").write_text('{"changed": true}', encoding="utf-8")

    try:
        WorkspaceIntegrityService().verify(tmp_path, expected_fingerprint=expected)
    except WorkspaceIntegrityError as error:
        assert error.code == "PLANNING_WORKSPACE_FINGERPRINT_MISMATCH"
        assert error.expected_fingerprint == expected
        assert error.actual_fingerprint != expected
    else:
        raise AssertionError("changed workspace unexpectedly passed integrity verification")


def test_added_file_changes_the_authoritative_tree_fingerprint(tmp_path):
    (tmp_path / "angular.json").write_text("{}", encoding="utf-8")
    expected = WorkspaceIntegrityService.fingerprint(tmp_path)
    (tmp_path / "relevant.ts").write_text("export const value = 1;", encoding="utf-8")

    try:
        WorkspaceIntegrityService().verify(tmp_path, expected_fingerprint=expected)
    except WorkspaceIntegrityError as error:
        assert error.actual_fingerprint != expected
    else:
        raise AssertionError("added file unexpectedly passed integrity verification")


def test_approved_complete_tree_binding_is_verified_then_normalized_for_planning(tmp_path):
    (tmp_path / "angular.json").write_text("{}", encoding="utf-8")
    generated = tmp_path / "node_modules" / "package" / "index.js"
    generated.parent.mkdir(parents=True)
    generated.write_text("module.exports = true;", encoding="utf-8")
    approved = LEGACY_STAGE_COMPLETE_FINGERPRINT_PROFILE.fingerprint(tmp_path)

    result = WorkspaceIntegrityService().verify(tmp_path, expected_fingerprint=approved)

    assert result.expected_fingerprint == approved
    assert result.actual_fingerprint == WorkspaceIntegrityService.fingerprint(tmp_path)
    assert result.actual_fingerprint != approved


def test_baseline_fingerprint_remains_valid_after_expected_generated_outputs(tmp_path):
    run_root = tmp_path / "run"
    snapshot = run_root / "source-snapshot"
    sandbox = run_root / "baseline-sandbox"
    snapshot.mkdir(parents=True)
    approved_snapshot_fingerprint = "sha256:" + "a" * 64
    (snapshot / "snapshot-fingerprint.json").write_text(
        json.dumps({"fingerprint": approved_snapshot_fingerprint}),
        encoding="utf-8",
    )
    (snapshot / "angular.json").write_text('{"projects": {}}', encoding="utf-8")
    (snapshot / "package.json").write_text('{"scripts": {}}', encoding="utf-8")
    (snapshot / "package-lock.json").write_text('{"lockfileVersion": 3}', encoding="utf-8")

    baseline = BaselineSandboxService().create(
        run_id="run-1",
        snapshot_root=snapshot,
        baseline_path=sandbox,
        approved_snapshot_fingerprint=approved_snapshot_fingerprint,
        registered_run_root=run_root,
    )
    for relative_path in (
        "node_modules/.package-lock.json",
        ".angular/cache/18.2.0/cache.bin",
        "dist/portal/browser/main.js",
        "coverage/lcov.info",
    ):
        generated = sandbox / relative_path
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("generated", encoding="utf-8")

    result = WorkspaceIntegrityService().verify(
        sandbox,
        expected_fingerprint=baseline.fingerprint,
    )

    assert result.actual_fingerprint == baseline.fingerprint
