"""Parser adapters and registry for deterministic command-output diagnostics."""

from __future__ import annotations

import re
from typing import Any, Callable

from app.domain.failure import (
    DiagnosticParserResult,
    DiagnosticParserType,
    FailureDiagnostic,
    ParserRegistry,
)


def _parse_npm(stdout: str, stderr: str, exit_code: int) -> DiagnosticParserResult:
    """Extract npm-specific diagnostics from command output."""
    diagnostics: list[FailureDiagnostic] = []
    combined = stderr + "\n" + stdout

    # npm ERR! patterns
    for m in re.finditer(r"npm ERR!\s+(.+?)(?:\n|$)", combined):
        msg = m.group(1).strip()
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.NPM,
            parser_confidence=0.9,
            message=msg[:2000],
            severity="error",
            raw_excerpt=m.group(0)[:2000],
        ))

    # Missing module / not found
    for m in re.finditer(r"MODULE_NOT_FOUND[:\s]+([^\s]+)", combined):
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.NPM,
            parser_confidence=0.85,
            message=f"Module not found: {m.group(1)}",
            code="MODULE_NOT_FOUND",
            severity="error",
        ))

    confidence = min(0.9, 0.3 + 0.3 * len(diagnostics)) if diagnostics else 0.3
    return DiagnosticParserResult(
        parser_type=DiagnosticParserType.NPM,
        confidence=confidence,
        diagnostics=diagnostics,
        exit_code_hint=exit_code,
        raw_excerpt=stderr[:4000] or stdout[:4000],
    )


def _parse_angular_cli(stdout: str, stderr: str, exit_code: int) -> DiagnosticParserResult:
    """Extract Angular CLI-specific diagnostics."""
    diagnostics: list[FailureDiagnostic] = []
    combined = stderr + "\n" + stdout

    # Angular build error
    for m in re.finditer(r"Error:\s(.+?)(?:\n|$)", combined):
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.ANGULAR_CLI,
            parser_confidence=0.9,
            message=m.group(1).strip()[:2000],
            severity="error",
            raw_excerpt=m.group(0)[:2000],
        ))

    # ng command not found
    if re.search(r"ng:\s+command\s+not\s+found", combined, re.IGNORECASE):
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.ANGULAR_CLI,
            parser_confidence=0.95,
            message="Angular CLI (ng) is not installed or not in PATH",
            code="NG_COMMAND_NOT_FOUND",
            severity="error",
        ))

    # Schematic errors
    for m in re.finditer(r"Collection\s\"@angular/(.+?)\".+?cannot\s+be\s+resolved", combined, re.IGNORECASE):
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.ANGULAR_CLI,
            parser_confidence=0.85,
            message=f"Angular schematic collection cannot be resolved: @angular/{m.group(1)}",
            code="SCHEMATIC_NOT_RESOLVED",
            severity="error",
        ))

    confidence = min(0.9, 0.3 + 0.3 * len(diagnostics)) if diagnostics else 0.3
    return DiagnosticParserResult(
        parser_type=DiagnosticParserType.ANGULAR_CLI,
        confidence=confidence,
        diagnostics=diagnostics,
        exit_code_hint=exit_code,
        raw_excerpt=stderr[:4000] or stdout[:4000],
    )


def _parse_typescript(stdout: str, stderr: str, exit_code: int) -> DiagnosticParserResult:
    """Extract TypeScript compiler diagnostics."""
    diagnostics: list[FailureDiagnostic] = []
    combined = stdout + "\n" + stderr

    # TS error: path(line,col): error TS1234: message
    for m in re.finditer(
        r"(?:^|\n)\s*([^\s].*?)\((\d+)(?:,(\d+))?\):\s+(error|warning)\s+(TS\d+):\s+(.+?)(?:\n|$)",
        combined,
    ):
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.TYPESCRIPT,
            parser_confidence=0.95,
            message=m.group(6).strip()[:2000],
            code=m.group(5),
            file_path=m.group(1).strip(),
            line_number=int(m.group(2)),
            column=int(m.group(3)) if m.group(3) else None,
            severity=m.group(4),
            raw_excerpt=m.group(0)[:2000],
        ))

    # TS error without location
    for m in re.finditer(r"(?:error|warning)\s+(TS\d+):\s+(.+?)(?:\n|$)", combined):
        # Skip if already matched with location
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.TYPESCRIPT,
            parser_confidence=0.8,
            message=m.group(2).strip()[:2000],
            code=m.group(1),
            severity="error" if m.group(0).startswith("error") else "warning",
            raw_excerpt=m.group(0)[:2000],
        ))

    # TypeScript error without TS code
    for m in re.finditer(r"src/.+?\.ts\(\d+,\d+\):\s+(error|warning)\s+(.+?)(?:\n|$)", combined):
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.TYPESCRIPT,
            parser_confidence=0.85,
            message=m.group(2).strip()[:2000],
            severity=m.group(1),
            file_path=m.group(0).split("(")[0].strip(),
            raw_excerpt=m.group(0)[:2000],
        ))

    confidence = min(0.95, 0.3 + 0.3 * len(diagnostics)) if diagnostics else 0.3
    return DiagnosticParserResult(
        parser_type=DiagnosticParserType.TYPESCRIPT,
        confidence=confidence,
        diagnostics=diagnostics,
        exit_code_hint=exit_code,
        raw_excerpt=stdout[:4000] or stderr[:4000],
    )


