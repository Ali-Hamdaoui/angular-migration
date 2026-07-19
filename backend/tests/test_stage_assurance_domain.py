"""S3-F13 domain test — stage assurance, parity, and G09 gate."""
import pytest
from app.domain.stage_assurance import (
    AssuranceAggregator,
    AssuranceCheck,
    AssuranceDimension,
    AssuranceStatus,
    BackendIntegrationResult,
    ComparisonStatus,
    G09Gate,
    GateDecision,
    RouteComparisonResult,
    StageAssuranceError,
)
from app.domain.stage_comparison import (
    BackendIntegrationComparisonService,
    RouteComparisonService,
    StageComparisonError,
)


def test_assurance_aggregator_all_passed():
    """Aggregating all-passed checks produces PASSED."""
    checks = [
        AssuranceCheck(dimension=AssuranceDimension.TECHNICAL_UPGRADE, status=AssuranceStatus.PASSED, details="OK"),
        AssuranceCheck(dimension=AssuranceDimension.FUNCTIONAL_PARITY, status=AssuranceStatus.PASSED, details="All routes match"),
    ]
    status = AssuranceAggregator.aggregate(checks)
    assert status is AssuranceStatus.PASSED


def test_assurance_aggregator_with_failures():
    """A failed check produces FAILED."""
    checks = [
        AssuranceCheck(dimension=AssuranceDimension.TECHNICAL_UPGRADE, status=AssuranceStatus.PASSED),
        AssuranceCheck(dimension=AssuranceDimension.FUNCTIONAL_PARITY, status=AssuranceStatus.FAILED, details="Route mismatch"),
    ]
    status = AssuranceAggregator.aggregate(checks)
    assert status is AssuranceStatus.FAILED


def test_assurance_aggregator_empty():
    """Empty checks produce NOT_EVALUATED."""
    status = AssuranceAggregator.aggregate([])
    assert status is AssuranceStatus.NOT_EVALUATED


def test_assurance_aggregator_manual_required():
    """A manual_required check produces MANUAL_REQUIRED."""
    checks = [
        AssuranceCheck(dimension=AssuranceDimension.SECURITY_ASSURANCE, status=AssuranceStatus.PASSED),
        AssuranceCheck(dimension=AssuranceDimension.QUALITY_ASSURANCE, status=AssuranceStatus.MANUAL_REQUIRED, details="Requires manual verification"),
    ]
    status = AssuranceAggregator.aggregate(checks)
    assert status is AssuranceStatus.MANUAL_REQUIRED


def test_assurance_aggregator_conditional():
    """A conditional check produces CONDITIONAL."""
    checks = [
        AssuranceCheck(dimension=AssuranceDimension.QUALITY_ASSURANCE, status=AssuranceStatus.CONDITIONAL, details="Quality within thresholds"),
    ]
    status = AssuranceAggregator.aggregate(checks)
    assert status is AssuranceStatus.CONDITIONAL


def test_g09_can_approve():
    """G09 gate can approve when conditions are met."""
    assert G09Gate.can_approve(assurance_status=AssuranceStatus.PASSED, all_gates_passed=True) is True
    assert G09Gate.can_approve(assurance_status=AssuranceStatus.CONDITIONAL, all_gates_passed=True) is True
    assert G09Gate.can_approve(assurance_status=AssuranceStatus.FAILED, all_gates_passed=True) is False
    assert G09Gate.can_approve(assurance_status=AssuranceStatus.PASSED, all_gates_passed=False) is False


def test_g09_requires_review():
    """G09 gate correctly identifies when review is required."""
    assert G09Gate.requires_review(assurance_status=AssuranceStatus.CONDITIONAL) is True
    assert G09Gate.requires_review(assurance_status=AssuranceStatus.MANUAL_REQUIRED) is True
    assert G09Gate.requires_review(assurance_status=AssuranceStatus.PASSED) is False
    assert G09Gate.requires_review(assurance_status=AssuranceStatus.FAILED) is False
    assert G09Gate.requires_review(assurance_status=AssuranceStatus.NOT_EVALUATED) is False


def test_route_comparison_service():
    """RouteComparisonService compares routes correctly."""
    service = RouteComparisonService()
    source = ["/home", "/admin"]
    target = ["/home", "/dashboard"]
    result = service.compare(baseline_routes=source, transformed_routes=target)
    assert result.status is ComparisonStatus.MISMATCH
    assert "/home" in result.matched_routes
    assert "/admin" in result.mismatched_routes or "/admin" in result.removed_routes
    assert "/dashboard" in result.mismatched_routes or "/dashboard" in result.new_routes


def test_backend_integration_comparison():
    """BackendIntegrationComparisonService compares integrations correctly."""
    service = BackendIntegrationComparisonService()
    source = ["/api/user"]
    target = ["/api/v2/user"]
    result = service.compare(baseline_endpoints=source, transformed_endpoints=target)
    assert result.status is ComparisonStatus.MISMATCH
    assert "/api/user" in result.mismatched_endpoints or "/api/v2/user" in result.mismatched_endpoints


def test_route_comparison_result_defaults():
    """RouteComparisonResult has sensible defaults."""
    result = RouteComparisonResult(status=ComparisonStatus.NOT_EVALUATED)
    assert result.matched_routes == ()
    assert result.mismatched_routes == ()
    assert result.details == ""


def test_backend_integration_result_defaults():
    """BackendIntegrationResult has sensible defaults."""
    result = BackendIntegrationResult(status=ComparisonStatus.NOT_EVALUATED)
    assert result.matched_endpoints == ()
    assert result.mismatched_endpoints == ()


def test_assurance_check_defaults():
    """AssuranceCheck has sensible defaults."""
    check = AssuranceCheck(dimension=AssuranceDimension.TECHNICAL_UPGRADE, status=AssuranceStatus.PASSED)
    assert check.details == ""
    assert check.evidence_refs == ()


def test_stage_assurance_error_raised():
    """StageAssuranceError is a ValueError."""
    with pytest.raises(StageAssuranceError):
        raise StageAssuranceError("Test error")


def test_stage_comparison_error_raised():
    """StageComparisonError is a ValueError."""
    with pytest.raises(StageComparisonError):
        raise StageComparisonError("Test comparison error")
