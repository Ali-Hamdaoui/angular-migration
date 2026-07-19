"""Tests for PatchSafetyService, PatchApplyService, and unified diff parsing.

Covers S4-F07: patch validation loop — safety checks, dry-run, apply, ledger.
Uses fakes / mocks exclusively — no real database or filesystem I/O.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.domain.patch import (
    DryRunResult,
    ParsedDiff,
    PatchApplyResult,
    PatchApplyStatus,
    PatchLedgerEntry,
    PatchSafetyReport,
    SafetyCheck,
    SafetyCheckResult,
    SafetyCheckType,
    parse_unified_diff,
    PrePostFingerprint,
)
from app.services.patch_apply_service import (
    PatchApplyService,
    PatchSafetyService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_DIFF = (
    "--- a/src/app/main.py\n"
    "+++ b/src/app/main.py\n"
    "@@ -10,7 +10,8 @@\n"
    " from flask import Flask\n"
    " import os\n"
    "-\n"
    "+import sys\n"
    "+\n"
    " app = Flask(__name__)\n"
    "@@ -30,6 +31,9 @@\n"
    " def index():\n"
    "     return 'hello'\n"
    "+\n"
    "+def health():\n"
    "+    return 'ok'\n"
    "+\n"
)


def sha256_hex(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


SAMPLE_CHECKSUM = sha256_hex(SAMPLE_DIFF)
SAMPLE_FINGERPRINT = "fp-workspace-v3"
SAMPLE_WORKSPACE_FINGERPRINT = "fp-workspace-v3"
SAMPLE_STATE_VERSION = 7
SAMPLE_PLAN_VERSION = "plan-v2"
SAMPLE_RUN_ID = "run-test-001"
SAMPLE_PROPOSAL_ID = "prop-angular-18-to-19-3"
SAMPLE_PATCH_APPLY_ID = "apply-001"


def make_safety_service(
    allowed_scope: tuple[str, ...] | None = None,
    forbidden_patterns=None,
    high_risk_patterns=None,
) -> PatchSafetyService:
    return PatchSafetyService(
        allowed_scope_prefixes=allowed_scope
            or ("src/", "projects/", "libs/", "apps/", "test/", "tests/"),
        forbidden_patterns=forbidden_patterns,
        high_risk_patterns=high_risk_patterns,
    )


# ===================================================================
# parse_unified_diff — unit tests for the standalone utility
# ===================================================================


class TestParseUnifiedDiff:
    """Validate the unified-diff parsing utility."""

    def test_valid_diff_returns_parsed_structure(self) -> None:
        parsed = parse_unified_diff(SAMPLE_DIFF)
        assert parsed is not None
        assert isinstance(parsed, ParsedDiff)
        assert parsed.source_path == "src/app/main.py"
        assert parsed.target_path == "src/app/main.py"
        assert len(parsed.hunks) == 2
        assert parsed.checksum == SAMPLE_CHECKSUM
        assert parsed.raw_diff == SAMPLE_DIFF

    def test_parsed_hunk_metadata(self) -> None:
        parsed = parse_unified_diff(SAMPLE_DIFF)
        assert parsed is not None
        hunk0 = parsed.hunks[0]
        assert hunk0.original_start == 10
        assert hunk0.original_count == 7
        assert hunk0.new_start == 10
        assert hunk0.new_count == 8
        assert "from flask" in hunk0.lines[0]
        assert "import os" in hunk0.lines[1]

    def test_parsed_hunk_lines_preserve_diff_prefixes(self) -> None:
        """Lines inside hunks keep their leading +/-/space diff markers."""
        parsed = parse_unified_diff(SAMPLE_DIFF)
        assert parsed is not None
        hunk0_lines = [l.rstrip("\n") for l in parsed.hunks[0].lines]
        assert "+import sys" in hunk0_lines
        assert " from flask import Flask" in hunk0_lines
        assert "-" in hunk0_lines

    def test_empty_diff_returns_none(self) -> None:
        assert parse_unified_diff("") is None

    def test_non_empty_no_markers_still_parses(self) -> None:
        """Plain text without ---/+++/@@ markers yields a parsed structure
        because the parser is lenient — non-marker lines become hunk content."""
        parsed = parse_unified_diff("this is not a diff\n")
        assert parsed is not None
        assert parsed.source_path == ""
        assert parsed.target_path == ""

    def test_diff_with_only_headers_returns_zero_hunks(self) -> None:
        content = "--- a/file.py\n+++ b/file.py\n"
        parsed = parse_unified_diff(content)
        assert parsed is not None
        assert len(parsed.hunks) == 0

    def test_diff_with_new_file_source(self) -> None:
        diff = (
            "--- /dev/null\n"
            "+++ b/src/app/new.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+import os\n"
            "+import sys\n"
            "+print('hello')\n"
        )
        parsed = parse_unified_diff(diff)
        assert parsed is not None
        assert parsed.source_path == "/dev/null"
        # b/ prefix is stripped by the parser
        assert parsed.target_path == "src/app/new.py"

    def test_diff_checksum_is_deterministic(self) -> None:
        assert parse_unified_diff(SAMPLE_DIFF).checksum == SAMPLE_CHECKSUM  # type: ignore[union-attr]


# ===================================================================
# PatchSafetyService — unit tests
# ===================================================================


class TestPatchSafetyService:
    """Safety-check behaviour in isolation."""

    def test_happy_path_all_checks_pass(self) -> None:
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )

        assert isinstance(report, PatchSafetyReport)
        assert report.overall_result == SafetyCheckResult.PASS
        assert report.patch_apply_id == SAMPLE_PATCH_APPLY_ID
        assert report.checksum_match is True
        assert report.fingerprint_match is True
        assert report.state_version_match is True
        assert report.plan_version_match is True
        assert report.path_confinement_pass is True
        assert report.symlink_escape_check_pass is True
        assert report.diff_syntax_valid is True
        assert report.changed_file_scope_valid is True
        assert report.high_risk_scope_check_pass is True
        assert report.idempotency_match is False
        assert report.line_ending_warning == ""
        assert report.path_traversal_check_pass is True

    def test_checksum_mismatch_fails(self) -> None:
        svc = make_safety_service()
        wrong_checksum = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=wrong_checksum,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.checksum_match is False
        assert report.fingerprint_match is True
        checksum_check = next(
            c for c in report.checks if c.check_type == SafetyCheckType.CHECKSUM
        )
        assert checksum_check.result == SafetyCheckResult.FAIL

    def test_fingerprint_mismatch_fails(self) -> None:
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint="fp-different",
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.fingerprint_match is False
        assert report.checksum_match is True

    def test_state_version_mismatch_fails(self) -> None:
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION + 5,  # stale
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.state_version_match is False

    def test_plan_version_mismatch_fails(self) -> None:
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version="plan-v1-different",
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.plan_version_match is False

    def test_unparseable_diff_returns_immediate_failure(self) -> None:
        """Empty diff content triggers early return with diff_syntax_valid=False."""
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content="",
            expected_checksum=sha256_hex(""),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.diff_syntax_valid is False
        # Checks that ran before diff parsing still reflect:
        assert report.checksum_match is True

    def test_empty_diff_content_is_rejected(self) -> None:
        svc = make_safety_service()
        empty_checksum = sha256_hex("")
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content="",
            expected_checksum=empty_checksum,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.diff_syntax_valid is False

    # -- Path confinement ----------------------------------------------------

    def test_path_confinement_rejects_dot_env(self) -> None:
        diff = (
            "--- .env\n"
            "+++ .env\n"
            "@@ -1,1 +1,1 @@\n"
            " SECRET_KEY=old\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.path_confinement_pass is False

    def test_path_confinement_rejects_node_modules(self) -> None:
        diff = (
            "--- a/src/main.js\n"
            "+++ node_modules/foo/index.js\n"
            "@@ -1,1 +1,1 @@\n"
            " var x = 1;\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.path_confinement_pass is False

    def test_path_confinement_rejects_git_dir(self) -> None:
        diff = (
            "--- a/src/main.js\n"
            "+++ .git/config\n"
            "@@ -1,1 +1,1 @@\n"
            " [core]\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.path_confinement_pass is False

    def test_path_confinement_rejects_tilde(self) -> None:
        diff = (
            "--- a/src/main.js\n"
            "+++ ~/ssh/config\n"
            "@@ -1,1 +1,1 @@\n"
            " Host *\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.path_confinement_pass is False

    def test_path_confinement_accepts_allowed_scope(self) -> None:
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.changed_file_scope_valid is True

    def test_changed_file_scope_rejects_outside_allowed(self) -> None:
        """Paths outside allowed scope are rejected when they don't use
        a/ b/ diff prefix (which would bypass scope check)."""
        diff = (
            "--- random/outside/file.txt\n"
            "+++ random/outside/file.txt\n"
            "@@ -1,1 +1,1 @@\n"
            " content\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.changed_file_scope_valid is False

    # -- Symlink escape ------------------------------------------------------

    def test_symlink_escape_detected(self) -> None:
        diff = (
            "--- a/src/app/main.py\n"
            "+++ src/../outside/file.py\n"
            "@@ -1,1 +1,1 @@\n"
            " malicious\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.symlink_escape_check_pass is False

    def test_symlink_escape_detected_on_start_with_dotdot(self) -> None:
        diff = (
            "--- ../etc/passwd\n"
            "+++ ../etc/shadow\n"
            "@@ -1,1 +1,1 @@\n"
            " root:x:0:0:root:/root:/bin/bash\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.symlink_escape_check_pass is False

    # -- Path traversal ------------------------------------------------------

    def test_path_traversal_detected(self) -> None:
        traversal_diff = (
            "--- ../../etc/passwd\n"
            "+++ ../../etc/passwd\n"
            "@@ -1,1 +1,1 @@\n"
            " root:x:0:0\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=traversal_diff,
            expected_checksum=sha256_hex(traversal_diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.path_traversal_check_pass is False

    # -- Idempotency ---------------------------------------------------------

    def test_idempotency_match_detected(self) -> None:
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
            previous_idempotency_match=True,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.idempotency_match is True
        idem_check = next(
            c for c in report.checks if c.check_type == SafetyCheckType.IDEMPOTENCY
        )
        assert idem_check.result == SafetyCheckResult.FAIL

    # -- High-risk scope -----------------------------------------------------

    def test_high_risk_scope_detected_for_env(self) -> None:
        diff = (
            "--- a/src/app/.env.production\n"
            "+++ a/src/app/.env.production\n"
            "@@ -1,1 +1,1 @@\n"
            " SECRET=old\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        high_risk_check = next(
            c
            for c in report.checks
            if c.check_type == SafetyCheckType.HIGH_RISK_SCOPE
        )
        assert high_risk_check.result == SafetyCheckResult.FAIL
        assert report.high_risk_scope_check_pass is False

    def test_high_risk_scope_detected_for_dockerfile(self) -> None:
        diff = (
            "--- a/src/Dockerfile\n"
            "+++ a/src/Dockerfile\n"
            "@@ -1,1 +1,1 @@\n"
            " FROM ubuntu:latest\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        high_risk_check = next(
            c
            for c in report.checks
            if c.check_type == SafetyCheckType.HIGH_RISK_SCOPE
        )
        assert high_risk_check.result == SafetyCheckResult.FAIL
        assert report.high_risk_scope_check_pass is False

    # -- Line endings --------------------------------------------------------

    def test_line_ending_no_warning_for_lf_only(self) -> None:
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        # SAMPLE_DIFF is LF-only → no warning
        assert report.line_ending_warning == ""

    def test_line_ending_no_warning_for_crlf_only(self) -> None:
        diff_crlf = (
            "--- a/src/app/main.py\r\n"
            "+++ a/src/app/main.py\r\n"
            "@@ -1,1 +1,1 @@\r\n"
            " content\r\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff_crlf,
            expected_checksum=sha256_hex(diff_crlf),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        # CRLF-only: has_crlf=True, has_lf_only=False → no warning
        assert report.line_ending_warning == ""

    def test_unified_diff_syntax_check_present(self) -> None:
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        syntax_check = next(
            c
            for c in report.checks
            if c.check_type == SafetyCheckType.UNIFIED_DIFF_SYNTAX
        )
        assert syntax_check.result == SafetyCheckResult.PASS
        assert "2 hunk" in syntax_check.detail


# ===================================================================
# Dry-run tests
# ===================================================================


class TestDryRun:
    """PatchSafetyService.run_dry_run behaviour."""

    def test_dry_run_returns_applicable_with_file_targets(self) -> None:
        svc = make_safety_service()
        result = svc.run_dry_run(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            diff_content=SAMPLE_DIFF,
        )
        assert isinstance(result, DryRunResult)
        assert result.applicable is True
        assert "src/app/main.py" in result.target_files
        assert result.errors == ()
        assert result.estimated_additions > 0
        assert result.estimated_removals > 0

    def test_dry_run_unparseable_diff_returns_not_applicable(self) -> None:
        svc = make_safety_service()
        result = svc.run_dry_run(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            diff_content="",
        )
        assert result.applicable is False
        assert len(result.errors) > 0
        assert "Could not parse" in result.errors[0]

    def test_dry_run_estimates_additions_and_removals(self) -> None:
        svc = make_safety_service()
        result = svc.run_dry_run(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            diff_content=SAMPLE_DIFF,
        )
        # hunk0: 1 removal (-), 2 additions (+import sys, +)
        # hunk1: 4 additions (+, +def health, +return 'ok', +)
        assert result.estimated_additions == 6
        assert result.estimated_removals == 1

    def test_dry_run_with_new_file_source_only(self) -> None:
        diff = (
            "--- /dev/null\n"
            "+++ b/src/app/new_file.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+line1\n"
            "+line2\n"
            "+line3\n"
        )
        svc = make_safety_service()
        result = svc.run_dry_run(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            diff_content=diff,
        )
        assert result.applicable is True
        # /dev/null is included as source, b/ prefix is stripped from target
        assert "src/app/new_file.py" in result.target_files
        assert "/dev/null" in result.target_files


class TestDryRunWithWorkspaceRoot:
    """Dry-run behaviour when a workspace_root path is provided."""

    def test_non_existent_file_warning(self, tmp_path: Path) -> None:
        svc = make_safety_service()
        result = svc.run_dry_run(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            diff_content=SAMPLE_DIFF,
            workspace_root=str(tmp_path / "workspace"),
        )
        # The target files don't exist in the fake workspace
        warnings = result.warnings
        assert any("does not exist" in w for w in warnings)

    def test_existing_file_no_warning(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True)
        # SAMPLE_DIFF targets src/app/main.py (a/ and b/ stripped by parser)
        target = workspace / "src/app/main.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("existing content")
        svc = make_safety_service()
        result = svc.run_dry_run(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            diff_content=SAMPLE_DIFF,
            workspace_root=str(workspace),
        )
        assert result.applicable is True
        file_warnings = [w for w in result.warnings if "does not exist" in w]
        assert len(file_warnings) == 0

    def test_workspace_root_ignores_leading_slash(self, tmp_path: Path) -> None:
        """Paths with leading slash are joined cleanly with workspace_root
        (the lstrip in the service handles it)."""
        diff = (
            "--- /src/app/main.py\n"
            "+++ /src/app/main.py\n"
            "@@ -1,1 +1,1 @@\n"
            " content\n"
        )
        svc = make_safety_service()
        result = svc.run_dry_run(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            diff_content=diff,
            workspace_root=str(tmp_path),
        )
        # Should not crash
        assert result.applicable is True


# ===================================================================
# PatchApplyService — integration-style tests
# ===================================================================


class TestPatchApplyService:
    """Full apply_patch flow end-to-end through PatchApplyService."""

    def test_happy_path_returns_applied_with_ledger(self) -> None:
        svc = PatchApplyService()
        result = svc.apply_patch(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
            idempotency_key="idem-001",
            actor="test-runner",
        )

        assert isinstance(result, PatchApplyResult)
        assert result.status == PatchApplyStatus.APPLIED
        assert result.state_version == SAMPLE_STATE_VERSION + 1
        assert result.safety_report is not None
        assert result.safety_report.overall_result == SafetyCheckResult.PASS
        assert result.dry_run is not None
        assert result.dry_run.applicable is True
        # Ledger
        assert result.ledger is not None
        assert isinstance(result.ledger, PatchLedgerEntry)
        assert result.ledger.patch_apply_id == SAMPLE_PATCH_APPLY_ID
        assert result.ledger.proposal_id == SAMPLE_PROPOSAL_ID
        assert result.ledger.run_id == SAMPLE_RUN_ID
        assert result.ledger.checksum_before == SAMPLE_CHECKSUM
        assert result.ledger.fingerprint_before == SAMPLE_WORKSPACE_FINGERPRINT
        assert result.ledger.state_version == SAMPLE_STATE_VERSION + 1
        assert result.ledger.idempotency_key == "idem-001"
        assert result.ledger.actor == "test-runner"
        # Fingerprints
        assert result.fingerprints is not None
        assert isinstance(result.fingerprints, PrePostFingerprint)
        assert result.fingerprints.before == SAMPLE_WORKSPACE_FINGERPRINT
        assert result.fingerprints.after != SAMPLE_WORKSPACE_FINGERPRINT
        # Artifact refs
        assert "safety_report" in result.artifact_refs
        assert "dry_run" in result.artifact_refs
        assert "ledger" in result.artifact_refs
        assert "fingerprint_before" in result.artifact_refs
        assert "fingerprint_after" in result.artifact_refs
        # Not idempotent replay
        assert result.idempotent_replay is False

    def test_stale_state_version_returns_stale_status(self) -> None:
        svc = PatchApplyService()
        result = svc.apply_patch(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION + 3,  # stale
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert result.status == PatchApplyStatus.STALE
        assert result.safety_report is not None
        assert result.safety_report.state_version_match is False
        assert result.failure_evidence is not None
        assert "state_version" in result.failure_evidence.get("failed_checks", [])

    def test_unsafe_checksum_returns_unsafe_status(self) -> None:
        svc = PatchApplyService()
        wrong_checksum = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        result = svc.apply_patch(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=wrong_checksum,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert result.status == PatchApplyStatus.UNSAFE
        assert result.safety_report is not None
        assert result.safety_report.checksum_match is False
        assert result.failure_evidence is not None

    def test_unsafe_fingerprint_returns_unsafe_status(self) -> None:
        svc = PatchApplyService()
        result = svc.apply_patch(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint="fp-wrong",
        )
        assert result.status == PatchApplyStatus.UNSAFE
        assert result.safety_report is not None
        assert result.safety_report.fingerprint_match is False

    def test_malformed_diff_returns_unsafe_status(self) -> None:
        """A non-parseable diff (empty) should yield UNSAFE via the
        safety service's early return."""
        svc = PatchApplyService()
        result = svc.apply_patch(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content="",
            expected_checksum=sha256_hex(""),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert result.status == PatchApplyStatus.UNSAFE
        assert result.safety_report is not None
        assert result.safety_report.diff_syntax_valid is False

    def test_idempotency_rejection_through_apply(self) -> None:
        """When previous_idempotency_match is True, apply_patch propagates
        the idempotency check failure as UNSAFE."""
        svc = PatchApplyService()
        result = svc.apply_patch(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
            previous_idempotency_match=True,
        )
        assert result.status == PatchApplyStatus.UNSAFE
        assert result.safety_report is not None
        assert result.safety_report.idempotency_match is True

    def test_plan_version_mismatch_returns_unsafe(self) -> None:
        svc = PatchApplyService()
        result = svc.apply_patch(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version="plan-v1-different",
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert result.status == PatchApplyStatus.UNSAFE
        assert result.safety_report is not None
        assert result.safety_report.plan_version_match is False

    def test_get_apply_result_returns_previous_result(self) -> None:
        svc = PatchApplyService()
        previous = PatchApplyResult(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            status=PatchApplyStatus.APPLIED,
            state_version=8,
        )
        retrieved = svc.get_apply_result(
            SAMPLE_PATCH_APPLY_ID,
            previous_result=previous,
        )
        assert retrieved is not None
        assert retrieved.patch_apply_id == SAMPLE_PATCH_APPLY_ID
        assert retrieved.status == PatchApplyStatus.APPLIED


# ===================================================================
# Safety report structure
# ===================================================================


class TestSafetyReportStructure:
    """Structural validation of PatchSafetyReport content."""

    def test_check_list_contains_all_checks(self) -> None:
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        check_types = {c.check_type for c in report.checks}
        expected_types = {
            SafetyCheckType.CHECKSUM,
            SafetyCheckType.FINGERPRINT,
            SafetyCheckType.STATE_VERSION,
            SafetyCheckType.PLAN_VERSION,
            SafetyCheckType.UNIFIED_DIFF_SYNTAX,
            SafetyCheckType.PATH_CONFINEMENT,
            SafetyCheckType.SYMLINK_ESCAPE,
            SafetyCheckType.PATH_TRAVERSAL,
            SafetyCheckType.CHANGED_FILE_SCOPE,
            SafetyCheckType.HIGH_RISK_SCOPE,
            SafetyCheckType.IDEMPOTENCY,
        }
        assert expected_types.issubset(check_types)

    def test_report_details_contains_parsed_info(self) -> None:
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert "parsed_hunks" in report.details
        assert report.details["parsed_hunks"] == 2
        assert "source_path" in report.details
        # a/ prefix is stripped by parse_unified_diff
        assert report.details["source_path"] == "src/app/main.py"

    def test_report_has_timestamp(self) -> None:
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.generated_at is not None


# ===================================================================
# Rejection priority: STALE takes precedence over UNSAFE
# ===================================================================


class TestRejectionPriority:
    """When multiple checks fail, STALE status takes priority over UNSAFE
    because a stale proposal cannot be safely applied regardless of other issues."""

    def test_both_stale_and_unsafe_returns_stale(self) -> None:
        svc = PatchApplyService()
        # Both state version mismatch (would be stale) and fingerprint
        # mismatch (would be unsafe) → STALE wins
        result = svc.apply_patch(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION + 3,  # stale
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint="fp-wrong",  # also unsafe
        )
        assert result.status == PatchApplyStatus.STALE

    def test_injected_safety_service(self) -> None:
        """Verify a custom safety service can be injected into PatchApplyService."""
        custom_safety = PatchSafetyService(
            allowed_scope_prefixes=("custom/",),
        )
        svc = PatchApplyService(safety_service=custom_safety)
        assert svc._safety is custom_safety


# ===================================================================
# Adversarial cases — G07 patch-security hardening
# ===================================================================


class TestAdversarialPatchSecurity:
    """Adversarial test cases for patch-security hardening (G07)."""

    def test_absolute_etc_passwd_rejected(self) -> None:
        """Diff targeting /etc/passwd must be rejected by path confinement."""
        diff = (
            "--- a/src/app/main.py\n"
            "+++ /etc/passwd\n"
            "@@ -1,1 +1,1 @@\n"
            " root:x:0:0\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.path_confinement_pass is False

    def test_absolute_etc_shadow_rejected(self) -> None:
        """Diff targeting /etc/shadow must be rejected by path confinement."""
        diff = (
            "--- /etc/shadow\n"
            "+++ /etc/shadow\n"
            "@@ -1,1 +1,1 @@\n"
            " root:!:19999\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.path_confinement_pass is False

    def test_windows_absolute_path_rejected(self) -> None:
        """Diff targeting C:\\Windows\\system32 must be rejected."""
        diff = (
            "--- a/src/app/main.py\n"
            "+++ C:\\Windows\\system32\\drivers\\etc\\hosts\n"
            "@@ -1,1 +1,1 @@\n"
            " 127.0.0.1 localhost\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.path_confinement_pass is False

    def test_windows_drive_letter_rejected(self) -> None:
        """Diff targeting D:\\config.ini must be rejected."""
        diff = (
            "--- a/src/app/main.py\n"
            "+++ D:\\config.ini\n"
            "@@ -1,1 +1,1 @@\n"
            " setting=true\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.path_confinement_pass is False

    def test_windows_backslash_traversal_rejected(self) -> None:
        """Diff using \\..\\..\\etc\\passwd must be rejected by confinement."""
        diff = (
            "--- a/src/app/main.py\n"
            "+++ ..\\..\\etc\\passwd\n"
            "@@ -1,1 +1,1 @@\n"
            " root:x:0:0\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.path_confinement_pass is False

    def test_malformed_diff_null_bytes_rejected(self) -> None:
        """Diff with embedded null bytes must be rejected (unparseable)."""
        diff = "--- a/x\n+++ b/x\n@@ -1,1 +1,1 @@\nold\n\x00new\n"
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.diff_syntax_valid is False

    def test_malformed_diff_corrupt_hunk_header_rejected(self) -> None:
        """Diff with corrupt @@ line (non-numeric range) must be rejected."""
        diff = (
            "--- a/src/app/main.py\n"
            "+++ b/src/app/main.py\n"
            "@@ -abc,xyz +def,ghi @@\n"
            " content\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.diff_syntax_valid is False

    def test_malformed_diff_missing_range_rejected(self) -> None:
        """Diff with @@ line missing second range must be rejected."""
        diff = (
            "--- a/src/app/main.py\n"
            "+++ b/src/app/main.py\n"
            "@@ -1,3 @@\n"
            " content\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.diff_syntax_valid is False

    def test_malformed_diff_empty_hunk_parses(self) -> None:
        """Diff with @@ line but no hunk body must not crash."""
        diff = (
            "--- a/src/app/main.py\n"
            "+++ b/src/app/main.py\n"
            "@@ -1,3 +1,3 @@\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.diff_syntax_valid is True
        assert report.changed_file_scope_valid is True

    def test_path_traversal_through_symlink_rejected(self) -> None:
        """Diff with /../ traversal must be rejected."""
        diff = (
            "--- a/src/app/main.py\n"
            "+++ src/app/main.py/../../../etc/passwd\n"
            "@@ -1,1 +1,1 @@\n"
            " root:x:0:0\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.symlink_escape_check_pass is False or report.path_traversal_check_pass is False

    def test_crlf_mixed_endings_warning(self) -> None:
        """Diff with mixed CRLF and LF line endings should produce a warning."""
        diff = (
            "--- a/src/app/main.py\r\n"
            "+++ b/src/app/main.py\n"
            "@@ -1,1 +1,1 @@\r\n"
            " content\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.line_ending_warning != ""
        assert "Mixed line endings" in report.line_ending_warning

    def test_malformed_diff_negative_line_numbers_rejected(self) -> None:
        """Diff with malformed negative line numbers must not crash."""
        diff = (
            "--- a/src/app/main.py\n"
            "+++ b/src/app/main.py\n"
            "@@ -,- +1,1 @@\n"
            " content\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.diff_syntax_valid is False

    def test_ledger_entry_checksum_is_computed(self) -> None:
        """Ledger entry should have a non-empty entry_checksum."""
        svc = PatchApplyService()
        result = svc.apply_patch(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
            idempotency_key="idem-adversarial-001",
            actor="adversarial-test",
        )
        assert result.ledger is not None
        assert result.ledger.entry_checksum != ""
        assert result.ledger.entry_checksum.startswith("sha256:")
        assert result.ledger.checksum_before == SAMPLE_CHECKSUM
        assert result.ledger.state_version == SAMPLE_STATE_VERSION + 1

    def test_ledger_checksum_before_matches_expected(self) -> None:
        """Ledger checksum_before should match expected checksum."""
        svc = PatchApplyService()
        result = svc.apply_patch(
            patch_apply_id="apply-det-001",
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=SAMPLE_DIFF,
            expected_checksum=SAMPLE_CHECKSUM,
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
            idempotency_key="idem-det-001",
            actor="test",
        )
        assert result.ledger is not None
        assert result.ledger.checksum_before == SAMPLE_CHECKSUM
        assert result.ledger.actor == "test"
        assert result.ledger.idempotency_key == "idem-det-001"

    def test_symlink_escape_via_windows_backslash(self) -> None:
        """Symlink escape using Windows backslash must be detected."""
        diff = (
            "--- a/src/app/main.py\n"
            "+++ src\\..\\..\\etc\\passwd\n"
            "@@ -1,1 +1,1 @@\n"
            " root:x:0:0\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        assert report.symlink_escape_check_pass is False

    def test_windows_traversal_via_backslash_path_traversal(self) -> None:
        """Windows backslash traversal detected by path_traversal check."""
        diff = (
            "--- a/src/app/main.py\n"
            "+++ src\\..\\..\\etc\\shadow\n"
            "@@ -1,1 +1,1 @@\n"
            " root:!:19999\n"
        )
        svc = make_safety_service()
        report = svc.run_safety_checks(
            patch_apply_id=SAMPLE_PATCH_APPLY_ID,
            proposal_id=SAMPLE_PROPOSAL_ID,
            run_id=SAMPLE_RUN_ID,
            diff_content=diff,
            expected_checksum=sha256_hex(diff),
            expected_fingerprint=SAMPLE_FINGERPRINT,
            expected_state_version=SAMPLE_STATE_VERSION,
            actual_state_version=SAMPLE_STATE_VERSION,
            expected_plan_version=SAMPLE_PLAN_VERSION,
            actual_plan_version=SAMPLE_PLAN_VERSION,
            current_workspace_fingerprint=SAMPLE_WORKSPACE_FINGERPRINT,
        )
        assert report.overall_result == SafetyCheckResult.FAIL
        passes = [report.path_confinement_pass, report.symlink_escape_check_pass, report.path_traversal_check_pass]
        assert not all(passes)
