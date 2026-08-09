import json
from pathlib import Path

import pytest

from app.services.workspace_configuration_reader import (
    WorkspaceConfigurationError,
    WorkspaceConfigurationReader,
)


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def test_reads_utf8_object_and_reports_checksum_and_parser_metadata(tmp_path):
    path = _write(tmp_path / "angular.json", b'{"projects": {}}')

    document = WorkspaceConfigurationReader().read_json_object(path, logical_name="angular.json")

    assert document.value == {"projects": {}}
    assert document.encoding == "utf-8"
    assert document.bom_detected is False
    assert document.parser_mode == "strict-json-with-optional-bom"
    assert document.checksum.startswith("sha256:")


def test_reads_utf8_bom_object_without_losing_bom_metadata(tmp_path):
    path = _write(tmp_path / "angular.json", b"\xef\xbb\xbf{" + b'"projects": {}}')

    document = WorkspaceConfigurationReader().read_json_object(path, logical_name="angular.json")

    assert document.value == {"projects": {}}
    assert document.encoding == "utf-8-sig"
    assert document.bom_detected is True


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b'{"projects":', "WORKSPACE_JSON_SYNTAX_INVALID"),
        (b"", "WORKSPACE_JSON_SYNTAX_INVALID"),
        (b"\xff\xfe", "WORKSPACE_JSON_ENCODING_INVALID"),
        (b"[]", "WORKSPACE_JSON_ROOT_INVALID"),
    ],
)
def test_classifies_invalid_json_inputs(tmp_path, content, code):
    path = _write(tmp_path / "angular.json", content)

    with pytest.raises(WorkspaceConfigurationError) as raised:
        WorkspaceConfigurationReader().read_json_object(path, logical_name="angular.json")

    assert raised.value.code == code
    assert raised.value.path == path
    assert raised.value.logical_name == "angular.json"


def test_preserves_json_decode_location(tmp_path):
    path = _write(tmp_path / "angular.json", b'{"projects": }')

    with pytest.raises(WorkspaceConfigurationError) as raised:
        WorkspaceConfigurationReader().read_json_object(path, logical_name="angular.json")

    assert raised.value.code == "WORKSPACE_JSON_SYNTAX_INVALID"
    assert raised.value.line == 1
    assert raised.value.column == 14
    assert raised.value.position == 13
    assert raised.value.exception_type == "JSONDecodeError"


def test_distinguishes_missing_and_unreadable_files(tmp_path, monkeypatch):
    missing = tmp_path / "missing.json"
    with pytest.raises(WorkspaceConfigurationError) as missing_error:
        WorkspaceConfigurationReader().read_json_object(missing, logical_name="angular.json")
    assert missing_error.value.code == "WORKSPACE_JSON_NOT_FOUND"

    unreadable = tmp_path / "unreadable.json"
    unreadable.write_bytes(b"{}")
    original_read_bytes = Path.read_bytes

    def fail_read_bytes(self):
        if self == unreadable:
            raise OSError("simulated access failure")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    with pytest.raises(WorkspaceConfigurationError) as unreadable_error:
        WorkspaceConfigurationReader().read_json_object(unreadable, logical_name="angular.json")
    assert unreadable_error.value.code == "WORKSPACE_JSON_UNREADABLE"
    assert unreadable_error.value.exception_type == "OSError"


def test_classifies_filesystem_stat_failure_as_unreadable(tmp_path, monkeypatch):
    path = tmp_path / "angular.json"
    path.write_bytes(b"{}")

    def fail_is_file(self):
        if self == path:
            raise OSError("simulated stat failure")
        return True

    monkeypatch.setattr(Path, "is_file", fail_is_file)
    with pytest.raises(WorkspaceConfigurationError) as raised:
        WorkspaceConfigurationReader().read_json_object(path, logical_name="angular.json")
    assert raised.value.code == "WORKSPACE_JSON_UNREADABLE"