def _parse_template(stdout: str, stderr: str, exit_code: int) -> DiagnosticParserResult:
    """Extract Angular template compilation diagnostics."""
    diagnostics: list[FailureDiagnostic] = []
    combined = stderr + "\n" + stdout

    # Template parse errors
    for m in re.finditer(
        r"Template\s+parse\s+errors?\s*(?:\n|:)(.+?)(?:\n\s*\n|$)",
        combined,
        re.DOTALL,
    ):
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.TEMPLATE,
            parser_confidence=0.9,
            message=m.group(1).strip()[:2000],
            severity="error",
            raw_excerpt=m.group(0)[:4000],
        ))

    # Component template errors
    for m in re.finditer(
        r"component/.+?\.html\((\d+)\):\s+(error|warning)\s+(.+?)(?:\n|$)",
        combined,
        re.IGNORECASE,
    ):
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.TEMPLATE,
            parser_confidence=0.85,
            message=m.group(3).strip()[:2000],
            line_number=int(m.group(1)),
            severity=m.group(2),
            raw_excerpt=m.group(0)[:2000],
        ))

    confidence = min(0.9, 0.3 + 0.3 * len(diagnostics)) if diagnostics else 0.3
    return DiagnosticParserResult(
        parser_type=DiagnosticParserType.TEMPLATE,
        confidence=confidence,
        diagnostics=diagnostics,
        exit_code_hint=exit_code,
        raw_excerpt=stderr[:4000] or stdout[:4000],
    )


def _parse_test(stdout: str, stderr: str, exit_code: int) -> DiagnosticParserResult:
    """Extract test-runner diagnostics."""
    diagnostics: list[FailureDiagnostic] = []
    combined = stdout + "\n" + stderr

    # FAIL / PASS test markers
    for m in re.finditer(r"(?:FAIL|PASS)\s+(.+?)(?:\s|$)", combined):
        is_fail = m.group(0).startswith("FAIL")
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.TEST,
            parser_confidence=0.8,
            message=f"{'FAIL' if is_fail else 'PASS'}: {m.group(1).strip()}",
            severity="error" if is_fail else "info",
            file_path=m.group(1).strip(),
            raw_excerpt=m.group(0)[:2000],
        ))

    # Test assertion errors
    for m in re.finditer(
        r"(?:AssertionError|expect|Expected|Received)[:\s]*(.+?)(?:\n\s*(?:\n|at\s)|$)",
        combined[:50000],
        re.DOTALL,
    ):
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.TEST,
            parser_confidence=0.75,
            message=m.group(1).strip()[:2000],
            severity="error",
            raw_excerpt=m.group(0)[:2000],
        ))

    confidence = min(0.8, 0.3 + 0.3 * len(diagnostics)) if diagnostics else 0.3
    return DiagnosticParserResult(
        parser_type=DiagnosticParserType.TEST,
        confidence=confidence,
        diagnostics=diagnostics,
        exit_code_hint=exit_code,
        raw_excerpt=stdout[:4000] or stderr[:4000],
    )


def _parse_generic(stdout: str, stderr: str, exit_code: int) -> DiagnosticParserResult:
    """Generic fallback parser for unclassified command output."""
    diagnostics: list[FailureDiagnostic] = []
    combined = stderr + "\n" + stdout

    # Generic error lines (non-empty stderr)
    for line in stderr.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) > 10 and exit_code != 0:
            diagnostics.append(FailureDiagnostic(
                parser_type=DiagnosticParserType.GENERIC,
                parser_confidence=0.4,
                message=stripped[:2000],
                severity="error",
                raw_excerpt=line[:2000],
            ))
            if len(diagnostics) >= 10:
                break

    # Permission denied
    if re.search(r"Permission\s+denied", combined, re.IGNORECASE):
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.GENERIC,
            parser_confidence=0.7,
            message="Permission denied — check file/directory access rights",
            code="PERMISSION_DENIED",
            severity="error",
        ))

    # Command not found
    if re.search(r"(?:command\s+not\s+found|not\s+a\s+command|not\s+found)", combined, re.IGNORECASE):
        diagnostics.append(FailureDiagnostic(
            parser_type=DiagnosticParserType.GENERIC,
            parser_confidence=0.6,
            message="Required command or file not found",
            code="COMMAND_NOT_FOUND",
            severity="error",
        ))

    confidence = min(0.6, 0.2 + 0.15 * len(diagnostics)) if diagnostics else 0.2
    return DiagnosticParserResult(
        parser_type=DiagnosticParserType.GENERIC,
        confidence=confidence,
        diagnostics=diagnostics,
        exit_code_hint=exit_code,
        raw_excerpt=stderr[:4000] or stdout[:4000],
    )


def create_default_parser_registry() -> ParserRegistry:
    """Build the default parser registry with all built-in parsers."""
    return {
        DiagnosticParserType.NPM: _parse_npm,
        DiagnosticParserType.ANGULAR_CLI: _parse_angular_cli,
        DiagnosticParserType.TYPESCRIPT: _parse_typescript,
        DiagnosticParserType.TEMPLATE: _parse_template,
        DiagnosticParserType.TEST: _parse_test,
        DiagnosticParserType.GENERIC: _parse_generic,
    }
