"""Quality and cost metrics contracts (V2 F29).

Deterministic metric schema over persisted evidence: tokens, latency, repair
cycles per stage, success/failure rates.  Rollups are reproducible and expose
per-run, per-stage, and per (source -> target) pair views; trends aggregate
across runs over time.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StageQualityMetrics(_ImmutableModel):
    """One stage's quality/cost metrics (F29-01)."""

    stage_id: str
    stage_order: int
    source_version_family: str
    target_version_family: str
    sealed: bool = False
    repair_cycles: int = Field(default=0, ge=0)
    command_latency_ms: float = Field(default=0.0, ge=0.0)
    llm_total_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)


class RunQualityMetrics(_ImmutableModel):
    """One run's quality/cost metrics (F29-01)."""

    run_id: str
    source_version_family: str
    target_version_family: str
    status: str
    success: bool
    stage_count: int = Field(default=0, ge=0)
    sealed_stage_count: int = Field(default=0, ge=0)
    repair_cycles: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    llm_latency_ms: float = Field(default=0.0, ge=0.0)
    command_latency_ms: float = Field(default=0.0, ge=0.0)
    run_duration_seconds: float | None = None
    stages: tuple[StageQualityMetrics, ...] = Field(default_factory=tuple)


class QualityMetricRollup(_ImmutableModel):
    """Aggregated metrics across a set of runs (F29-03)."""

    scope: str  # "run" | "stage" | "pair"
    key: str
    run_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    total_tokens: int = Field(default=0, ge=0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    mean_repair_cycles: float = Field(default=0.0, ge=0.0)
    mean_llm_latency_ms: float = Field(default=0.0, ge=0.0)
    mean_command_latency_ms: float = Field(default=0.0, ge=0.0)


class MetricTrendPoint(_ImmutableModel):
    """One time bucket of aggregate metrics (F29-04)."""

    bucket: str
    run_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    total_tokens: int = Field(default=0, ge=0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    mean_repair_cycles: float = Field(default=0.0, ge=0.0)
    measured_at: datetime
