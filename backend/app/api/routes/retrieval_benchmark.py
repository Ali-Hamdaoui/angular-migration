"""Retrieval benchmark API (V2 F28)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.retrieval_benchmark_contracts import (
    RetrievalBenchmarkCaseResultDto,
    RetrievalBenchmarkListDto,
    RetrievalBenchmarkReportDto,
    RetrievalBenchmarkRunRequest,
)
from app.services.retrieval_benchmark_service import RetrievalBenchmarkError, RetrievalBenchmarkService

router = APIRouter(tags=["retrieval-benchmark"])


def get_benchmark_service() -> RetrievalBenchmarkService:
    from app.core.config import get_settings
    from app.services.code_context_service import CodeContextService

    roots = get_settings().allowed_source_roots
    if not roots:
        raise RuntimeError("ALLOWED_SOURCE_ROOTS must be configured for the retrieval benchmark endpoint")
    return RetrievalBenchmarkService(context_service=CodeContextService(allowed_roots=roots))


def _case_dto(result) -> RetrievalBenchmarkCaseResultDto:
    return RetrievalBenchmarkCaseResultDto(
        case_id=result.case_id, fixture_kind=result.fixture_kind, source_major=result.source_major,
        retrieved_files=list(result.retrieved_files), relevant_retrieved=list(result.relevant_retrieved),
        precision=result.precision, recall=result.recall, f1=result.f1, latency_ms=result.latency_ms,
        budget=result.budget, total_tokens=result.total_tokens,
        budget_utilization=result.budget_utilization, truncated=result.truncated,
    )


def _report_dto(report) -> RetrievalBenchmarkReportDto:
    if isinstance(report, dict):
        return RetrievalBenchmarkReportDto(**report)
    return RetrievalBenchmarkReportDto(
        benchmark_id=report.benchmark_id, version=report.version, fixture_set=report.fixture_set,
        case_results=[_case_dto(r) for r in report.case_results],
        mean_precision=report.mean_precision, mean_recall=report.mean_recall, mean_f1=report.mean_f1,
        p95_latency_ms=report.p95_latency_ms, mean_budget_utilization=report.mean_budget_utilization,
        deterministic=report.deterministic, ran_at=report.ran_at, checksum=report.checksum,
    )


def _raise(error: RetrievalBenchmarkError) -> None:
    raise HTTPException(status_code=404 if error.code == "BENCHMARK_NOT_FOUND" else 422,
                        detail={"error_code": error.code, "message": error.message})


def _from_model(model) -> dict:
    return {
        "benchmark_id": model.id,
        "version": model.version,
        "fixture_set": model.fixture_set,
        "case_results": list(model.case_results),
        "mean_precision": model.mean_precision,
        "mean_recall": model.mean_recall,
        "mean_f1": model.mean_f1,
        "p95_latency_ms": model.p95_latency_ms,
        "mean_budget_utilization": model.mean_budget_utilization,
        "deterministic": model.deterministic,
        "ran_at": model.ran_at,
        "checksum": model.checksum,
    }


@router.post("/retrieval-benchmark/run", response_model=RetrievalBenchmarkReportDto)
def run_benchmark(
    request: RetrievalBenchmarkRunRequest,
    service: RetrievalBenchmarkService = Depends(get_benchmark_service),
) -> RetrievalBenchmarkReportDto:
    try:
        report = service.run_benchmark(workspace_root=Path(request.workspace_root))
        persisted = service.persist_report(report)
    except RetrievalBenchmarkError as error:
        _raise(error)
    return _report_dto(_from_model(persisted))


@router.get("/retrieval-benchmark", response_model=RetrievalBenchmarkListDto)
def list_benchmarks(
    service: RetrievalBenchmarkService = Depends(get_benchmark_service),
) -> RetrievalBenchmarkListDto:
    return RetrievalBenchmarkListDto(benchmarks=[_report_dto(_from_model(r)) for r in service.list_reports()])


@router.get("/retrieval-benchmark/{benchmark_id}", response_model=RetrievalBenchmarkReportDto)
def get_benchmark(
    benchmark_id: str,
    service: RetrievalBenchmarkService = Depends(get_benchmark_service),
) -> RetrievalBenchmarkReportDto:
    report = service.get_report(benchmark_id)
    if report is None:
        raise HTTPException(status_code=404,
                            detail={"error_code": "BENCHMARK_NOT_FOUND", "message": "Benchmark report not found"})
    return _report_dto(_from_model(report))
