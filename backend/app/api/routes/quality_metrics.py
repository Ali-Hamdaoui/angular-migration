"""Quality and cost metrics API (V2 F29)."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.quality_metrics_contracts import (
    MetricRollupListDto,
    MetricTrendListDto,
    MetricTrendPointDto,
    QualityMetricRollupDto,
    RunQualityMetricsDto,
    StageQualityMetricsDto,
)
from app.services.quality_metrics_service import QualityMetricError, QualityMetricsService

router = APIRouter(tags=["quality-metrics"])


def get_metrics_service() -> QualityMetricsService:
    return QualityMetricsService()


def _stage_dto(s) -> StageQualityMetricsDto:
    return StageQualityMetricsDto(
        stage_id=s.stage_id, stage_order=s.stage_order,
        source_version_family=s.source_version_family, target_version_family=s.target_version_family,
        sealed=s.sealed, repair_cycles=s.repair_cycles, command_latency_ms=s.command_latency_ms,
        llm_total_tokens=s.llm_total_tokens, cost_usd=s.cost_usd,
    )


def _run_dto(r) -> RunQualityMetricsDto:
    return RunQualityMetricsDto(
        run_id=r.run_id, source_version_family=r.source_version_family,
        target_version_family=r.target_version_family, status=r.status, success=r.success,
        stage_count=r.stage_count, sealed_stage_count=r.sealed_stage_count,
        repair_cycles=r.repair_cycles, total_tokens=r.total_tokens,
        total_cost_usd=r.total_cost_usd, llm_latency_ms=r.llm_latency_ms,
        command_latency_ms=r.command_latency_ms, run_duration_seconds=r.run_duration_seconds,
        stages=[_stage_dto(s) for s in r.stages],
    )


def _raise(error: QualityMetricError) -> None:
    raise HTTPException(status_code=404 if error.code == "RUN_NOT_FOUND" else 422,
                        detail={"error_code": error.code, "message": error.message})


@router.get("/runs/{run_id}/quality-metrics", response_model=RunQualityMetricsDto)
def get_run_metrics(
    run_id: str,
    service: QualityMetricsService = Depends(get_metrics_service),
) -> RunQualityMetricsDto:
    try:
        metrics = service.collect_run(run_id)
    except QualityMetricError as error:
        _raise(error)
    return _run_dto(metrics)


@router.get("/quality-metrics/rollup", response_model=MetricRollupListDto)
def get_rollup(
    source: str | None = Query(default=None),
    target: str | None = Query(default=None),
    service: QualityMetricsService = Depends(get_metrics_service),
) -> MetricRollupListDto:
    return MetricRollupListDto(rollups=[QualityMetricRollupDto(**r.model_dump()) for r in service.rollup(source=source, target=target)])


@router.get("/quality-metrics/trend", response_model=MetricTrendListDto)
def get_trend(
    bucket: str = Query(default="day"),
    since_days: int = Query(default=90, ge=1),
    service: QualityMetricsService = Depends(get_metrics_service),
) -> MetricTrendListDto:
    return MetricTrendListDto(points=[MetricTrendPointDto(**p.model_dump()) for p in service.trend(bucket=bucket, since_days=since_days)])
