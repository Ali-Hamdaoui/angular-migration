from datetime import UTC, datetime, timedelta

from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.repositories.models import (
    Base,
    CommandExecutionModel,
    CompatibilityResolutionModel,
    LlmInvocationModel,
    MigrationRunModel,
    RepairAttemptModel,
    UsageCostRecordModel,
    WorkflowEventModel,
)
from app.api.routes import runs as run_routes
from app.main import app
from app.services.run_timing_service import RunTimingService
from app.services.workflow_projection_service import WorkflowProjectionService


RUN_ID = "run-timing-1"
START = datetime(2026, 8, 9, 10, 0, tzinfo=UTC)
FINISH = START + timedelta(minutes=12)


def _session(tmp_path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'timing.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _run(*, status: str = "COMPLETED") -> MigrationRunModel:
    return MigrationRunModel(
        id=RUN_ID,
        status=status,
        run_phase="STAGED_MIGRATION",
        phase_status="completed" if status == "COMPLETED" else "running",
        approval_status="approved",
        repair_status="not_required",
        state_version=4,
        created_at=START - timedelta(hours=1),
        updated_at=FINISH + timedelta(hours=1),
    )


def _event(event_id: str, event_type: str, sequence: int, occurred_at: datetime, *, stage_id: str | None = None) -> WorkflowEventModel:
    return WorkflowEventModel(
        id=event_id,
        run_id=RUN_ID,
        stage_id=stage_id,
        event_type=event_type,
        idempotency_key=event_id,
        actor="test",
        reason="timing fixture",
        sequence=sequence,
        payload={"stage_id": stage_id} if stage_id else {},
        occurred_at=occurred_at,
    )


def _resolution(route: list[dict[str, str]]) -> CompatibilityResolutionModel:
    return CompatibilityResolutionModel(
        id="resolution-1",
        run_id=RUN_ID,
        idempotency_key="resolution-1",
        request_checksum="sha256:request",
        actor="test",
        status="supported",
        catalogue_version="catalogue-1",
        catalogue_checksum="sha256:catalogue",
        registry_snapshot_id="registry-1",
        registry_snapshot_checksum="sha256:registry",
        registry_snapshot={},
        runtime_candidates=[],
        source_exact="18.0.0",
        source_family="angular-18.x",
        target_family="angular-21.x",
        support_level="supported",
        route=route,
        selected_profile=None,
        blockers=[],
        warnings=[],
        package={"route": route},
        package_checksum="sha256:package",
        artifact_set_checksum="sha256:artifacts",
        artifact_ids=[],
        artifact_checksums={},
        state_version=4,
        event_sequence=4,
        created_at=START,
        updated_at=START,
    )


def _command(command_id: str, *, status: str, started_at: datetime | None, finished_at: datetime | None, key: str | None = None) -> CommandExecutionModel:
    return CommandExecutionModel(
        id=command_id,
        run_id=RUN_ID,
        idempotency_key=key or command_id,
        executable="npm",
        arguments=["run", "test"],
        status=status,
        requested_at=START,
        started_at=started_at,
        finished_at=finished_at,
    )


def _llm(invocation_id: str, *, task_type: str, latency_ms: int | None, started_at: datetime, completed_at: datetime | None, status: str = "completed") -> LlmInvocationModel:
    return LlmInvocationModel(
        id=invocation_id,
        run_id=RUN_ID,
        idempotency_key=invocation_id,
        request_checksum="sha256:request",
        input_hashes=[],
        correlation_id=invocation_id,
        actor="transformer",
        role="proposer",
        task_type=task_type,
        provider="azure_openai",
        deployment_alias="deployment",
        prompt_version="prompt",
        schema_version="schema",
        pricing_version="pricing",
        status=status,
        artifact_ids=[],
        artifact_checksums={},
        state_version=1,
        event_sequence=1,
        retries=0,
        latency_ms=latency_ms,
        started_at=started_at,
        completed_at=completed_at,
        created_at=started_at,
    )


def _repair(attempt_id: str, *, status: str, created_at: datetime, completed_at: datetime | None) -> RepairAttemptModel:
    return RepairAttemptModel(
        id=attempt_id,
        run_id=RUN_ID,
        stage_id="stage-1",
        attempt_number=int(attempt_id.rsplit("-", 1)[-1]) if attempt_id.rsplit("-", 1)[-1].isdigit() else 1,
        state_version=1,
        status=status,
        risk_level="low",
        created_at=created_at,
        completed_at=completed_at,
    )


def _route(stage_ids: list[str]) -> list[dict[str, str]]:
    return [
        {
            "stage_id": stage_id,
            "source_family": f"angular-{18 + index}.x",
            "target_family": f"angular-{19 + index}.x",
        }
        for index, stage_id in enumerate(stage_ids)
    ]


def test_completed_total_uses_semantic_start_and_finish_events(tmp_path) -> None:
    session = _session(tmp_path)
    session.add(_run())
    session.add_all(
        [
            _event("created", "RUN_CREATED", 1, START - timedelta(hours=1)),
            _event("accepted", "RUN_START_ACCEPTED", 2, START),
            _event("completed", "STAGED_MIGRATION_COMPLETED", 3, FINISH),
        ]
    )
    session.commit()

    timing = RunTimingService().build(session, RUN_ID, as_of=FINISH + timedelta(minutes=1))

    assert timing.started_at == START
    assert timing.finished_at == FINISH
    assert timing.total_duration_seconds == 720.0
    assert timing.total_measurement_status == "complete"


def test_running_total_uses_one_supplied_as_of_without_mutation(tmp_path) -> None:
    session = _session(tmp_path)
    session.add(_run(status="RUNNING"))
    session.add(_event("accepted", "RUN_START_ACCEPTED", 1, START))
    session.commit()
    before = {table.name: session.scalar(select(func.count()).select_from(table)) for table in Base.metadata.sorted_tables}

    timing = RunTimingService().build(session, RUN_ID, as_of=START + timedelta(minutes=5))

    after = {table.name: session.scalar(select(func.count()).select_from(table)) for table in Base.metadata.sorted_tables}
    assert timing.total_duration_seconds == 300.0
    assert timing.finished_at is None
    assert timing.total_measurement_status == "running"
    assert before == after
    assert not session.new and not session.dirty and not session.deleted


def test_not_started_run_is_unavailable_and_does_not_use_created_at(tmp_path) -> None:
    session = _session(tmp_path)
    session.add(_run(status="CREATED"))
    session.commit()

    timing = RunTimingService().build(session, RUN_ID, as_of=FINISH)

    assert timing.started_at is None
    assert timing.finished_at is None
    assert timing.total_duration_seconds is None
    assert timing.total_measurement_status == "unavailable"


def test_terminal_run_without_semantic_finish_is_unavailable(tmp_path) -> None:
    session = _session(tmp_path)
    session.add(_run(status="COMPLETED"))
    session.add(_event("accepted", "RUN_START_ACCEPTED", 1, START))
    session.commit()

    timing = RunTimingService().build(session, RUN_ID, as_of=FINISH + timedelta(days=1))

    assert timing.total_duration_seconds is None
    assert timing.total_measurement_status == "unavailable"


def test_stages_follow_dynamic_approved_route_and_authoritative_events(tmp_path) -> None:
    session = _session(tmp_path)
    route = _route(["stage-a", "stage-b", "stage-c", "stage-d"])
    session.add_all([_run(status="RUNNING"), _resolution(route)])
    stage_a = "stage-a--" + ""  # replaced below by the service's route identity
    from app.services.planning_application_service import run_scoped_stage_id

    stage_a = run_scoped_stage_id(RUN_ID, "stage-a")
    stage_b = run_scoped_stage_id(RUN_ID, "stage-b")
    session.add_all(
        [
            _event("accepted", "RUN_START_ACCEPTED", 1, START),
            _event("stage-a-created", "STAGE_CREATED", 2, START + timedelta(minutes=1), stage_id=stage_a),
            _event("stage-a-sealed", "STAGE_SEALED", 3, START + timedelta(minutes=3), stage_id=stage_a),
            _event("stage-b-created", "STAGE_CREATED", 4, START + timedelta(minutes=4), stage_id=stage_b),
        ]
    )
    session.commit()

    timing = RunTimingService().build(session, RUN_ID, as_of=START + timedelta(minutes=7))

    assert [item.label for item in timing.stages] == ["Angular 18 → 19", "Angular 19 → 20", "Angular 20 → 21", "Angular 21 → 22"]
    assert [item.status for item in timing.stages] == ["completed", "running", "not_started", "not_started"]
    assert timing.stages[0].duration_seconds == 120.0
    assert timing.stages[1].duration_seconds == 180.0


def test_commands_include_failed_and_retried_runtime_but_invalid_intervals_are_partial(tmp_path) -> None:
    session = _session(tmp_path)
    session.add(_run(status="COMPLETED"))
    session.add_all(
        [
            _command("failed", status="failed", started_at=START, finished_at=START + timedelta(seconds=10)),
            _command("retry", status="succeeded", started_at=START + timedelta(seconds=12), finished_at=START + timedelta(seconds=32)),
            _command("inverted", status="failed", started_at=START + timedelta(seconds=40), finished_at=START + timedelta(seconds=39)),
        ]
    )
    session.commit()

    timing = RunTimingService().build(session, RUN_ID, as_of=FINISH)

    assert timing.activity.commands.duration_seconds == 30.0
    assert timing.activity.commands.measured_count == 2
    assert timing.activity.commands.unmeasured_count == 1
    assert timing.activity.commands.measurement_status == "partial"


def test_llm_uses_latency_or_positive_timestamp_fallback_and_excludes_assistant_diagnostics(tmp_path) -> None:
    session = _session(tmp_path)
    session.add(_run(status="COMPLETED"))
    session.add_all(
        [
            _llm("latency", task_type="repair_proposal", latency_ms=2500, started_at=START, completed_at=START),
            _llm("fallback", task_type="repair_review", latency_ms=None, started_at=START, completed_at=START + timedelta(seconds=4)),
            _llm("unmeasured", task_type="repair_review", latency_ms=0, started_at=START, completed_at=START),
            _llm("assistant", task_type="assistant_response", latency_ms=9000, started_at=START, completed_at=START + timedelta(seconds=9)),
            _llm("smoke", task_type="smoke_check", latency_ms=9000, started_at=START, completed_at=START + timedelta(seconds=9)),
            _llm("failed", task_type="repair_reviewer", latency_ms=1000, started_at=START, completed_at=START, status="failed"),
        ]
    )
    session.commit()

    timing = RunTimingService().build(session, RUN_ID, as_of=FINISH)

    assert timing.activity.llm.duration_seconds == 7.5
    assert timing.activity.llm.measured_count == 3
    assert timing.activity.llm.unmeasured_count == 1
    assert timing.activity.llm.measurement_status == "partial"


def test_gate_wait_pairs_revisions_and_current_pending_lifecycle_in_sequence_order(tmp_path) -> None:
    session = _session(tmp_path)
    session.add(_run(status="RUNNING"))
    session.add_all(
        [
            _event("accepted", "RUN_START_ACCEPTED", 1, START),
            _event("g02-created-1", "G02_CREATED", 2, START + timedelta(seconds=1)),
            _event("g02-stale", "G02_STALE", 3, START + timedelta(seconds=4)),
            _event("g02-created-2", "G02_CREATED", 4, START + timedelta(seconds=5)),
            _event("g02-approved", "G02_APPROVED", 5, START + timedelta(seconds=9)),
            _event("g12-created", "G12_CREATED", 6, START + timedelta(seconds=10)),
        ]
    )
    session.commit()

    timing = RunTimingService().build(session, RUN_ID, as_of=START + timedelta(seconds=20))

    assert timing.activity.human_approval_wait.duration_seconds == 17.0
    assert timing.activity.human_approval_wait.measured_count == 2
    assert timing.activity.human_approval_wait.active_count == 1
    assert timing.activity.human_approval_wait.unmeasured_count == 0


def test_repair_counts_completed_active_and_unmeasured_attempts_without_updated_at_fallback(tmp_path) -> None:
    session = _session(tmp_path)
    session.add(_run(status="RUNNING"))
    session.add_all(
        [
            _repair("completed-1", status="superseded", created_at=START, completed_at=START + timedelta(seconds=8)),
            _repair("active-2", status="proposed", created_at=START + timedelta(seconds=10), completed_at=None),
            _repair("missing-finish-3", status="completed", created_at=START + timedelta(seconds=12), completed_at=None),
        ]
    )
    session.commit()

    timing = RunTimingService().build(session, RUN_ID, as_of=START + timedelta(seconds=20))

    assert timing.activity.repair.duration_seconds == 18.0
    assert timing.activity.repair.measured_count == 1
    assert timing.activity.repair.active_count == 1
    assert timing.activity.repair.unmeasured_count == 1


def test_validation_is_cumulative_subset_of_command_runtime(tmp_path) -> None:
    session = _session(tmp_path)
    session.add(_run(status="COMPLETED"))
    session.add_all(
        [
            _command("normal", status="succeeded", started_at=START, finished_at=START + timedelta(seconds=10)),
            _command("validation-1", status="failed", started_at=START + timedelta(seconds=12), finished_at=START + timedelta(seconds=20), key="cont:validation:attempt:tests:tests"),
            _command("validation-2", status="succeeded", started_at=START + timedelta(seconds=22), finished_at=START + timedelta(seconds=27), key="cont:validation:attempt:builds:builds"),
        ]
    )
    session.commit()

    timing = RunTimingService().build(session, RUN_ID, as_of=FINISH)

    assert timing.activity.commands.duration_seconds == 23.0
    assert timing.activity.validation.duration_seconds == 13.0
    assert timing.activity.validation.measurement_status == "complete"


def test_sealing_uses_latest_accepted_g11_or_g12_approval_and_active_as_of(tmp_path) -> None:
    session = _session(tmp_path)
    route = _route(["stage-a", "stage-b"])
    session.add_all([_run(status="RUNNING"), _resolution(route)])
    from app.services.planning_application_service import run_scoped_stage_id

    stage_a = run_scoped_stage_id(RUN_ID, "stage-a")
    stage_b = run_scoped_stage_id(RUN_ID, "stage-b")
    session.add_all(
        [
            _event("accepted", "RUN_START_ACCEPTED", 1, START),
            _event("stage-a-created", "STAGE_CREATED", 2, START + timedelta(seconds=1), stage_id=stage_a),
            _event("g11-created", "G11_CREATED", 3, START + timedelta(seconds=2), stage_id=stage_a),
            _event("g11-approved", "G11_APPROVED", 4, START + timedelta(seconds=5), stage_id=stage_a),
            _event("g12-created", "G12_CREATED", 5, START + timedelta(seconds=6), stage_id=stage_a),
            _event("g12-approved", "G12_APPROVED", 6, START + timedelta(seconds=9), stage_id=stage_a),
            _event("stage-a-sealed", "STAGE_SEALED", 7, START + timedelta(seconds=14), stage_id=stage_a),
            _event("stage-b-created", "STAGE_CREATED", 8, START + timedelta(seconds=15), stage_id=stage_b),
            _event("g11-b-approved", "G11_APPROVED", 9, START + timedelta(seconds=17), stage_id=stage_b),
        ]
    )
    session.commit()

    timing = RunTimingService().build(session, RUN_ID, as_of=START + timedelta(seconds=20))

    assert timing.activity.sealing.duration_seconds == 8.0
    assert timing.activity.sealing.measured_count == 1
    assert timing.activity.sealing.active_count == 1


def test_repeated_builds_are_read_only_and_stable_for_fixed_as_of(tmp_path) -> None:
    session = _session(tmp_path)
    session.add(_run(status="RUNNING"))
    session.add(_event("accepted", "RUN_START_ACCEPTED", 1, START))
    session.commit()
    before = {table.name: session.scalar(select(func.count()).select_from(table)) for table in Base.metadata.sorted_tables}

    first = RunTimingService().build(session, RUN_ID, as_of=START + timedelta(minutes=2))
    second = RunTimingService().build(session, RUN_ID, as_of=START + timedelta(minutes=2))

    after = {table.name: session.scalar(select(func.count()).select_from(table)) for table in Base.metadata.sorted_tables}
    assert first == second
    assert before == after


def test_workflow_projection_delegates_timing_and_preserves_usage_aggregation(tmp_path) -> None:
    session = _session(tmp_path)
    session.add(_run(status="COMPLETED"))
    invocation = _llm("usage-invocation", task_type="repair_proposal", latency_ms=1000, started_at=START, completed_at=START + timedelta(seconds=1))
    session.add(invocation)
    session.add(
        UsageCostRecordModel(
            id="usage-1",
            invocation_id=invocation.id,
            run_id=RUN_ID,
            stage_id=None,
            pricing_version="pricing",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            input_price_per_million=1.0,
            output_price_per_million=2.0,
            input_cost_usd=0.01,
            output_cost_usd=0.02,
            total_cost_usd=0.03,
            created_at=START,
        )
    )
    session.add_all(
        [
            _event("accepted", "RUN_START_ACCEPTED", 1, START),
            _event("completed", "STAGED_MIGRATION_COMPLETED", 2, FINISH),
        ]
    )
    session.commit()

    projection = WorkflowProjectionService().build(session, RUN_ID)

    assert projection.operational_statistics.run_start_timestamp == START
    assert projection.operational_statistics.recorded_workflow_duration_seconds == 720.0
    assert projection.operational_statistics.current_active_run_age_seconds is None
    assert projection.operational_statistics.total_tokens == 15
    assert projection.operational_statistics.total_cost_usd == 0.03


def test_timing_route_returns_typed_projection_and_404_envelope(tmp_path, monkeypatch) -> None:
    session = _session(tmp_path)
    session.add(_run(status="COMPLETED"))
    session.add_all(
        [
            _event("accepted", "RUN_START_ACCEPTED", 1, START),
            _event("completed", "STAGED_MIGRATION_COMPLETED", 2, FINISH),
        ]
    )
    session.commit()

    @contextmanager
    def scope():
        yield session

    monkeypatch.setattr(run_routes, "session_scope", scope)
    client = TestClient(app)

    response = client.get(f"/api/v1/runs/{RUN_ID}/timing")
    missing = client.get("/api/v1/runs/missing/timing")

    assert response.status_code == 200
    assert response.json()["total_duration_seconds"] == 720.0
    assert response.json()["activity"]["commands"]["duration_seconds"] is None
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "RUN_NOT_FOUND"
