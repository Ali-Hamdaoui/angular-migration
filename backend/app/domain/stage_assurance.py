"""Domain rules for parity comparison, assurance aggregation, and gate decisions.

S3-F13 capability: route comparison, backend integration comparison,
assurance dimension aggregation, G09 validation acceptance gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StageAssuranceError(ValueError):
    """Raised when assurance logic detects an illegal operation."""


class ComparisonStatus(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    NEW = "new"
    REMOVED = "removed"
    NOT_EVALUATED = "not_evaluated"
    ERROR = "error"


class AssuranceDimension(str, Enum):
    TECHNICAL_UPGRADE = "technical_upgrade"
    FUNCTIONAL_PARITY = "functional_parity"
    ROUTE_COMPARISON = "route_comparison"
    BACKEND_INTEGRATION = "backend_integration"
    SECURITY_ASSURANCE = "security_assurance"
    QUALITY_ASSURANCE = "quality_assurance"


class AssuranceStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    CONDITIONAL = "conditional"
    MANUAL_REQUIRED = "manual_required"
    NOT_EVALUATED = "not_evaluated"


class GateDecision(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ACCEPTED_RISK = "ACCEPTED_RISK"
    MODIFICATION_REQUESTED = "MODIFICATION_REQUESTED"


@dataclass(frozen=True)
class AssuranceCheck:
    dimension: AssuranceDimension
    status: AssuranceStatus
    details: str = ""
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RouteComparisonResult:
    status: ComparisonStatus
    matched_routes: tuple[str, ...] = ()
    mismatched_routes: tuple[str, ...] = ()
    new_routes: tuple[str, ...] = ()
    removed_routes: tuple[str, ...] = ()
    details: str = ""


@dataclass(frozen=True)
class BackendIntegrationResult:
    status: ComparisonStatus
    matched_endpoints: tuple[str, ...] = ()
    mismatched_endpoints: tuple[str, ...] = ()
    details: str = ""


class G09Gate:
    """G09 validation acceptance gate logic."""
    GATE_ID = "G09"
    GATE_VERSION = "g09-v1"

    @staticmethod
    def can_approve(*, assurance_status: AssuranceStatus, all_gates_passed: bool = True) -> bool:
        return all_gates_passed and assurance_status in (AssuranceStatus.PASSED, AssuranceStatus.CONDITIONAL)

    @staticmethod
    def requires_review(*, assurance_status: AssuranceStatus) -> bool:
        return assurance_status in (AssuranceStatus.CONDITIONAL, AssuranceStatus.MANUAL_REQUIRED)


class AssuranceAggregator:
    """Aggregate assurance dimension checks into a composite result."""

    @staticmethod
    def aggregate(checks: list[AssuranceCheck]) -> AssuranceStatus:
        if not checks:
            return AssuranceStatus.NOT_EVALUATED
        if any(c.status is AssuranceStatus.FAILED for c in checks):
            return AssuranceStatus.FAILED
        if all(c.status is AssuranceStatus.PASSED for c in checks):
            return AssuranceStatus.PASSED
        if any(c.status is AssuranceStatus.MANUAL_REQUIRED for c in checks):
            return AssuranceStatus.MANUAL_REQUIRED
        if any(c.status is AssuranceStatus.CONDITIONAL for c in checks):
            return AssuranceStatus.CONDITIONAL
        return AssuranceStatus.NOT_EVALUATED
