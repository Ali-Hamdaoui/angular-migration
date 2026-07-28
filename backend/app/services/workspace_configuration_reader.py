"""Authoritative reader for approval-critical workspace JSON files."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkspaceJsonDocument:
    path: Path
    logical_name: str
    value: dict[str, Any]
    checksum: str
    encoding: str
    bom_detected: bool
    parser_mode: str


class WorkspaceConfigurationError(ValueError):
    def __init__(
        self,
        code: str,
        path: Path,
        logical_name: str,
        *,
        retryable: bool = False,
        exception_type: str | None = None,
        checksum: str | None = None,
        bom_detected: bool | None = None,
        line: int | None = None,
        column: int | None = None,
        position: int | None = None,
        encoding: str | None = None,
        parser_mode: str | None = None,
        message: str | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.logical_name = logical_name
        self.retryable = retryable
        self.exception_type = exception_type
        self.checksum = checksum
        self.bom_detected = bom_detected
        self.line = line
        self.column = column
        self.position = position
        self.encoding = encoding
        self.parser_mode = parser_mode or "strict-json-with-optional-bom"
        self.message = message or code
        super().__init__(self.message)


class WorkspaceConfigurationReader:
    """Read strict UTF-8 JSON, accepting only the optional UTF-8 BOM."""

    parser_mode = "strict-json-with-optional-bom"

    def read_json_object(self, path: Path, *, logical_name: str) -> WorkspaceJsonDocument:
        path = Path(path)
        try:
            exists = path.is_file()
        except OSError as error:
            raise WorkspaceConfigurationError(
                "WORKSPACE_JSON_UNREADABLE", path, logical_name,
                exception_type=type(error).__name__, message=str(error),
            ) from error
        if not exists:
            raise WorkspaceConfigurationError("WORKSPACE_JSON_NOT_FOUND", path, logical_name)

        try:
            raw = path.read_bytes()
        except OSError as error:
            raise WorkspaceConfigurationError(
                "WORKSPACE_JSON_UNREADABLE", path, logical_name,
                exception_type=type(error).__name__, message=str(error),
                encoding=None, parser_mode=self.parser_mode,
            ) from error

        checksum = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        bom_detected = raw.startswith(b"\xef\xbb\xbf")
        encoding = "utf-8-sig" if bom_detected else "utf-8"
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError as error:
            raise WorkspaceConfigurationError(
                "WORKSPACE_JSON_ENCODING_INVALID", path, logical_name,
                exception_type=type(error).__name__, checksum=checksum,
                bom_detected=bom_detected, position=error.start, message=str(error),
                encoding=encoding, parser_mode=self.parser_mode,
            ) from error

        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise WorkspaceConfigurationError(
                "WORKSPACE_JSON_SYNTAX_INVALID", path, logical_name,
                exception_type=type(error).__name__, checksum=checksum,
                bom_detected=bom_detected, line=error.lineno, column=error.colno,
                position=error.pos, message=str(error),
                encoding=encoding, parser_mode=self.parser_mode,
            ) from error

        if not isinstance(value, dict):
            raise WorkspaceConfigurationError(
                "WORKSPACE_JSON_ROOT_INVALID", path, logical_name,
                checksum=checksum, bom_detected=bom_detected,
                encoding=encoding, parser_mode=self.parser_mode,
                message="The JSON root must be an object.",
            )
        return WorkspaceJsonDocument(
            path=path, logical_name=logical_name, value=value, checksum=checksum,
            encoding=encoding, bom_detected=bom_detected, parser_mode=self.parser_mode,
        )
