"""Retrieval benchmark service (V2 F28-02/03).

Runs the deterministic 11 -> 21 fixture set through the F20 code-context
retrieval, measures relevance (precision/recall/f1), latency, and budget
utilization, and persists a versioned report.
"""

from __future__ import annotations

import hashlib
import statistics
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

from sqlalchemy import select

from app.domain.retrieval_benchmark import (
    RetrievalBenchmarkCase,
    RetrievalBenchmarkCaseResult,
    RetrievalBenchmarkReport,
)
from app.repositories.models import MigrationRunModel
from app.repositories.retrieval_benchmark_models import RetrievalBenchmarkModel
from app.repositories.session import session_scope
from app.services.code_context_service import CodeContextError, CodeContextService
from app.services.retrieval_benchmark_fixtures import benchmark_fixture_set, build_fixture_workspace


class RetrievalBenchmarkError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RetrievalBenchmarkService:
    """Deterministic retrieval benchmark over the 11 -> 21 fixture set (F28)."""

    def __init__(
        self,
        *,
        context_service: CodeContextService | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._context = context_service or CodeContextService()
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def run_benchmark(
        self,
        *,
        workspace_root: Path,
        fixture_set: list[RetrievalBenchmarkCase] | None = None,
        run_id: str | None = None,
    ) -> RetrievalBenchmarkReport:
        """Run the fixture set and produce a deterministic, versioned report (F28-02)."""
        fixture_set = fixture_set or benchmark_fixture_set()
        run_id = run_id or f"bench-{uuid4().hex[:12]}"
        if not workspace_root.is_dir():
            raise RetrievalBenchmarkError("WORKSPACE_ROOT_MISSING", "benchmark workspace root is not a directory")
        case_results = [self._run_case(workspace_root, case) for case in fixture_set]

        precisions = [r.precision for r in case_results]
        recalls = [r.recall for r in case_results]
        f1s = [r.f1 for r in case_results]
        latencies = sorted(r.latency_ms for r in case_results)
        budget_utilizations = [r.budget_utilization for r in case_results]
        report = RetrievalBenchmarkReport(
            benchmark_id=run_id,
            version=1,
            fixture_set="11-to-21",
            case_results=tuple(case_results),
            mean_precision=round(statistics.fmean(precisions), 4),
            mean_recall=round(statistics.fmean(recalls), 4),
            mean_f1=round(statistics.fmean(f1s), 4),
            p95_latency_ms=round(_percentile(latencies, 0.95), 3),
            mean_budget_utilization=round(statistics.fmean(budget_utilizations), 4),
            deterministic=True,
            ran_at=self._now_provider(),
        ).bind_checksum()
        return report

    def persist_report(self, report: RetrievalBenchmarkReport) -> RetrievalBenchmarkModel:
        """Persist the versioned benchmark report (F28-03).

        Idempotent by fixture_set+checksum: re-running identical retrieval
        returns the existing report; changed results bump to the next version.
        """
        with self._session_scope() as session:
            existing_by_set = list(
                session.scalars(
                    select(RetrievalBenchmarkModel)
                    .where(RetrievalBenchmarkModel.fixture_set == report.fixture_set)
                    .order_by(RetrievalBenchmarkModel.version.desc())
                ).all()
            )
            for existing in existing_by_set:
                if existing.checksum == report.checksum:
                    return existing
            version = (existing_by_set[0].version + 1) if existing_by_set else report.version
            benchmark_id = "bench-" + hashlib.sha256(
                f"{report.fixture_set}:{version}:{report.checksum}".encode()
            ).hexdigest()[:24]
            model = RetrievalBenchmarkModel(
                id=benchmark_id,
                version=version,
                fixture_set=report.fixture_set,
                case_results=[r.model_dump(mode="json") for r in report.case_results],
                mean_precision=report.mean_precision,
                mean_recall=report.mean_recall,
                mean_f1=report.mean_f1,
                p95_latency_ms=report.p95_latency_ms,
                mean_budget_utilization=report.mean_budget_utilization,
                deterministic=report.deterministic,
                checksum=report.checksum,
                ran_at=report.ran_at,
                created_at=self._now_provider(),
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return model

    def list_reports(self) -> list[RetrievalBenchmarkModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(RetrievalBenchmarkModel).order_by(RetrievalBenchmarkModel.ran_at.desc())
                ).all()
            )

    def get_report(self, benchmark_id: str) -> RetrievalBenchmarkModel | None:
        with self._session_scope() as session:
            return session.get(RetrievalBenchmarkModel, benchmark_id)

    def _assert_root_allowed(self, workspace_root: Path) -> None:
        """Fail closed before any fixture is written (review hardening).

        The default service (no injected roots) is only reachable from
        non-API callers; the API route always binds ALLOWED_SOURCE_ROOTS.
        """
        context = self._context
        if getattr(context, "_allow_all", False):
            return
        allowed_roots = getattr(context, "_allowed_roots", [])
        resolved = workspace_root.resolve(strict=False)
        if allowed_roots and not any(
            _within_root(resolved, root) for root in allowed_roots
        ):
            raise RetrievalBenchmarkError(
                "WORKSPACE_ROOT_NOT_ALLOWED",
                f"benchmark workspace_root {workspace_root} is outside the allowed source roots",
            )

    def _run_case(self, workspace_root: Path, case: RetrievalBenchmarkCase) -> RetrievalBenchmarkCaseResult:
        self._assert_root_allowed(workspace_root)
        workspace = build_fixture_workspace(workspace_root, case)
        started = monotonic()
        try:
            bundle = self._context.retrieve_context(
                workspace, list(case.symbols), list(case.template_selectors), budget=case.budget
            )
            retrieved_files = sorted({Path(unit.path).name for unit in bundle.units})
            relevant = set(case.relevant_files)
            relevant_retrieved = sorted(set(retrieved_files) & relevant)
            precision = len(relevant_retrieved) / len(retrieved_files) if retrieved_files else 0.0
            recall = len(relevant_retrieved) / len(relevant) if relevant else 0.0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        except CodeContextError as error:
            raise RetrievalBenchmarkError(
                "BENCHMARK_CASE_FAILED",
                f"case {case.case_id} failed: {error.message}",
            ) from error
        finally:
            latency_ms = (monotonic() - started) * 1000.0
        return RetrievalBenchmarkCaseResult(
            case_id=case.case_id,
            fixture_kind=case.fixture_kind.value,
            source_major=case.source_major,
            retrieved_files=tuple(retrieved_files),
            relevant_retrieved=tuple(relevant_retrieved),
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            latency_ms=round(latency_ms, 3),
            budget=case.budget,
            total_tokens=bundle.total_tokens,
            budget_utilization=round(bundle.total_tokens / case.budget, 4),
            truncated=bundle.truncated,
        )


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    index = max(0, min(len(sorted_values) - 1, int(p * len(sorted_values))))
    return sorted_values[index]


def _within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
