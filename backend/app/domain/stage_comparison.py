"""Domain rules for route and backend integration comparison.

S3-F13 capability: compare transformed application routes and backend
integration points against the baseline to identify parity gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.stage_assurance import ComparisonStatus


class StageComparisonError(ValueError):
    """Raised when comparison logic detects an illegal operation."""


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


class RouteComparisonService:
    """Compare route configurations between baseline and transformed application."""

    @staticmethod
    def compare(*, baseline_routes: list[str], transformed_routes: list[str]) -> RouteComparisonResult:
        baseline_set = set(baseline_routes or [])
        transformed_set = set(transformed_routes or [])
        matched = tuple(sorted(baseline_set & transformed_set))
        mismatched = tuple(sorted(baseline_set ^ transformed_set))
        new_routes = tuple(sorted(transformed_set - baseline_set))
        removed_routes = tuple(sorted(baseline_set - transformed_set))
        status = ComparisonStatus.MATCH if not mismatched else ComparisonStatus.MISMATCH
        return RouteComparisonResult(
            status=status,
            matched_routes=matched,
            mismatched_routes=mismatched,
            new_routes=new_routes,
            removed_routes=removed_routes,
            details=f"{len(matched)} routes matched, {len(mismatched)} routes differ" if mismatched else "All routes match",
        )


class BackendIntegrationComparisonService:
    """Compare backend integration endpoints between baseline and transformed application."""

    @staticmethod
    def compare(*, baseline_endpoints: list[str], transformed_endpoints: list[str]) -> BackendIntegrationResult:
        baseline_set = set(baseline_endpoints or [])
        transformed_set = set(transformed_endpoints or [])
        matched = tuple(sorted(baseline_set & transformed_set))
        mismatched = tuple(sorted(baseline_set ^ transformed_set))
        status = ComparisonStatus.MATCH if not mismatched else ComparisonStatus.MISMATCH
        return BackendIntegrationResult(
            status=status,
            matched_endpoints=matched,
            mismatched_endpoints=mismatched,
            details=f"{len(matched)} endpoints matched, {len(mismatched)} endpoints differ" if mismatched else "All endpoints match",
        )
