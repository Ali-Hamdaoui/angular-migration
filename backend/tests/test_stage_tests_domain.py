"""S3-F12 domain test — stage test suite and lint."""
import pytest
from app.domain.stage_tests import (
    BaselineFailure,
    BaselineFailureComparator,
    KnownFailurePolicy,
    LintCheck,
    LintResult,
    LintTool,
    StageTestError,
    StageTestService,
    TestResult,
    TestStatus,
    TestSuite,
    TestSuiteKind,
)


def test_get_test_suites():
    """StageTestService returns configured test suites."""
    service = StageTestService()
    suites = service.get_test_suites()
    assert len(suites) >= 2
    kinds = {s.kind for s in suites}
    assert TestSuiteKind.UNIT in kinds
    assert TestSuiteKind.INTEGRATION in kinds


def test_get_lint_checks():
    """StageTestService returns configured lint checks."""
    service = StageTestService()
    checks = service.get_lint_checks()
    assert len(checks) >= 2
    tools = {c.tool for c in checks}
    assert LintTool.ESLINT in tools


def test_aggregate_test_summary_all_passed():
    """Aggregate test summary correctly counts passed tests."""
    service = StageTestService()
    results = [
        TestResult(suite_id="unit", kind=TestSuiteKind.UNIT, status=TestStatus.PASSED, test_count=10, passed_count=10, failed_count=0),
        TestResult(suite_id="integration", kind=TestSuiteKind.INTEGRATION, status=TestStatus.PASSED, test_count=5, passed_count=5, failed_count=0),
    ]
    summary = service.aggregate_test_summary(results)
    assert summary["suite_count"] == 2
    assert summary["passed"] == 2
    assert summary["total_tests"] == 15
    assert summary["total_passed"] == 15


def test_aggregate_test_summary_with_failures():
    """Aggregate test summary correctly counts failures."""
    service = StageTestService()
    results = [
        TestResult(suite_id="unit", kind=TestSuiteKind.UNIT, status=TestStatus.FAILED, test_count=10, passed_count=8, failed_count=2, failed_tests=("Header renders",)),
    ]
    summary = service.aggregate_test_summary(results)
    assert summary["failed"] == 1
    assert summary["total_failed"] == 2


def test_aggregate_lint_summary():
    """Aggregate lint summary correctly reports results."""
    service = StageTestService()
    results = [
        LintResult(check_id="eslint", tool=LintTool.ESLINT, status=TestStatus.PASSED, error_count=0, warning_count=1),
        LintResult(check_id="prettier", tool=LintTool.PRETTIER, status=TestStatus.FAILED, error_count=2, warning_count=0),
    ]
    summary = service.aggregate_lint_summary(results)
    assert summary["check_count"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["total_errors"] == 2
    assert summary["total_warnings"] == 1


def test_baseline_failure_comparator_detects_known():
    """BaselineFailureComparator detects known failures."""
    known = (BaselineFailure(test_name="Header renders", suite_kind=TestSuiteKind.UNIT, fingerprint="Header renders"),)
    comparator = BaselineFailureComparator(known_failures=known)
    result = TestResult(suite_id="unit", kind=TestSuiteKind.UNIT, status=TestStatus.FAILED, failed_count=1, failed_tests=("Header renders",))
    is_known, policy = comparator.is_known_failure(result)
    assert is_known is True
    assert policy is KnownFailurePolicy.ALLOW


def test_baseline_failure_comparator_unknown():
    """BaselineFailureComparator returns default policy for unknown failures."""
    comparator = BaselineFailureComparator()
    result = TestResult(suite_id="unit", kind=TestSuiteKind.UNIT, status=TestStatus.FAILED, failed_count=1, failed_tests=("Unknown failure",))
    is_known, policy = comparator.is_known_failure(result)
    assert is_known is False
    assert policy is KnownFailurePolicy.WARN


def test_baseline_failure_no_failures():
    """Comparator returns False when result has no failures."""
    comparator = BaselineFailureComparator()
    result = TestResult(suite_id="unit", kind=TestSuiteKind.UNIT, status=TestStatus.PASSED, failed_count=0)
    is_known, policy = comparator.is_known_failure(result)
    assert is_known is False


def test_test_suite_defaults():
    """TestSuite has sensible defaults."""
    suite = TestSuite(suite_id="test-suite", kind=TestSuiteKind.UNIT, command_id="test:unit")
    assert suite.executable == "npx"
    assert suite.arguments == ()
    assert suite.timeout_seconds == 600
    assert suite.supported is True


def test_test_result_defaults():
    """TestResult has sensible defaults."""
    result = TestResult(suite_id="test-suite", kind=TestSuiteKind.UNIT, status=TestStatus.PENDING)
    assert result.exit_code is None
    assert result.test_count is None
    assert result.failed_tests == ()


def test_stage_test_error_raised():
    """StageTestError is a ValueError."""
    with pytest.raises(StageTestError):
        raise StageTestError("Test error")
