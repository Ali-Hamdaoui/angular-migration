"""Tests for S4-F01-I01: FailureEvidenceBuilder, parsers, fingerprints, origin classification."""

from __future__ import annotations

import pytest

from app.domain.failure import (
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
from app.services.failure_evidence_builder import (
    DEFAULT_PARSER_REGISTRY,
    FailureEvidenceBuilder,
    FailureEvidenceBuilderError,
    _stub_parse_angular_cli,
    _stub_parse_generic,
    _stub_parse_npm,
    _stub_parse_template,
    _stub_parse_test,
    _stub_parse_typescript,
)


def _make_input(
    exit_code: int = 1,
    stdout: str = "",
    stderr: str = "error: something failed",
    *,
    run_id: str = "run-test-001",
    stage_id: str = "stage-18-to-19",
    execution_id: str = "exec-001",
    idempotency_key: str | None = None,
) -> FailureBuilderInput:
    return FailureBuilderInput(
        run_id=run_id,
        stage_id=stage_id,
        execution_id=execution_id,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        workspace_fingerprint="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        idempotency_key=idempotency_key or f"ik-{run_id}-{execution_id}",
    )


class TestFailureEvidenceBuilder:
    """Happy path and edge cases for the evidence builder."""

    def test_happy_path_npm_failure(self):
        """Valid command with npm error produces FailureEvidence with diagnostics."""
        input_data = _make_input(
            exit_code=1,
            stderr="npm ERR! Failed to install dependency\nnpm ERR! code ELIFECYCLE\n",
        )
        builder = FailureEvidenceBuilder()
        evidence = builder.build(input_data)

        assert evidence.failure_id.startswith("failure-")
        assert evidence.run_id == "run-test-001"
        assert evidence.stage_id == "stage-18-to-19"
        assert evidence.execution_id == "exec-001"
        assert evidence.failure_fingerprint.startswith("sha256:")
        assert evidence.origin in FailureOrigin
        assert len(evidence.diagnostics) >= 1
        assert evidence.status == FailureStatus.FINALIZED
        assert evidence.workspace_fingerprint.startswith("sha256:")

    def test_happy_path_typescript_error(self):
        """TypeScript compiler error produces typed diagnostics with file/line info."""
        input_data = _make_input(
            exit_code=2,
            stdout="src/app/component.ts(15,5): error TS2322: Type 'string' is not assignable to type 'number'\n",
        )
        builder = FailureEvidenceBuilder()
        evidence = builder.build(input_data)

        assert len(evidence.diagnostics) >= 1
        ts_diags = [d for d in evidence.diagnostics if d.parser_type == DiagnosticParserType.TYPESCRIPT]
        assert len(ts_diags) >= 1
        assert ts_diags[0].file_path is not None
        assert ts_diags[0].line_number is not None

    def test_rejects_no_output(self):
        """Builder rejects input with no exit_code and no output."""
        builder = FailureEvidenceBuilder()
        with pytest.raises(FailureEvidenceBuilderError):
            builder.build(_make_input(exit_code=0, stdout="", stderr="", idempotency_key="empty-test"))

    def test_origin_migration_caused_without_baseline(self):
        """Origin defaults to MIGRATION_CAUSED when no baseline artifacts are provided."""
        builder = FailureEvidenceBuilder()
        evidence = builder.build(_make_input(exit_code=1, stderr="fatal error"))
        assert evidence.origin == FailureOrigin.MIGRATION_CAUSED

    def test_multiple_parsers_are_tried(self):
        """All parsers in the registry are invoked and diagnostics aggregated."""
        builder = FailureEvidenceBuilder()
        evidence = builder.build(_make_input(
            exit_code=1,
            stdout="src/main.ts(5,1): error TS1005: ',' expected\n",
            stderr="npm ERR! code ELIFECYCLE\nError: Command failed\n",
        ))
        parser_types = {d.parser_type for d in evidence.diagnostics}
        assert DiagnosticParserType.TYPESCRIPT in parser_types
        assert DiagnosticParserType.NPM in parser_types

    def test_fingerprint_determinism(self):
        """Same input produces the same fingerprint."""
        builder = FailureEvidenceBuilder()
        input_data = _make_input(exit_code=1, stderr="npm ERR! failure")
        e1 = builder.build(input_data)
        e2 = builder.build(input_data)
        assert e1.failure_fingerprint == e2.failure_fingerprint

    def test_different_input_different_fingerprint(self):
        """Different stderr produces a different fingerprint."""
        builder = FailureEvidenceBuilder()
        e1 = builder.build(_make_input(exit_code=1, stderr="npm ERR! failure A\nnpm ERR! code E001\n", idempotency_key="test-diff-1"))
        e2 = builder.build(_make_input(exit_code=1, stderr="npm ERR! failure B\nnpm ERR! code E002\n", idempotency_key="test-diff-2"))
        assert e1.failure_fingerprint != e2.failure_fingerprint

    def test_idempotent_replay_returns_same_evidence(self):
        """Same idempotency key returns the same evidence."""
        builder = FailureEvidenceBuilder()
        ik = "idempotent-test-001"
        inp = _make_input(exit_code=1, stderr="npm ERR! fail", idempotency_key=ik)
        e1 = builder.build(inp)
        e2 = builder.build(inp)
        assert e1.failure_id == e2.failure_id
        assert e1.failure_fingerprint == e2.failure_fingerprint


class TestStubParsers:
    """Unit tests for individual stub parser implementations."""

    def test_npm_parser_detects_npm_err(self):
        result = _stub_parse_npm("npm ERR! code ELIFECYCLE\nnpm ERR! errno 1\n")
        assert len(result.diagnostics) >= 1
        for d in result.diagnostics:
            assert d.parser_type == DiagnosticParserType.NPM

    def test_angular_cli_parser_detects_build_error(self):
        result = _stub_parse_angular_cli("Error: The Angular compiler requires TypeScript")
        assert len(result.diagnostics) >= 1

    def test_angular_cli_parser_detects_unhandled(self):
        result = _stub_parse_angular_cli("An unhandled exception occurred: Something broke")
        assert len(result.diagnostics) >= 1

    def test_typescript_parser_detects_ts_error(self):
        result = _stub_parse_typescript("src/app.ts(10,3): error TS2345: Argument type issue\n")
        assert len(result.diagnostics) >= 1
        assert result.diagnostics[0].file_path == "src/app.ts"
        assert result.diagnostics[0].line_number == 10

    def test_typescript_parser_no_match(self):
        result = _stub_parse_typescript("some random output\n")
        assert len(result.diagnostics) == 0

    def test_template_parser_detects_html_error(self):
        result = _stub_parse_template("src/app.html:42:5 - error Unexpected closing tag\n")
        assert len(result.diagnostics) >= 1
        assert result.diagnostics[0].file_path is not None

    def test_template_parser_parse_error_keyword(self):
        result = _stub_parse_template("Template parse error: Something broke\n")
        assert len(result.diagnostics) >= 1

    def test_test_parser_detects_fail(self):
        result = _stub_parse_test("FAIL src/app.spec.ts\n")
        assert len(result.diagnostics) >= 1

    def test_test_parser_detects_test_failure(self):
        result = _stub_parse_test("  ● MyComponent › should render\n")
        assert len(result.diagnostics) >= 1

    def test_generic_parser_fallback(self):
        result = _stub_parse_generic("some random error occurred\nanother failure\n")
        assert len(result.diagnostics) >= 1

    def test_generic_parser_skips_clean_output(self):
        result = _stub_parse_generic("everything is fine\nno problems here\n")
        assert len(result.diagnostics) == 0


class TestFailureFingerprintService:
    """Fingerprint determinism and collision resistance."""

    def test_deterministic_fingerprint(self):
        diags = [
            FailureDiagnostic(
                parser_type=DiagnosticParserType.NPM,
                parser_confidence=0.9,
                message="npm ERR! failure",
                severity="error",
            ),
        ]
        fp1 = FailureFingerprintService.compute(diags)
        fp2 = FailureFingerprintService.compute(diags)
        assert fp1 == fp2
        assert fp1.startswith("sha256:")

    def test_different_diagnostics_different_fingerprints(self):
        d1 = [
            FailureDiagnostic(
                parser_type=DiagnosticParserType.NPM,
                parser_confidence=0.9,
                message="error A",
                severity="error",
            ),
        ]
        d2 = [
            FailureDiagnostic(
                parser_type=DiagnosticParserType.TYPESCRIPT,
                parser_confidence=0.9,
                message="error B",
                severity="error",
            ),
        ]
        assert FailureFingerprintService.compute(d1) != FailureFingerprintService.compute(d2)


class TestOriginComparator:
    """Failure origin classification logic."""

    def test_migration_caused_no_baseline_ids(self):
        oc = OriginComparator()
        result = oc.compare([FailureDiagnostic(
            parser_type=DiagnosticParserType.NPM,
            parser_confidence=0.9,
            message="new error",
            severity="error",
        )], [])
        assert result == FailureOrigin.MIGRATION_CAUSED

    def test_migration_caused_with_baseline_reader_returning_empty(self):
        oc = OriginComparator(baseline_diagnostics_reader=lambda id: [])
        result = oc.compare([FailureDiagnostic(
            parser_type=DiagnosticParserType.NPM,
            parser_confidence=0.9,
            message="new error",
            severity="error",
        )], ["artifact-1"])
        assert result == FailureOrigin.MIGRATION_CAUSED

    def test_pre_existing_unchanged(self):
        d = FailureDiagnostic(
            parser_type=DiagnosticParserType.NPM,
            parser_confidence=0.9,
            message="npm ERR! known fail",
            severity="error",
        )
        oc = OriginComparator(baseline_diagnostics_reader=lambda id: [d])
        assert oc.compare([d], ["artifact-1"]) == FailureOrigin.PRE_EXISTING_UNCHANGED

    def test_pre_existing_changed(self):
        old = FailureDiagnostic(
            parser_type=DiagnosticParserType.NPM,
            parser_confidence=0.9,
            message="old error",
            severity="error",
        )
        new = FailureDiagnostic(
            parser_type=DiagnosticParserType.TYPESCRIPT,
            parser_confidence=0.9,
            message="new error",
            severity="error",
        )
        oc = OriginComparator(baseline_diagnostics_reader=lambda id: [old])
        assert oc.compare([new, old], ["artifact-1"]) == FailureOrigin.PRE_EXISTING_CHANGED


class TestParserRegistry:
    """ParserRegistry as a dict subclass."""

    def test_default_registry_has_all_parsers(self):
        assert DiagnosticParserType.NPM in DEFAULT_PARSER_REGISTRY
        assert DiagnosticParserType.ANGULAR_CLI in DEFAULT_PARSER_REGISTRY
        assert DiagnosticParserType.TYPESCRIPT in DEFAULT_PARSER_REGISTRY
        assert DiagnosticParserType.TEMPLATE in DEFAULT_PARSER_REGISTRY
        assert DiagnosticParserType.TEST in DEFAULT_PARSER_REGISTRY
        assert DiagnosticParserType.GENERIC in DEFAULT_PARSER_REGISTRY

    def test_parse_all_returns_results(self):
        results = DEFAULT_PARSER_REGISTRY.parse_all("npm ERR! code 1\n")
        assert len(results) == len(DEFAULT_PARSER_REGISTRY)

    def test_register_adds_parser(self):
        registry: ParserRegistry = ParserRegistry()
        registry.register(DiagnosticParserType.NPM, _stub_parse_npm)
        assert DiagnosticParserType.NPM in registry
        result = registry.parse_all("npm ERR! test")
        assert len(result) == 1

    def test_custom_registry_can_be_injected(self):
        custom = ParserRegistry()
        custom.register(DiagnosticParserType.GENERIC, lambda output: __import__(
            "app.domain.failure"
        ).domain.failure.DiagnosticParserResult(
            parser_type=DiagnosticParserType.GENERIC,
            confidence=1.0,
            diagnostics=[
                FailureDiagnostic(
                    parser_type=DiagnosticParserType.GENERIC,
                    parser_confidence=1.0,
                    message="custom parser invoked",
                    severity="error",
                )
            ],
        ))
        builder = FailureEvidenceBuilder(parser_registry=custom)
        evidence = builder.build(_make_input(exit_code=1, stderr="custom error"))
        assert any("custom parser invoked" in d.message for d in evidence.diagnostics)
