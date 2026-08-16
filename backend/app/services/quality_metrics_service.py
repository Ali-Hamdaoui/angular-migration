"""Quality and cost metric collection service (V2 F29-02).

Computes deterministic per-run metrics from persisted evidence (runs,
stages, LLM usage/cost records, repair attempts, command executions).  All
aggregations are pure functions of the evidence, so repeated collection is
reproducible.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.domain.quality_metrics import (
    MetricTrendPoint,
    QualityMetricRollup,
    RunQualityMetrics,
    StageQualityMetrics,
)
from app.repositories.models import (
    CommandExecutionModel,
    LlmInvocationModel,
    LlmUsageRecordModel,
    MigrationRunModel,
    MigrationStageModel,
    RepairAttemptModel,
    UsageCostRecordModel,
)
from app.repositories.session import session_scope

_SUCCESS_STATUSES = frozenset({"COMPLETED"})
_TERMINAL = frozenset({"COMPLETED", "CANCELLED", "FAILED", "TIMED_OUT", "WORKER_LOST", "ORPHANED", "CLEANUP_FAILED"})


class QualityMetricError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _family(value: str | None) -> str:
    return value or "unknown"


def _seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    if end <= start:
        return None
    return (end - start).total_seconds()


class QualityMetricsService:
    """Deterministic quality/cost metrics from persisted evidence (F29)."""

    def __init__(self, *, session_scope_factory=None) -> None:
        self._session_scope = session_scope_factory or session_scope

    def collect_run(self, run_id: str) -> RunQualityMetrics:
        """Collect one run's quality/cost metrics deterministically (F29-02)."""
        with self._session_scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise QualityMetricError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
            stages = list(
                session.scalars(
                    select(MigrationStageModel)
                    .where(MigrationStageModel.run_id == run_id)
                    .order_by(MigrationStageModel.stage_order)
                ).all()
            )
            usage = list(session.scalars(select(LlmUsageRecordModel).where(LlmUsageRecordModel.run_id == run_id)).all())
            costs = list(session.scalars(select(UsageCostRecordModel).where(UsageCostRecordModel.run_id == run_id)).all())
            invocations = list(session.scalars(select(LlmInvocationModel).where(LlmInvocationModel.run_id == run_id)).all())
            attempts = list(session.scalars(select(RepairAttemptModel).where(RepairAttemptModel.run_id == run_id)).all())
            commands = list(session.scalars(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id)).all())

        attempts_by_stage: defaultdict[str, int] = defaultdict(int)
        for attempt in attempts:
            attempts_by_stage[attempt.stage_id] += 1

        command_latency_by_stage: defaultdict[str, float] = defaultdict(float)
        command_latency_total = 0.0
        for command in commands:
            elapsed = _seconds(command.started_at, command.finished_at)
            if elapsed is not None:
                command_latency_total += elapsed * 1000
                if command.stage_id:
                    command_latency_by_stage[command.stage_id] += elapsed * 1000

        llm_tokens_by_stage: defaultdict[str, int] = defaultdict(int)
        llm_cost_by_stage: defaultdict[str, float] = defaultdict(float)
        for cost in costs:
            stage_key = cost.stage_id or ""
            llm_cost_by_stage[stage_key] += getattr(cost, "total_cost_usd", 0.0) or 0.0
            llm_tokens_by_stage[stage_key] += cost.total_tokens
        llm_tokens_by_run = sum(record.total_tokens for record in usage)

        stage_metrics: list[StageQualityMetrics] = []
        sealed = 0
        for stage in stages:
            stage_metrics.append(
                StageQualityMetrics(
                    stage_id=stage.id,
                    stage_order=stage.stage_order,
                    source_version_family=_family(stage.source_version_family),
                    target_version_family=_family(stage.target_version_family),
                    sealed=bool(stage.status == "sealed"),
                    repair_cycles=attempts_by_stage.get(stage.id, 0),
                    command_latency_ms=round(command_latency_by_stage.get(stage.id, 0.0), 3),
                    llm_total_tokens=llm_tokens_by_stage.get(stage.id, 0),
                    cost_usd=round(llm_cost_by_stage.get(stage.id, 0.0), 6),
                )
            )
            if stage.status == "sealed":
                sealed += 1

        total_tokens = sum(record.total_tokens for record in usage)
        cost_usd = sum(getattr(cost, "total_cost_usd", 0.0) or 0.0 for cost in costs)
        llm_latency = sum(invocation.latency_ms or 0 for invocation in invocations if invocation.latency_ms)

        return RunQualityMetrics(
            run_id=run_id,
            source_version_family=_family(run.source_version_family),
            target_version_family=_family(run.target_version_family),
            status=run.status,
            success=run.status in _SUCCESS_STATUSES,
            stage_count=len(stages),
            sealed_stage_count=sealed,
            repair_cycles=len(attempts),
            total_tokens=total_tokens,
            total_cost_usd=round(cost_usd, 6),
            llm_latency_ms=llm_latency,
            command_latency_ms=round(command_latency_total, 3),
            run_duration_seconds=round(_seconds(run.created_at, run.updated_at), 3)
            if _seconds(run.created_at, run.updated_at) is not None
            else None,
            stages=tuple(stage_metrics),
        )

    def rollup(self, *, source: str | None = None, target: str | None = None) -> list[QualityMetricRollup]:
        """Rolled up metrics per (source -> target) pair (F29-03)."""
        with self._session_scope() as session:
            runs = list(session.scalars(select(MigrationRunModel)).all())
            usage = list(session.scalars(select(LlmUsageRecordModel)).all())
            costs = list(session.scalars(select(UsageCostRecordModel)).all())
            attempts = list(session.scalars(select(RepairAttemptModel)).all())
            invocations = list(session.scalars(select(LlmInvocationModel)).all())
            commands = list(session.scalars(select(CommandExecutionModel)).all())
        usage_by_run: defaultdict[str, int] = defaultdict(int)
        for record in usage:
            usage_by_run[record.run_id] += record.total_tokens
        cost_by_run: defaultdict[str, float] = defaultdict(float)
        for cost in costs:
            cost_by_run[cost.run_id] += getattr(cost, "total_cost_usd", 0.0) or 0.0
        attempts_by_run: defaultdict[str, int] = defaultdict(int)
        for attempt in attempts:
            attempts_by_run[attempt.run_id] += 1
        llm_latency_by_run: defaultdict[str, float] = defaultdict(float)
        for invocation in invocations:
            if invocation.latency_ms:
                llm_latency_by_run[invocation.run_id] += invocation.latency_ms
        command_latency_by_run: defaultdict[str, float] = defaultdict(float)
        for command in commands:
            elapsed = _seconds(command.started_at, command.finished_at)
            if elapsed is not None:
                command_latency_by_run[command.run_id] += elapsed * 1000

        pairs: dict[str, dict[str, Any]] = {}
        for run in runs:
            source_family = _family(run.source_version_family)
            target_family = _family(run.target_version_family)
            if source and source_family != source:
                continue
            if target and target_family != target:
                continue
            key = f"{source_family} -> {target_family}"
            bucket = pairs.setdefault(
                key,
                {
                    "key": key,
                    "run_count": 0,
                    "success_count": 0,
                    "total_tokens": 0,
                    "total_cost_usd": 0.0,
                    "repair_cycles": 0,
                    "llm_latency_ms": 0.0,
                    "command_latency_ms": 0.0,
                },
            )
            bucket["run_count"] += 1
            if run.status in _SUCCESS_STATUSES:
                bucket["success_count"] += 1
            bucket["total_tokens"] += usage_by_run.get(run.id, 0)
            bucket["total_cost_usd"] += cost_by_run.get(run.id, 0.0)
            bucket["repair_cycles"] += attempts_by_run.get(run.id, 0)
            bucket["llm_latency_ms"] += llm_latency_by_run.get(run.id, 0.0)
            bucket["command_latency_ms"] += command_latency_by_run.get(run.id, 0.0)

        rollups = []
        for bucket in pairs.values():
            count = bucket["run_count"]
            rollups.append(
                QualityMetricRollup(
                    scope="pair",
                    key=bucket["key"],
                    run_count=count,
                    success_count=bucket["success_count"],
                    success_rate=round(bucket["success_count"] / count, 4) if count else 0.0,
                    total_tokens=bucket["total_tokens"],
                    total_cost_usd=round(bucket["total_cost_usd"], 6),
                    mean_repair_cycles=round(bucket["repair_cycles"] / count, 4) if count else 0.0,
                    mean_llm_latency_ms=round(bucket["llm_latency_ms"] / count, 3) if count else 0.0,
                    mean_command_latency_ms=round(bucket["command_latency_ms"] / count, 3) if count else 0.0,
                )
            )
        rollups.sort(key=lambda r: r.key)
        return rollups

    def trend(self, *, bucket: str = "day", since_days: int = 90) -> list[MetricTrendPoint]:
        """Trend reporting across runs bucketed by day/week (F29-04)."""
        window_start = datetime.now(UTC) - timedelta(days=since_days)
        with self._session_scope() as session:
            runs = list(
                session.scalars(
                    select(MigrationRunModel).order_by(MigrationRunModel.created_at)
                ).all()
            )
            usage = list(session.scalars(select(LlmUsageRecordModel)).all())
            costs = list(session.scalars(select(UsageCostRecordModel)).all())
            attempts = list(session.scalars(select(RepairAttemptModel)).all())
        usage_by_run: defaultdict[str, int] = defaultdict(int)
        for record in usage:
            usage_by_run[record.run_id] += record.total_tokens
        cost_by_run: defaultdict[str, float] = defaultdict(float)
        for cost in costs:
            cost_by_run[cost.run_id] += getattr(cost, "total_cost_usd", 0.0) or 0.0
        attempts_by_run: defaultdict[str, int] = defaultdict(int)
        for attempt in attempts:
            attempts_by_run[attempt.run_id] += 1

        buckets: dict[str, dict[str, Any]] = {}
        for run in runs:
            if run.created_at is None:
                continue
            created = run.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            created = created.astimezone(UTC)
            if created < window_start:
                continue
            if bucket == "week":
                iso = created.isocalendar()
                key = f"{iso.year}-W{iso.week:02d}"
                measured_at = created
            else:
                key = created.date().isoformat()
                measured_at = created
            b = buckets.setdefault(key, {"run_count": 0, "success_count": 0, "total_tokens": 0,
                                         "total_cost_usd": 0.0, "repair_cycles": 0, "measured_at": measured_at})
            b["run_count"] += 1
            if run.status in _SUCCESS_STATUSES:
                b["success_count"] += 1
            b["total_tokens"] += usage_by_run.get(run.id, 0)
            b["total_cost_usd"] += cost_by_run.get(run.id, 0.0)
            b["repair_cycles"] += attempts_by_run.get(run.id, 0)

        points = []
        for key, b in sorted(buckets.items()):
            count = b["run_count"]
            points.append(
                MetricTrendPoint(
                    bucket=key,
                    run_count=count,
                    success_count=b["success_count"],
                    success_rate=round(b["success_count"] / count, 4) if count else 0.0,
                    total_tokens=b["total_tokens"],
                    total_cost_usd=round(b["total_cost_usd"], 6),
                    mean_repair_cycles=round(b["repair_cycles"] / count, 4) if count else 0.0,
                    measured_at=b["measured_at"],
                )
            )
        return points
