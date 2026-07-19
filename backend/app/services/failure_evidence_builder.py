"""Application service that builds immutable FailureEvidence from raw command output."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from app.domain.contracts import ArtifactRefDto, ArtifactType
from app.domain.failure import (
    DiagnosticParserResult,
    DiagnosticParserType,
    FailureBuilderInput,
    FailureDiagnostic,
    FailureEvidence,
    FailureFingerprintService,
    FailureOrigin,
    FailureStatus,
    OriginComparator,
    ParserRegistry,
)

# ---------------------------------------------------------------------------
# Stub parsers — each extracts basic patterns from raw command output.
# ---------------------------------------------------------------------------


def _stub_parse_npm(raw_output: str) -> DiagnosticParserResult:
    """Extract npm error diagnostics from raw command output."""
    diagnostics: list[FailureDiagnostic] = []
    lines = raw_output.splitlines()
    for i, line in enumerate(lines):
        # npm ERR! code ERESOLVE
        m = re.search(r"npm\s+ERR!\s+code\s+(\S+)", line, re.IGNORECASE)
        if m:
            diagnostics.append(
                FailureDiagnostic(
                    message=line.strip(),
                    code=m.group(1),
                    line_number=i + 1,
                    severity="error",
                    parser_type=DiagnosticParserType.NPM,
                    parser_confidence=0.95,
                )
            )
            continue
        # npm ERR! <message>
        m = re.match(r"npm\s+ERR!\s+(.+)", line, re.IGNORECASE)
        if m:
            diagnostics.append(
                FailureDiagnostic(
                    message=m.group(1).strip(),
                    line_number=i + 1,
                    severity="error",
                    parser_type=DiagnosticParserType.NPM,
                    parser_confidence=0.8,
                )
            )
    excerpt = "\n".join(lines[:20]) if diagnostics else None
    return DiagnosticParserResult(
        parser_type=DiagnosticParserType.NPM,
        confidence=0.9 if diagnostics else 0.0,
        diagnostics=diagnostics,
        raw_excerpt=excerpt,
    )


def _stub_parse_angular_cli(raw_output: str) -> DiagnosticParserResult:
    """Extract Angular CLI error diagnostics from raw command output."""
    diagnostics: list[FailureDiagnostic] = []
    lines = raw_output.splitlines()
    for i, line in enumerate(lines):
        # Error: <message>
        m = re.match(r"^\s*Error:\s*(.+)", line, re.IGNORECASE)
        if m:
            diagnostics.append(
                FailureDiagnostic(
                    message=m.group(1).strip(),
                    line_number=i + 1,
                    severity="error",
                    parser_type=DiagnosticParserType.ANGULAR_CLI,
                    parser_confidence=0.85,
                )
            )
            continue
        # An unhandled exception occurred:
        if re.search(r"unhandled\s+exception", line, re.IGNORECASE):
            diagnostics.append(
                FailureDiagnostic(
                    message=line.strip(),
                    line_number=i + 1,
                    severity="error",
                    parser_type=DiagnosticParserType.ANGULAR_CLI,
                    parser_confidence=0.7,
                )
            )
    excerpt = "\n".join(lines[:20]) if diagnostics else None
    return DiagnosticParserResult(
        parser_type=DiagnosticParserType.ANGULAR_CLI,
        confidence=0.85 if diagnostics else 0.0,
        diagnostics=diagnostics,
        raw_excerpt=excerpt,
    )


def _stub_parse_typescript(raw_output: str) -> DiagnosticParserResult:
    """Extract TypeScript compiler diagnostics from raw command output."""
    diagnostics: list[FailureDiagnostic] = []
    lines = raw_output.splitlines()
    # Pattern: src/file.ts:42:5 - error TS2345: Message
    ts_pattern = re.compile(
        r"^(.+?)\((\d+),\d+\):\s+error\s+(TS\d+):\s*(.+)$"
    )
    ts_pattern2 = re.compile(
        r"^(.+?):(\d+):(\d+)\s+-\s+error\s+(TS\d+):\s*(.+)$"
    )
    for i, line in enumerate(lines):
        m = ts_pattern.match(line)
        if m:
            diagnostics.append(
                FailureDiagnostic(
                    message=m.group(4).strip(),
                    code=m.group(3),
                    file_path=m.group(1).strip(),
                    line_number=int(m.group(2)),
                    severity="error",
                    parser_type=DiagnosticParserType.TYPESCRIPT,
                    parser_confidence=0.9,
                )
            )
            continue
        m = ts_pattern2.match(line)
        if m:
            diagnostics.append(
                FailureDiagnostic(
                    message=m.group(5).strip(),
                    code=m.group(4),
                    file_path=m.group(1).strip(),
                    line_number=int(m.group(2)),
                    column=int(m.group(3)),
                    severity="error",
                    parser_type=DiagnosticParserType.TYPESCRIPT,
                    parser_confidence=0.9,
                )
            )
    excerpt = "\n".join(lines[:20]) if diagnostics else None
    return DiagnosticParserResult(
        parser_type=DiagnosticParserType.TYPESCRIPT,
        confidence=0.9 if diagnostics else 0.0,
        diagnostics=diagnostics,
        raw_excerpt=excerpt,
    )


def _stub_parse_template(raw_output: str) -> DiagnosticParserResult:
    """Extract Angular template compilation errors."""
    diagnostics: list[FailureDiagnostic] = []
    lines = raw_output.splitlines()
    templ_pattern = re.compile(
        r"^(.*\.html):(\d+):(\d+)\s+-\s+error\s+(.+)$"
    )
    for i, line in enumerate(lines):
        m = templ_pattern.match(line)
        if m:
            diagnostics.append(
                FailureDiagnostic(
                    message=m.group(4).strip(),
                    file_path=m.group(1).strip(),
                    line_number=int(m.group(2)),
                    column=int(m.group(3)),
                    severity="error",
                    parser_type=DiagnosticParserType.TEMPLATE,
                    parser_confidence=0.85,
                )
            )
            continue
        if re.search(r"template\s+error|parse\s+error", line, re.IGNORECASE):
            diagnostics.append(
                FailureDiagnostic(
                    message=line.strip(),
                    line_number=i + 1,
                    severity="error",
                    parser_type=DiagnosticParserType.TEMPLATE,
                    parser_confidence=0.6,
                )
            )
    excerpt = "\n".join(lines[:20]) if diagnostics else None
    return DiagnosticParserResult(
        parser_type=DiagnosticParserType.TEMPLATE,
        confidence=0.85 if diagnostics else 0.0,
        diagnostics=diagnostics,
        raw_excerpt=excerpt,
    )


def _stub_parse_test(raw_output: str) -> DiagnosticParserResult:
    """Extract test failure diagnostics from test runner output."""
    diagnostics: list[FailureDiagnostic] = []
    lines = raw_output.splitlines()
    # FAIL <file>
    fail_pattern = re.compile(r"^FAIL\s+(.+\.spec\.ts)")
    # ● <test name>
    test_fail_pattern = re.compile(r"^\s*●\s+(.+)")
    for i, line in enumerate(lines):
        m = fail_pattern.match(line)
        if m:
            diagnostics.append(
                FailureDiagnostic(
                    message=line.strip(),
                    file_path=m.group(1).strip(),
                    line_number=i + 1,
                    severity="error",
                    parser_type=DiagnosticParserType.TEST,
                    parser_confidence=0.8,
                )
            )
            continue
        m = test_fail_pattern.match(line)
        if m:
            diagnostics.append(
                FailureDiagnostic(
                    message=f"Test failed: {m.group(1).strip()}",
                    line_number=i + 1,
                    severity="error",
                    parser_type=DiagnosticParserType.TEST,
                    parser_confidence=0.9,
                )
            )
    excerpt = "\n".join(lines[:20]) if diagnostics else None
    return DiagnosticParserResult(
        parser_type=DiagnosticParserType.TEST,
        confidence=0.85 if diagnostics else 0.0,
        diagnostics=diagnostics,
        raw_excerpt=excerpt,
    )


def _stub_parse_generic(raw_output: str) -> DiagnosticParserResult:
    """Fallback parser that flags lines containing common error keywords."""
    diagnostics: list[FailureDiagnostic] = []
    lines = raw_output.splitlines()
    error_keywords = re.compile(
        r"(error|failed|failure|exception|traceback|killed|segfault)",
        re.IGNORECASE,
    )
    for i, line in enumerate(lines):
        if error_keywords.search(line):
            diagnostics.append(
                FailureDiagnostic(
                    message=line.strip()[:1000],
                    line_number=i + 1,
                    severity="error",
                    parser_type=DiagnosticParserType.GENERIC,
                    parser_confidence=0.3,
                )
            )
    excerpt = "\n".join(lines[:20]) if diagnostics else None
    return DiagnosticParserResult(
        parser_type=DiagnosticParserType.GENERIC,
        confidence=0.3 if diagnostics else 0.0,
        diagnostics=diagnostics,
        raw_excerpt=excerpt,
    )


# ---------------------------------------------------------------------------
# Default parser registry with stub parsers
# ---------------------------------------------------------------------------

DEFAULT_PARSER_REGISTRY = ParserRegistry(
    {
        DiagnosticParserType.NPM: _stub_parse_npm,
        DiagnosticParserType.ANGULAR_CLI: _stub_parse_angular_cli,
        DiagnosticParserType.TYPESCRIPT: _stub_parse_typescript,
        DiagnosticParserType.TEMPLATE: _stub_parse_template,
        DiagnosticParserType.TEST: _stub_parse_test,
        DiagnosticParserType.GENERIC: _stub_parse_generic,
    }
)


# ---------------------------------------------------------------------------
# FailureEvidenceBuilder
# ---------------------------------------------------------------------------


class FailureEvidenceBuilderError(ValueError):
    """Raised when failure evidence construction fails a policy check."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class FailureEvidenceBuilder:
    """Compose failure evidence from raw command execution results.

    Accepts a ``FailureBuilderInput``, runs parsers, computes fingerprints,
    classifies origin via baseline comparison, registers artifacts through
    a supplied artifact store, and returns an immutable ``FailureEvidence``.
    """

    def __init__(
        self,
        *,
        parser_registry: ParserRegistry | None = None,
        fingerprint_service: FailureFingerprintService | None = None,
        origin_comparator: OriginComparator | None = None,
        artifact_store: Any | None = None,
        policy_skip_parsers: frozenset[DiagnosticParserType] | None = None,
    ) -> None:
        self._parser_registry = parser_registry or DEFAULT_PARSER_REGISTRY
        self._fingerprint_service = fingerprint_service or FailureFingerprintService()
        self._origin_comparator = origin_comparator or OriginComparator()
        self._artifact_store = artifact_store
        self._policy_skip_parsers = policy_skip_parsers or frozenset()
        self._results: dict[str, tuple[str, FailureEvidence]] = {}

    def build(self, input_data: FailureBuilderInput) -> FailureEvidence:
        """Produce an immutable FailureEvidence from builder input.

        Steps:
          1. Check idempotency
          2. Validate parser policy (no skipping)
          3. Run parsers
          4. Compute fingerprint
          5. Classify origin
          6. Register artifacts (best-effort)
          7. Return immutable model
        """
        key = input_data.idempotency_key
        existing = self._results.get(key)
        if existing:
            return existing[1].model_copy(update={"status": FailureStatus.FINALIZED})

        self._validate_parser_policy(input_data)

        raw_output = self._combine_output(input_data.stdout, input_data.stderr)
        parser_results = self._parser_registry.parse_all(raw_output)

        diagnostics = self._collect_diagnostics(parser_results)
        if not diagnostics:
            raise FailureEvidenceBuilderError(
                "NO_DIAGNOSTICS",
                "No diagnostics could be extracted from command output.",
                422,
            )

        fingerprint = self._fingerprint_service.compute(diagnostics)
        origin = self._origin_comparator.compare(
            diagnostics, input_data.baseline_artifact_ids
        )

        raw_log_artifacts = self._register_artifacts(
            input_data, raw_output, parser_results, diagnostics, origin
        )

        evidence = FailureEvidence(
            failure_id=self._new_failure_id(),
            run_id=input_data.run_id,
            stage_id=input_data.stage_id,
            execution_id=input_data.execution_id,
            failure_fingerprint=fingerprint,
            origin=origin,
            diagnostics=diagnostics,
            workspace_fingerprint=input_data.workspace_fingerprint,
            status=FailureStatus.FINALIZED,
            raw_log_artifacts=raw_log_artifacts,
        )
        self._results[key] = (input_data.model_dump_json(), evidence)
        return evidence

    def _validate_parser_policy(self, input_data: FailureBuilderInput) -> None:
        """Reject attempts to skip parsers via policy bypass."""
        if self._policy_skip_parsers:
            # Check whether the input signals a bypass intent (e.g. empty
            # stdout+stderr when parsers are expected to be skipped).
            if not input_data.stdout and not input_data.stderr:
                raise FailureEvidenceBuilderError(
                    "PARSER_SKIP_REJECTED",
                    "Policy requires parsers to run; cannot skip parser stage.",
                    422,
                )

    def _combine_output(self, stdout: str, stderr: str) -> str:
        parts: list[str] = []
        if stdout:
            parts.append(stdout)
        if stderr:
            if parts:
                parts.append("\n--- STDERR ---\n")
            parts.append(stderr)
        return "".join(parts)

    def _collect_diagnostics(
        self, parser_results: list[DiagnosticParserResult]
    ) -> list[FailureDiagnostic]:
        seen: set[str] = set()
        collected: list[FailureDiagnostic] = []
        for result in parser_results:
            for diag in result.diagnostics:
                dedup_key = (
                    f"{diag.message}|{diag.code}|{diag.file_path}|{diag.line_number}"
                )
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    collected.append(diag)
        return collected

    def _register_artifacts(
        self,
        input_data: FailureBuilderInput,
        raw_output: str,
        parser_results: list[DiagnosticParserResult],
        diagnostics: list[FailureDiagnostic],
        origin: FailureOrigin,
    ) -> list[ArtifactRefDto]:
        """Register diagnostic artifacts through the injected store.

        Returns whatever refs were successfully stored.  If the store is
        not configured or fails, returns an empty list so the evidence
        record is still produced (partial preservation).
        """
        if self._artifact_store is None:
            return []

        refs: list[ArtifactRefDto] = []
        try:
            stored = self._artifact_store.write_text_artifact(
                run_id=input_data.run_id,
                relative_path=f"05_failure_evidence/{input_data.execution_id}_raw_output.log",
                content=raw_output,
                artifact_type=ArtifactType.TEXT_LOG,
                stage_id=input_data.stage_id,
                created_by="failure-evidence-builder",
            )
            refs.append(stored.ref)
        except Exception:
            pass

        try:
            stored = self._artifact_store.write_text_artifact(
                run_id=input_data.run_id,
                relative_path=f"05_failure_evidence/{input_data.execution_id}_structured.json",
                content=json.dumps(
                    [d.model_dump(mode="json") for d in diagnostics],
                    indent=2,
                    sort_keys=True,
                ),
                artifact_type=ArtifactType.JSON,
                stage_id=input_data.stage_id,
                created_by="failure-evidence-builder",
            )
            refs.append(stored.ref)
        except Exception:
            pass

        try:
            stored = self._artifact_store.write_text_artifact(
                run_id=input_data.run_id,
                relative_path=f"05_failure_evidence/{input_data.execution_id}_parser_report.json",
                content=json.dumps(
                    [r.model_dump(mode="json") for r in parser_results],
                    indent=2,
                    sort_keys=True,
                ),
                artifact_type=ArtifactType.JSON,
                stage_id=input_data.stage_id,
                created_by="failure-evidence-builder",
            )
            refs.append(stored.ref)
        except Exception:
            pass

        try:
            stored = self._artifact_store.write_text_artifact(
                run_id=input_data.run_id,
                relative_path=f"05_failure_evidence/{input_data.execution_id}_normalized_diagnostics.json",
                content=json.dumps(
                    [d.model_dump(mode="json") for d in diagnostics],
                    indent=2,
                    sort_keys=True,
                ),
                artifact_type=ArtifactType.JSON,
                stage_id=input_data.stage_id,
                created_by="failure-evidence-builder",
            )
            refs.append(stored.ref)
        except Exception:
            pass

        try:
            stored = self._artifact_store.write_text_artifact(
                run_id=input_data.run_id,
                relative_path=f"05_failure_evidence/{input_data.execution_id}_origin_comparison.json",
                content=json.dumps(
                    {"origin": origin.value, "diagnostic_count": len(diagnostics)},
                    indent=2,
                ),
                artifact_type=ArtifactType.JSON,
                stage_id=input_data.stage_id,
                created_by="failure-evidence-builder",
            )
            refs.append(stored.ref)
        except Exception:
            pass

        return refs

    @staticmethod
    def _new_failure_id() -> str:
        return f"failure-{uuid4().hex}"
