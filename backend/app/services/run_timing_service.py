"""Read-only timing projection over persisted migration workflow evidence."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.domain.contracts import (
    RunStatus,
    RunTimingActivityDto,
    RunTimingDto,
    TimingActivityDto,
    TimingSpanDto,
)
from app.repositories.models import (
    CommandExecutionModel,
    CompatibilityResolutionModel,
    LlmInvocationModel,
    MigrationRunModel,
    RepairAttemptModel,
    WorkflowEventModel,
)
from app.services.planning_application_service import run_scoped_stage_id
from app.services.repair_lifecycle_service import ACTIVE_REPAIR_STATUSES


_TERMINAL_STATUSES = frozenset(
    {"COMPLETED", "CANCELLED", "FAILED", "TIMED_OUT", "WORKER_LOST", "ORPHANED", "CLEANUP_FAILED"}
)
_GATE_TERMINALS = frozenset({"APPROVED", "REJECTED", "MODIFICATION_REQUESTED", "STALE"})
_LLM_EXCLUDED_TASKS = frozenset({"assistant_response", "smoke_check"})
_ACTIVE_COMMAND_STATUSES = frozenset({"queued", "pending", "running"})
_FAILED_TERMINAL_EVENTS = frozenset(
    {"SOURCE_INTAKE_FAILED", "PLANNING_FAILED", "TRANSFORMATION_CONTINUATION_FAILED", "STAGE_VALIDATION_FAILED"}
)


class RunTimingError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 404) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _interval(start: datetime | None, end: datetime | None) -> float | None:
    start_utc = _utc(start)
    end_utc = _utc(end)
    if start_utc is None or end_utc is None or end_utc <= start_utc:
        return None
    return (end_utc - start_utc).total_seconds()


def _status_value(value: object) -> str:
    return str(getattr(value, "value", value)).upper()


def _event_scope(event: WorkflowEventModel) -> str | None:
    if event.stage_id:
        return str(event.stage_id)
    payload = event.payload or {}
    scope = payload.get("stage_id")
    return str(scope) if scope else None


def _activity(duration: float, measured: int, unmeasured: int, active: int) -> TimingActivityDto:
    if not measured and not unmeasured and not active:
        return TimingActivityDto(
            duration_seconds=None,
            measured_count=0,
            unmeasured_count=0,
            active_count=0,
            measurement_status="unavailable",
        )
    return TimingActivityDto(
        duration_seconds=duration or None,
        measured_count=measured,
        unmeasured_count=unmeasured,
        active_count=active,
        measurement_status="partial" if unmeasured or active else "complete",
    )


def _event_time(events: list[WorkflowEventModel], event_type: str) -> datetime | None:
    times = [_utc(event.occurred_at) for event in events if event.event_type == event_type]
    return min((value for value in times if value is not None), default=None)


def _first_event(events: list[WorkflowEventModel], event_types: set[str]) -> WorkflowEventModel | None:
    return next((event for event in events if event.event_type in event_types), None)


def _label(route_item: dict[str, Any]) -> str:
    source = route_item.get("source_family") or route_item.get("source_version_family")
    target = route_item.get("target_family") or route_item.get("target_version_family")
    if source and target:
        source_major = str(source).removeprefix("angular-").removesuffix(".x")
        target_major = str(target).removeprefix("angular-").removesuffix(".x")
        return f"Angular {source_major} → {target_major}"
    return str(route_item.get("stage_id") or "Stage")


def _route(resolution: CompatibilityResolutionModel | None) -> list[dict[str, Any]]:
    if resolution is None:
        return []
    return [item for item in (resolution.route or []) if isinstance(item, dict) and item.get("stage_id")]


def _gate_activity(
    events: list[WorkflowEventModel],
    *,
    started_at: datetime | None,
    as_of: datetime,
    terminal: bool,
) -> TimingActivityDto:
    if started_at is None:
        return _activity(0.0, 0, 0, 0)
    start_sequence = next((event.sequence for event in events if event.event_type == "RUN_START_ACCEPTED"), None)
    opened: defaultdict[tuple[str, str | None], deque[WorkflowEventModel]] = defaultdict(deque)
    duration = 0.0
    measured = unmeasured = active = 0
    for event in events:
        if start_sequence is not None and event.sequence < start_sequence:
            continue
        parts = event.event_type.split("_", 1)
        if len(parts) != 2 or not parts[0].startswith("G") or not parts[0][1:].isdigit():
            continue
        gate_number = int(parts[0][1:])
        if gate_number < 2 or gate_number > 12:
            continue
        key = (parts[0], _event_scope(event))
        if parts[1] == "CREATED":
            opened[key].append(event)
        elif parts[1] in _GATE_TERMINALS:
            if not opened[key]:
                unmeasured += 1
                continue
            created = opened[key].popleft()
            elapsed = _interval(created.occurred_at, event.occurred_at)
            if elapsed is None:
                unmeasured += 1
            else:
                measured += 1
                duration += elapsed
    for pending in opened.values():
        for created in pending:
            elapsed = _interval(created.occurred_at, as_of)
            if elapsed is None or terminal:
                unmeasured += 1
            else:
                active += 1
                duration += elapsed
    return _activity(duration, measured, unmeasured, active)


def _command_activity(
    commands: list[CommandExecutionModel], *, as_of: datetime, validation_only: bool = False
) -> TimingActivityDto:
    duration = 0.0
    measured = unmeasured = active = 0
    for command in commands:
        is_validation = ":validation:" in (command.idempotency_key or "")
        if validation_only and not is_validation:
            continue
        elapsed = _interval(command.started_at, command.finished_at)
        if elapsed is not None:
            measured += 1
            duration += elapsed
        elif _status_value(command.status).lower() in _ACTIVE_COMMAND_STATUSES and command.started_at:
            elapsed = _interval(command.started_at, as_of)
            if elapsed is None:
                unmeasured += 1
            else:
                active += 1
                duration += elapsed
        else:
            unmeasured += 1
    return _activity(duration, measured, unmeasured, active)


def _llm_activity(invocations: list[LlmInvocationModel]) -> TimingActivityDto:
    duration = 0.0
    measured = unmeasured = active = 0
    for invocation in invocations:
        if str(invocation.task_type).lower() in _LLM_EXCLUDED_TASKS:
            continue
        elapsed = None
        if invocation.latency_ms is not None and invocation.latency_ms > 0:
            elapsed = invocation.latency_ms / 1000
        if elapsed is None:
            elapsed = _interval(invocation.started_at, invocation.completed_at)
        if elapsed is not None:
            measured += 1
            duration += elapsed
        elif str(invocation.status).lower() in {"queued", "pending", "in_progress", "running"}:
            active += 1
        else:
            unmeasured += 1
    return _activity(duration, measured, unmeasured, active)


def _repair_activity(attempts: list[RepairAttemptModel], *, as_of: datetime) -> TimingActivityDto:
    duration = 0.0
    measured = unmeasured = active = 0
    for attempt in attempts:
        end = attempt.completed_at
        is_active = end is None and str(attempt.status).lower() in ACTIVE_REPAIR_STATUSES
        if is_active:
            end = as_of
        elapsed = _interval(attempt.created_at, end)
        if elapsed is None:
            unmeasured += 1
        elif is_active:
            active += 1
            duration += elapsed
        else:
            measured += 1
            duration += elapsed
    return _activity(duration, measured, unmeasured, active)


def _stage_events(events: list[WorkflowEventModel], stage_id: str) -> list[WorkflowEventModel]:
    return [event for event in events if _event_scope(event) == stage_id]


def _latest_active_approval(events: list[WorkflowEventModel], *, before_sequence: int | None = None) -> datetime | None:
    approvals: dict[str, datetime] = {}
    for event in events:
        if before_sequence is not None and event.sequence >= before_sequence:
            break
        parts = event.event_type.split("_", 1)
        if len(parts) != 2 or parts[0] not in {"G11", "G12"}:
            continue
        if parts[1] == "CREATED":
            approvals.pop(parts[0], None)
        elif parts[1] == "APPROVED":
            approvals[parts[0]] = _utc(event.occurred_at)  # type: ignore[assignment]
        elif parts[1] in _GATE_TERMINALS - {"APPROVED"}:
            approvals.pop(parts[0], None)
    return max(approvals.values(), default=None)


def _sealing_activity(
    events: list[WorkflowEventModel],
    stage_ids: list[str],
    *,
    as_of: datetime,
    terminal: bool,
) -> TimingActivityDto:
    duration = 0.0
    measured = unmeasured = active = 0
    for stage_id in stage_ids:
        scoped = _stage_events(events, stage_id)
        created = _first_event(scoped, {"STAGE_CREATED"})
        if created is None:
            continue
        sealed = _first_event(scoped, {"STAGE_SEALED"})
        scoped_after_created = [event for event in scoped if event.sequence >= created.sequence]
        approval = _latest_active_approval(scoped_after_created, before_sequence=sealed.sequence if sealed else None)
        if sealed is not None:
            elapsed = _interval(approval, sealed.occurred_at)
            if elapsed is None:
                unmeasured += 1
            else:
                measured += 1
                duration += elapsed
        elif approval is not None and not terminal:
            elapsed = _interval(approval, as_of)
            if elapsed is None:
                unmeasured += 1
            else:
                active += 1
                duration += elapsed
    return _activity(duration, measured, unmeasured, active)


def _span(
    key: str,
    label: str,
    start: datetime | None,
    finish: datetime | None,
    *,
    as_of: datetime,
    running: bool,
) -> TimingSpanDto:
    if start is None:
        return TimingSpanDto(key=key, label=label, status="not_started")
    if finish is None and running:
        elapsed = _interval(start, as_of)
        if elapsed is not None:
            return TimingSpanDto(key=key, label=label, status="running", started_at=start, duration_seconds=elapsed)
    if finish is None:
        return TimingSpanDto(key=key, label=label, status="unavailable", started_at=start)
    elapsed = _interval(start, finish)
    if elapsed is None:
        return TimingSpanDto(key=key, label=label, status="unavailable", started_at=start, finished_at=finish)
    return TimingSpanDto(key=key, label=label, status="completed", started_at=start, finished_at=finish, duration_seconds=elapsed)


class RunTimingService:
    def build(self, session, run_id: str, *, as_of: datetime | None = None) -> RunTimingDto:
        captured_as_of = _utc(as_of) if as_of is not None else datetime.now(UTC)
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise RunTimingError("RUN_NOT_FOUND", "Migration run does not exist.")

        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id).order_by(WorkflowEventModel.sequence)))
        commands = list(session.scalars(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id)))
        invocations = list(session.scalars(select(LlmInvocationModel).where(LlmInvocationModel.run_id == run_id)))
        attempts = list(session.scalars(select(RepairAttemptModel).where(RepairAttemptModel.run_id == run_id)))
        resolutions = list(
            session.scalars(
                select(CompatibilityResolutionModel)
                .where(CompatibilityResolutionModel.run_id == run_id, CompatibilityResolutionModel.status != "blocked")
                .order_by(CompatibilityResolutionModel.state_version.desc(), CompatibilityResolutionModel.created_at.desc())
            )
        )
        route = _route(resolutions[0] if resolutions else None)
        terminal = _status_value(run.status) in _TERMINAL_STATUSES
        started_at = _event_time(events, "RUN_START_ACCEPTED")
        terminal_types = {"STAGED_MIGRATION_COMPLETED"} if _status_value(run.status) == "COMPLETED" else (
            {"RUN_CANCELLED", "TRANSFORMATION_CANCELLED"} if _status_value(run.status) == "CANCELLED" else _FAILED_TERMINAL_EVENTS
        )
        finished_event = _first_event(events, terminal_types) if terminal else None
        finished_at = _utc(finished_event.occurred_at) if finished_event else None
        if started_at is None:
            total_duration = None
            total_status = "unavailable"
        elif finished_at is not None:
            total_duration = _interval(started_at, finished_at)
            total_status = "complete" if total_duration is not None else "unavailable"
        elif not terminal:
            total_duration = _interval(started_at, captured_as_of)
            total_status = "running" if total_duration is not None else "unavailable"
        else:
            total_duration = None
            total_status = "unavailable"

        phase_specs = (
            ("PREFLIGHT_SNAPSHOT", "Preflight & snapshot", "RUN_START_ACCEPTED", "DISCOVERY_STARTED"),
            ("DISCOVERY_BASELINE", "Discovery & baseline", "DISCOVERY_STARTED", "G04_APPROVED"),
            ("FEASIBILITY_PLANNING", "Feasibility & planning", "G04_APPROVED", "TRANSFORMATION_CONTINUATION_CREATED"),
            ("STAGED_MIGRATION", "Staged migration", "TRANSFORMATION_CONTINUATION_CREATED", "STAGED_MIGRATION_COMPLETED"),
        )
        phase_starts = {key: _event_time(events, start_type) for key, _label_value, start_type, _end_type in phase_specs}
        phases = []
        for index, (key, label, start_type, end_type) in enumerate(phase_specs):
            phase_end = _event_time(events, end_type)
            is_current = not terminal and phase_starts[key] is not None and phase_end is None and all(
                phase_starts[next_key] is None for next_key, *_ in phase_specs[index + 1 :]
            )
            phases.append(_span(key, label, phase_starts[key], phase_end, as_of=captured_as_of, running=is_current))

        stages = []
        stage_ids = []
        for item in route:
            stage_id = run_scoped_stage_id(run_id, str(item["stage_id"]))
            stage_ids.append(stage_id)
            scoped = _stage_events(events, stage_id)
            created = _first_event(scoped, {"STAGE_CREATED"})
            sealed = _first_event(scoped, {"STAGE_SEALED"})
            stages.append(
                _span(
                    stage_id,
                    _label(item),
                    _utc(created.occurred_at) if created else None,
                    _utc(sealed.occurred_at) if sealed else None,
                    as_of=captured_as_of,
                    running=not terminal and created is not None and sealed is None,
                )
            )

        activity = RunTimingActivityDto(
            llm=_llm_activity(invocations),
            commands=_command_activity(commands, as_of=captured_as_of),
            human_approval_wait=_gate_activity(events, started_at=started_at, as_of=captured_as_of, terminal=terminal),
            repair=_repair_activity(attempts, as_of=captured_as_of),
            validation=_command_activity(commands, as_of=captured_as_of, validation_only=True),
            sealing=_sealing_activity(events, stage_ids, as_of=captured_as_of, terminal=terminal),
        )
        return RunTimingDto(
            run_id=run_id,
            status=RunStatus(_status_value(run.status)),
            as_of=captured_as_of,
            started_at=started_at,
            finished_at=finished_at,
            total_duration_seconds=total_duration,
            total_measurement_status=total_status,
            activity=activity,
            phases=phases,
            stages=stages,
        )
