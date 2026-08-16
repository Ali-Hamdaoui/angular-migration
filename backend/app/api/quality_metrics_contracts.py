"""API contracts for quality and cost metrics (V2 F29)."""

from datetime import datetime

from app.domain.contracts import ContractModel


class StageQualityMetricsDto(ContractModel):
    stage_id: str
    stage_order: int
    source_version_family: str
    target_version_family: str
    sealed: bool
    repair_cycles: int
    command_latency_ms: float
    llm_total_tokens: int
    cost_usd: float


class RunQualityMetricsDto(ContractModel):
    run_id: str
    source_version_family: str
    target_version_family: str
    status: str
    success: bool
    stage_count: int
    sealed_stage_count: int
    repair_cycles: int
    total_tokens: int
    total_cost_usd: float
    llm_latency_ms: float
    command_latency_ms: float
    run_duration_seconds: float | None = None
    stages: list[StageQualityMetricsDto]


class QualityMetricRollupDto(ContractModel):
    scope: str
    key: str
    run_count: int
    success_count: int
    success_rate: float
    total_tokens: int
    total_cost_usd: float
    mean_repair_cycles: float
    mean_llm_latency_ms: float
    mean_command_latency_ms: float


class MetricTrendPointDto(ContractModel):
    bucket: str
    run_count: int
    success_count: int
    success_rate: float
    total_tokens: int
    total_cost_usd: float
    mean_repair_cycles: float
    measured_at: datetime


class MetricTrendListDto(ContractModel):
    points: list[MetricTrendPointDto]


class MetricRollupListDto(ContractModel):
    rollups: list[QualityMetricRollupDto]
