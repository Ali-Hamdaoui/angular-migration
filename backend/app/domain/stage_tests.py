"""Deterministic rules for S3-F12 stage tests and conditional lint.

This module defines:
- TestSuite, LintCheck types for stage test/lint execution
- BaselineFailureComparator for known baseline failure detection
- KnownFailurePolicy for handling pre-identified failures
- StageTestService for orchestrating test and lint execution
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StageTestError(ValueError):
    """Raised when stage test inputs or preconditions are invalid."""


class TestSuiteKind(str, Enum):
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"


class LintTool(str, Enum):
    ESLINT = "eslint"
    PRETTIER = "prettier"
    STYLELINT = "stylelint"


class TestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class TestSuite:
    """A test suite definition for stage execution."""
    suite_id: str
    kind: TestSuiteKind
    command_id: str
    executable: str = "npx"
    arguments: tuple[str, ...] = ()
    working_directory_alias: str = "STAGE_SANDBOX"
    timeout_seconds: int = 600
    supported: bool = True
    blocker: str | None = None


@dataclass(frozen=True)
class LintCheck:
    """A lint check definition for conditional execution."""
    check_id: str
    tool: LintTool
    command_id: str
    executable: str = "npx"
    arguments: tuple[str, ...] = ()
    working_directory_alias: str = "STAGE_SANDBOX"
    timeout_seconds: int = 300
    supported: bool = True
    blocker: str | None = None


@dataclass(frozen=True)
class TestResult:
    """Outcome of a single test suite execution."""
    suite_id: str
    kind: TestSuiteKind
    status: TestStatus
    exit_code: int | None = None
    duration_ms: int | None = None
    test_count: int | None = None
    passed_count: int | None = None
    failed_count: int | None = None
    skipped_count: int | None = None
    failed_tests: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    output_location: str | None = None
    artifact_ids: tuple[str, ...] = ()
    blocker: str | None = None


@dataclass(frozen=True)
class LintResult:
    """Outcome of a single lint check execution."""
    check_id: str
    tool: LintTool
    status: TestStatus
    exit_code: int | None = None
    duration_ms: int | None = None
    error_count: int = 0
    warning_count: int = 0
    issues: tuple[dict[str, Any], ...] = ()
    output_location: str | None = None
    artifact_ids: tuple[str, ...] = ()
    blocker: str | None = None


@dataclass(frozen=True)
class BaselineFailure:
    """A known baseline failure that can be compared."""
    test_name: str
    suite_kind: TestSuiteKind
    fingerprint: str
    failure_message: str | None = None
    expected_exit_code: int | None = None


class KnownFailurePolicy(str, Enum):
    """Policy for handling known baseline failures."""
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


class BaselineFailureComparator:
    """Compares test failures against baseline-known failures."""

    def __init__(self, known_failures: tuple[BaselineFailure, ...] = ()):
        self._known = {f.fingerprint: f for f in known_failures}

    def is_known_failure(self, result: TestResult, default_policy: KnownFailurePolicy = KnownFailurePolicy.WARN) -> tuple[bool, KnownFailurePolicy]:
        """Check if a test result matches a known baseline failure."""
        if result.failed_count is None or result.failed_count == 0:
            return False, default_policy
        for failed_test in result.failed_tests:
            if failed_test in self._known:
                return True, KnownFailurePolicy.ALLOW
        return False, default_policy


class StageTestService:
    """Orchestrates test suite execution and conditional lint.

    This service defines test suites, lint checks, and failure comparison.
    Actual execution is delegated to the application service layer.
    """

    def __init__(
        self,
        test_suites: tuple[TestSuite, ...] = (
            TestSuite(suite_id="stage-unit-tests", kind=TestSuiteKind.UNIT, command_id="stage_test_unit", arguments=("ng", "test", "--no-watch", "--browsers=ChromeHeadless")),
            TestSuite(suite_id="stage-integration-tests", kind=TestSuiteKind.INTEGRATION, command_id="stage_test_integration", arguments=("ng", "test", "--no-watch", "--browsers=ChromeHeadless", "--configuration=integration")),
        ),
        lint_checks: tuple[LintCheck, ...] = (
            LintCheck(check_id="stage-eslint", tool=LintTool.ESLINT, command_id="stage_lint_eslint", arguments=("npx", "eslint", ".")),
            LintCheck(check_id="stage-prettier", tool=LintTool.PRETTIER, command_id="stage_lint_prettier", arguments=("npx", "prettier", "--check", ".")),
        ),
        failure_comparator: BaselineFailureComparator | None = None,
    ):
        self._test_suites = test_suites
        self._lint_checks = lint_checks
        self._failure_comparator = failure_comparator or BaselineFailureComparator()

    def get_test_suites(self) -> list[TestSuite]:
        return list(self._test_suites)

    def get_lint_checks(self) -> list[LintCheck]:
        return list(self._lint_checks)

    def compare_to_baseline(
        self, result: TestResult, policy: KnownFailurePolicy = KnownFailurePolicy.WARN
    ) -> tuple[bool, KnownFailurePolicy]:
        """Compare a test result against known baseline failures."""
        return self._failure_comparator.is_known_failure(result, policy)

    def aggregate_test_summary(self, results: list[TestResult]) -> dict[str, Any]:
        """Aggregate test results into a summary dict."""
        return {
            "suite_count": len(results),
            "passed": sum(1 for r in results if r.status is TestStatus.PASSED),
            "failed": sum(1 for r in results if r.status is TestStatus.FAILED),
            "skipped": sum(1 for r in results if r.status is TestStatus.SKIPPED),
            "total_tests": sum(r.test_count or 0 for r in results),
            "total_passed": sum(r.passed_count or 0 for r in results),
            "total_failed": sum(r.failed_count or 0 for r in results),
            "total_skipped": sum(r.skipped_count or 0 for r in results),
            "known_baseline_failures": sum(
                1 for r in results if self._failure_comparator.is_known_failure(r)[0]
            ),
        }

    def aggregate_lint_summary(self, results: list[LintResult]) -> dict[str, Any]:
        """Aggregate lint results into a summary dict."""
        return {
            "check_count": len(results),
            "passed": sum(1 for r in results if r.status is TestStatus.PASSED),
            "failed": sum(1 for r in results if r.status is TestStatus.FAILED),
            "total_errors": sum(r.error_count for r in results),
            "total_warnings": sum(r.warning_count for r in results),
        }
