from app.services.workspace_integrity_service import WorkspaceIntegrityError, WorkspaceIntegrityService


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
