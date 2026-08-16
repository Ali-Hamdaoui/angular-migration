"""Tests for F29 quality and cost metrics."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
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
from app.services.quality_metrics_service import QualityMetricError, QualityMetricsService

NOW = datetime.now(UTC)
client = TestClient(app)


def _seed_run(run_id: str, *, status: str = "COMPLETED", source: str = "angular-11.x", target: str = "angular-14.x") -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status=status, run_phase="initialized",
                                      source_version_family=source, target_version_family=target,
                                      created_at=NOW - timedelta(hours=1), updated_at=NOW))
        for order in (1, 2, 3):
            session.add(MigrationStageModel(id=f"stage-{run_id}-{order}", run_id=run_id, stage_order=order,
                                            source_version_family=f"angular-{10+order}.x",
                                            target_version_family=f"angular-{11+order}.x",
                                            source_angular_version=f"{10+order}.0.0",
                                            target_angular_version=f"{11+order}.0.0",
                                            status="sealed" if order < 3 else "planned", created_at=NOW))
        session.add(LlmUsageRecordModel(id=f"usage-{run_id}", run_id=run_id, model="gpt-x",
                                        input_tokens=100, output_tokens=50, total_tokens=150,
                                        input_price_per_million=1.0, output_price_per_million=2.0,
                                        cost_usd=0.0002, created_at=NOW))
        session.add(UsageCostRecordModel(id=f"cost-{run_id}", invocation_id=f"inv-{run_id}",
                                         run_id=run_id, pricing_version="v1", input_tokens=100,
                                         output_tokens=50, total_tokens=150, input_price_per_million=1.0,
                                         output_price_per_million=2.0, input_cost_usd=0.0001,
                                         output_cost_usd=0.0001, total_cost_usd=0.0002, created_at=NOW))
        session.add(LlmInvocationModel(id=f"inv-{run_id}", run_id=run_id, idempotency_key=f"invkey-{run_id}",
                                       request_checksum="sha256:" + "1" * 64, correlation_id="corr",
                                       actor="operator", role="assistant", task_type="repair_proposal",
                                       provider="mock", deployment_alias="mock", prompt_version="v1",
                                       schema_version="v1", status="succeeded", latency_ms=250,
                                       state_version=1, event_sequence=1, started_at=NOW - timedelta(minutes=1),
                                       completed_at=NOW, created_at=NOW))
        session.add(RepairAttemptModel(id=f"repair-{run_id}", run_id=run_id, stage_id=f"stage-{run_id}-2",
                                       attempt_number=1, status="completed", risk_level="low",
                                       created_at=NOW - timedelta(minutes=30), completed_at=NOW))
        session.add(CommandExecutionModel(id=f"exec-{run_id}", run_id=run_id, stage_id=f"stage-{run_id}-2",
                                          command_id="npm-ci-bootstrap", executable="npm", arguments=["ci"],
                                          status="succeeded", requested_at=NOW - timedelta(minutes=5),
                                          started_at=NOW - timedelta(minutes=5), finished_at=NOW,
                                          operation_kind="read_only", state_version=1, event_sequence=1)
                  )
        session.commit()


def test_collect_run_metrics():
    run_id = f"run-f29-{uuid4().hex[:8]}"
    _seed_run(run_id)
    service = QualityMetricsService()
    metrics = service.collect_run(run_id)
    assert metrics.success is True
    assert metrics.stage_count == 3
    assert metrics.sealed_stage_count == 2
    assert metrics.repair_cycles == 1
    assert metrics.total_tokens == 150
    assert metrics.total_cost_usd == 0.0002
    assert metrics.llm_latency_ms == 250
    assert metrics.command_latency_ms > 0
    assert metrics.run_duration_seconds is not None
    assert len(metrics.stages) == 3
    assert metrics.stages[1].repair_cycles == 1
    assert metrics.stages[1].command_latency_ms > 0


def test_collect_failed_run():
    run_id = f"run-f29-{uuid4().hex[:8]}"
    _seed_run(run_id, status="FAILED")
    service = QualityMetricsService()
    metrics = service.collect_run(run_id)
    assert metrics.success is False


def test_collect_unknown_run_raises():
    service = QualityMetricsService()
    try:
        service.collect_run("run-missing")
        assert False, "expected RUN_NOT_FOUND"
    except QualityMetricError as exc:
        assert exc.code == "RUN_NOT_FOUND"


def test_collection_is_deterministic():
    run_id = f"run-f29-{uuid4().hex[:8]}"
    _seed_run(run_id)
    service = QualityMetricsService()
    first = service.collect_run(run_id)
    second = service.collect_run(run_id)
    assert first.total_tokens == second.total_tokens
    assert first.repair_cycles == second.repair_cycles
    assert first.command_latency_ms == second.command_latency_ms
    assert [s.stage_order for s in first.stages] == [s.stage_order for s in second.stages]


def test_rollup_by_pair():
    source = "angular-30.x"
    target = "angular-33.x"
    run_id = f"run-f29-{uuid4().hex[:8]}"
    _seed_run(run_id, source=source, target=target)
    run_id2 = f"run-f29-{uuid4().hex[:8]}"
    _seed_run(run_id2, status="FAILED", source=source, target=target)
    service = QualityMetricsService()
    rollups = service.rollup()
    pair = next(r for r in rollups if r.key == f"{source} -> {target}")
    assert pair.run_count == 2
    assert pair.success_count == 1
    assert pair.success_rate == 0.5
    assert pair.total_tokens == 300
    assert pair.mean_repair_cycles == 1.0


def test_rollup_filtered_by_source():
    run_id = f"run-f29-{uuid4().hex[:8]}"
    _seed_run(run_id)
    service = QualityMetricsService()
    rollups = service.rollup(source="angular-11.x")
    assert any(r.key == "angular-11.x -> angular-14.x" for r in rollups)
    rollups_other = service.rollup(source="angular-20.x")
    assert rollups_other == []


def test_trend_buckets_by_day():
    run_id = f"run-f29-{uuid4().hex[:8]}"
    _seed_run(run_id)
    service = QualityMetricsService()
    points = service.trend(bucket="day")
    assert points
    today = datetime.now(UTC).date().isoformat()
    point = next(p for p in points if p.bucket == today)
    assert point.run_count >= 1
    assert point.success_count >= 1
    assert point.total_tokens >= 150


def test_api_run_metrics():
    run_id = f"run-f29-{uuid4().hex[:8]}"
    _seed_run(run_id)
    response = client.get(f"/runs/{run_id}/quality-metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["total_tokens"] == 150
    assert body["repair_cycles"] == 1
    assert len(body["stages"]) == 3


def test_api_rollup_and_trend():
    run_id = f"run-f29-{uuid4().hex[:8]}"
    _seed_run(run_id)
    rollup = client.get("/quality-metrics/rollup")
    assert rollup.status_code == 200
    assert rollup.json()["rollups"]

    trend = client.get("/quality-metrics/trend?bucket=day")
    assert trend.status_code == 200
    assert trend.json()["points"]


def test_api_unknown_run_404():
    response = client.get("/runs/run-missing/quality-metrics")
    assert response.status_code == 404
    assert response.json()["error_code"] == "RUN_NOT_FOUND"
