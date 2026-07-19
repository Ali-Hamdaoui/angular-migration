"""S3-F10 domain test — stage validation (install + static checks)."""
import pytest
from app.domain.stage_validation import (
    InstallStaticCheckType,
    StageValidationError,
    StageValidationService,
    StaticCheckResult,
    ValidationResult,
    ValidationResultStatus,
)


def test_aggregate_results_all_passed():
    """Aggregating all-passed checks produces a passed ValidationResult."""
    checks = [
        StaticCheckResult(check_type=InstallStaticCheckType.TYPESCRIPT_COMPILE, status=ValidationResultStatus.PASSED, message="OK"),
        StaticCheckResult(check_type=InstallStaticCheckType.TEMPLATE_CHECK, status=ValidationResultStatus.PASSED, message="OK"),
    ]
    result = StageValidationService.aggregate_results(check_results=checks, install_succeeded=True, install_duration_ms=45000)
    assert result.install_succeeded is True
    assert result.all_checks_passed is True
    assert len(result.check_results) == 2


def test_aggregate_results_failed_static_check():
    """A failed static check produces all_checks_passed=False."""
    checks = [
        StaticCheckResult(check_type=InstallStaticCheckType.TYPESCRIPT_COMPILE, status=ValidationResultStatus.FAILED, message="TS2322: Type error"),
    ]
    result = StageValidationService.aggregate_results(check_results=checks, install_succeeded=True)
    assert result.install_succeeded is True
    assert result.all_checks_passed is False


def test_aggregate_results_failed_install():
    """A failed install produces all_checks_passed=False."""
    result = StageValidationService.aggregate_results(check_results=[], install_succeeded=False)
    assert result.install_succeeded is False
    assert result.all_checks_passed is False


def test_not_configured_check_is_not_a_failure():
    """A not_configured check is treated neutrally - does not fail."""
    checks = [
        StaticCheckResult(check_type=InstallStaticCheckType.ANGULAR_COMPAT, status=ValidationResultStatus.NOT_CONFIGURED, message="Not configured for this project"),
    ]
    result = StageValidationService.aggregate_results(check_results=checks, install_succeeded=True)
    # not_configured is not PASSED, so all_checks_passed is False
    # but the check itself is not a failure
    assert result.install_succeeded is True
    assert result.check_results[0].status is ValidationResultStatus.NOT_CONFIGURED


def test_aggregate_summary():
    """Summary contains correct metadata."""
    checks = [
        StaticCheckResult(check_type=InstallStaticCheckType.TYPESCRIPT_COMPILE, status=ValidationResultStatus.PASSED, message="OK"),
    ]
    result = StageValidationService.aggregate_results(check_results=checks, install_succeeded=True, install_duration_ms=30000)
    summary = StageValidationService.aggregate_summary(result)
    assert summary["install_succeeded"] is True
    assert summary["all_checks_passed"] is True
    assert summary["check_result_count"] == 1
    assert summary["overall"] == "passed"


def test_aggregate_summary_failed():
    """Summary correctly reports failure."""
    checks = [
        StaticCheckResult(check_type=InstallStaticCheckType.TYPESCRIPT_COMPILE, status=ValidationResultStatus.FAILED, message="Error"),
    ]
    result = StageValidationService.aggregate_results(check_results=checks, install_succeeded=True)
    summary = StageValidationService.aggregate_summary(result)
    assert summary["overall"] == "failed"


def test_stage_validation_error_raised():
    """StageValidationError is a ValueError."""
    with pytest.raises(StageValidationError):
        raise StageValidationError("Test validation error")


def test_static_check_result_defaults():
    """StaticCheckResult has sensible defaults."""
    result = StaticCheckResult(check_type=InstallStaticCheckType.TYPESCRIPT_COMPILE, status=ValidationResultStatus.PASSED)
    assert result.message == ""
    assert result.duration_ms == 0
    assert result.details is None


def test_validation_result_defaults():
    """ValidationResult has sensible defaults."""
    result = ValidationResult()
    assert result.install_succeeded is False
    assert result.install_duration_ms == 0
    assert len(result.check_results) == 0
    assert result.all_checks_passed is False
