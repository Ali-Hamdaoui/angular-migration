"""Shared, read-only semantic projection for cross-phase Assistant consumers."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.contracts import (
    AssistantEvidenceReferenceDto,
    AssistantOperationalStatisticsDto,
    AssistantWorkflowProjectionDto,
    ProjectionValue,
)
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    ExecutionProfileModel,
    G02ApprovalModel,
    MigrationRunModel,
    MigrationStageModel,
    StageStepModel,
    SourceSnapshotModel,
    WorkflowEventModel,
)
from app.services.assistant_capabilities import build_next_step_proposals
from app.services.llm_evidence_application_service import aggregate_run_llm_usage

_PHASES = ["Preflight Snapshot", "Baseline", "Planning", "Transformation", "Validation", "Completion"]
_PHASE_LABELS = {
    "PREFLIGHT_SNAPSHOT": "Preflight Snapshot",
    "DISCOVERY_BASELINE": "Baseline",
    "FEASIBILITY_PLANNING": "Planning",
    "STAGED_MIGRATION": "Transformation",
    "FINAL_ASSURANCE": "Validation",
    "DELIVERY_REPORTING": "Completion",
}
_GATE_EVENT = re.compile(r"^(G\d{2})_(CREATED|APPROVED|REJECTED)$")


def _value(value, *, supported: bool = True) -> ProjectionValue:
    if not supported:
        return ProjectionValue(value=None, availability="unsupported")
    if value is None or value == "":
        return ProjectionValue(value=None, availability="unavailable")
    return ProjectionValue(value=value, availability="known")


def _seconds(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    if start.tzinfo is None and end.tzinfo is not None:
        start = start.replace(tzinfo=end.tzinfo)
    elif end.tzinfo is None and start.tzinfo is not None:
        end = end.replace(tzinfo=start.tzinfo)
    return max(0.0, (end - start).total_seconds())


def _application_name(source_path: str | None) -> str | None:
    if not source_path:
        return None
    parts = [part for part in re.split(r"[\\/]", source_path.rstrip("\\/")) if part]
    return parts[-1] if parts else None


def _event_detail(event: WorkflowEventModel | None) -> str | None:
    if event is None:
        return None
    payload = event.payload or {}
    return next(
        (
            str(value)
            for value in (
                payload.get("blocker"),
                payload.get("failure_reason"),
                payload.get("error_code"),
                payload.get("reason_code"),
                payload.get("error"),
                event.reason,
            )
            if value
        ),
        None,
    )


class WorkflowProjectionService:
    """Compose one query-ready projection from persisted run records and events."""

    def build(self, session, run_id: str) -> AssistantWorkflowProjectionDto:
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise ValueError("Migration run does not exist.")
        stages = list(session.scalars(select(MigrationStageModel).where(MigrationStageModel.run_id == run_id).order_by(MigrationStageModel.stage_order)))
        steps = list(session.scalars(select(StageStepModel).where(StageStepModel.run_id == run_id).order_by(StageStepModel.id)))
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id).order_by(WorkflowEventModel.sequence)))
        commands = list(session.scalars(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id).order_by(CommandExecutionModel.requested_at, CommandExecutionModel.id)))
        llm_usage = aggregate_run_llm_usage(session, run_id)
        artifacts = list(session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id).order_by(ArtifactMetadataModel.created_at, ArtifactMetadataModel.id)))
        snapshot = session.scalar(select(SourceSnapshotModel).where(SourceSnapshotModel.run_id == run_id).order_by(SourceSnapshotModel.created_at.desc()))
        g02 = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == run_id).order_by(G02ApprovalModel.updated_at.desc()))
        execution_profile = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.updated_at.desc()))

        current_stage = next((item for item in reversed(stages) if item.status not in {"PASSED", "COMPLETED", "CANCELLED"}), None) or (stages[-1] if stages else None)
        current_step = next((item for item in reversed(steps) if item.status not in {"PASSED", "COMPLETED", "CANCELLED"}), None)
        current_event = events[-1] if events else None
        terminal = str(run.status).upper() in {"COMPLETED", "CANCELLED", "FAILED", "TIMED_OUT", "WORKER_LOST", "ORPHANED", "CLEANUP_FAILED"}
        duration = _seconds(run.created_at, run.updated_at if terminal else max((item.occurred_at for item in events), default=None))

        counts: dict[str, int] = {}
        for command in commands:
            counts[command.status] = counts.get(command.status, 0) + 1
        role_counts = {item.key: item.calls for item in llm_usage.by_role}
        usage_available = llm_usage.usage_recorded_calls > 0
        stats = AssistantOperationalStatisticsDto(
            run_start_timestamp=run.created_at,
            recorded_workflow_duration_seconds=duration,
            current_active_run_age_seconds=None if terminal else _seconds(run.created_at, datetime.now(UTC)),
            stage_durations_seconds=(stage_durations := {item.id: value for item in stages if (value := _seconds(item.started_at, item.completed_at)) is not None}) or None,
            command_totals_by_status=counts or None,
            successful_commands=sum(value for key, value in counts.items() if key in {"succeeded", "completed"}) if commands else None,
            failed_commands=sum(value for key, value in counts.items() if key in {"failed", "timed_out", "rejected", "interrupted"}) if commands else None,
            relevant_command_ids=[item.id for item in commands],
            llm_calls_by_role=role_counts or None,
            input_tokens=llm_usage.input_tokens if usage_available else None,
            output_tokens=llm_usage.output_tokens if usage_available else None,
            total_tokens=llm_usage.total_tokens if usage_available else None,
            input_cost_usd=llm_usage.input_cost_usd if usage_available else None,
            output_cost_usd=llm_usage.output_cost_usd if usage_available else None,
            total_cost_usd=llm_usage.total_cost_usd if usage_available else None,
        )

        referenced_artifact_ids = [artifact_id for event in events for artifact_id in (event.payload.get("artifact_ids", []) if isinstance(event.payload.get("artifact_ids", []), list) else [])]
        if snapshot is not None and snapshot.status == "created":
            referenced_artifact_ids.extend(snapshot.artifact_ids or [])
        if g02 is not None and g02.status == "approved":
            referenced_artifact_ids.extend(g02.artifact_ids or [])
        if execution_profile is not None:
            referenced_artifact_ids.extend(execution_profile.artifact_ids or [])
        referenced_order = {artifact_id: index for index, artifact_id in enumerate(referenced_artifact_ids)}
        selected_artifacts = [item for item in artifacts if item.immutable and {item.id, item.id.removeprefix("metadata-")} & referenced_order.keys()]
        selected_artifacts.sort(key=lambda item: referenced_order.get(item.id, referenced_order.get(item.id.removeprefix("metadata-"), len(referenced_order))))
        evidence = [AssistantEvidenceReferenceDto(artifact_id=item.id, label=item.relative_path, checksum=item.checksum, run_id=item.run_id, stage_id=item.stage_id, category=item.artifact_type, lineage=item.owner_reference, immutable=item.immutable) for item in selected_artifacts]

        phase = _PHASE_LABELS.get(run.run_phase, run.run_phase)
        completed_work = [stage.id for stage in stages if stage.status in {"PASSED", "COMPLETED"}]
        if snapshot is not None and snapshot.status == "created":
            completed_work.append("Immutable source snapshot")
        if g02 is not None and g02.status == "approved":
            completed_work.append("G02 approval")
        for event in events:
            if event.event_type == "SNAPSHOT_CREATED" or event.event_type.endswith(("_COMPLETED", "_SUCCEEDED", "_APPROVED", "_VERIFIED")):
                completed_work.append(event.event_type.replace("_", " ").title())
        completed_work = list(dict.fromkeys(completed_work))
        try:
            remaining_work = _PHASES[_PHASES.index(phase) + 1 :]
        except ValueError:
            remaining_work = []

        latest_gate = next((match for event in reversed(events) if (match := _GATE_EVENT.match(event.event_type))), None)
        if latest_gate:
            gate_name, gate_state = latest_gate.groups()
            gate_pending = gate_state == "CREATED"
            gate_value = f"{gate_name} {'pending' if gate_pending else gate_state.lower()}"
        else:
            gate_value = run.approval_status if run.approval_status not in {None, "not_required"} else None
            gate_pending = str(gate_value).lower() in {"pending", "waiting_approval"}

        profile_blockers = list(execution_profile.blockers or []) if execution_profile is not None else []
        profile_guidance = list(execution_profile.guidance or []) if execution_profile is not None else []
        failed_event = next((event for event in reversed(events) if event.event_type.endswith(("_FAILED", "_BLOCKED", "_REJECTED"))), None)
        blocker_value = profile_blockers[0] if execution_profile is not None and execution_profile.status == "blocked" and profile_blockers else _event_detail(failed_event)
        failure_value = _event_detail(failed_event)
        waiting_reason = f"Human decision required for {gate_value.split()[0]}." if gate_pending and gate_value else None
        if gate_pending and gate_value:
            next_action = f"Review and decide {gate_value.split()[0]} through the governed cockpit control."
        elif blocker_value and profile_guidance:
            next_action = f"{profile_guidance[0]} Retry runtime-profile resolution."
        elif terminal:
            next_action = "Review final evidence and reporting."
        elif phase == "Preflight Snapshot":
            next_action = "Continue the governed source-intake and baseline workflow."
        else:
            next_action = f"Continue the governed {phase.lower()} workflow."

        stage_value = current_stage.id if current_stage else (gate_value or phase)
        step_value = current_step.name if current_step else (current_event.event_type if current_event else run.phase_status)
        gate_id = gate_value.split()[0] if gate_value and gate_value.split()[0].startswith("G") else None
        gate_state = gate_value.split()[1] if gate_value and len(gate_value.split()) > 1 else ("pending" if gate_pending else gate_value)
        failed_command = next((item for item in reversed(commands) if str(item.status).lower() in {"failed", "timed_out", "rejected", "interrupted"}), None)
        blocker_phase = "runtime_resolution" if execution_profile is not None and execution_profile.status == "blocked" else (phase.lower().replace(" ", "_") if blocker_value else None)
        proposals = build_next_step_proposals(run_id=run_id, gate_id=gate_id, gate_state=gate_state, blocker_phase=blocker_phase, terminal=terminal, waiting_reason=waiting_reason, command_failed=failed_command is not None)
        failure_classification = failure_value or blocker_value
        latest_command = commands[-1] if commands else None
        return AssistantWorkflowProjectionDto(
            application_name=_value(_application_name(run.source_path)),
            run_id=run_id,
            current_angular_version=_value(run.source_angular_version),
            target_angular_version=_value(run.target_angular_version),
            node_execution_profile=_value((run.workspace_aliases or {}).get("NODE_EXECUTION_PROFILE")),
            package_manager=_value((run.run_policy_snapshot or {}).get("package_manager")),
            migration_route=_value((run.target_policy_snapshot or {}).get("migration_route")),
            stage_workspace_reference=_value((run.workspace_aliases or {}).get("STAGE_SANDBOX")),
            source_fingerprint=_value((run.run_policy_snapshot or {}).get("source_fingerprint")),
            stage_fingerprint=_value(None, supported=False),
            phase=_value(phase),
            stage=_value(stage_value),
            step=_value(step_value),
            gate=_value(gate_value),
            current_gate_id=_value(gate_id, supported=gate_id is not None),
            gate_state=_value(gate_state, supported=gate_state is not None),
            status=_value(run.status),
            completed_work=completed_work,
            remaining_work=remaining_work,
            blocker=_value(blocker_value or "none"),
            waiting_reason=_value(waiting_reason),
            failure_reason=_value(failure_value),
            failure_classification=_value(failure_classification, supported=failure_classification is not None),
            repair_state=_value(run.repair_status),
            next_permitted_action=_value(next_action),
            next_step_proposals=proposals,
            latest_command_result=_value({"command_key": latest_command.command_id or latest_command.executable, "status": latest_command.status, "exit_code": latest_command.exit_code, "failure_code": latest_command.failure_code, "started_at": latest_command.started_at, "completed_at": latest_command.finished_at, "correlation_id": latest_command.correlation_id} if latest_command else None, supported=latest_command is not None),
            semantic_state_version=run.state_version,
            operational_event_sequence=current_event.sequence if current_event else 0,
            phase_duration_seconds=_value(duration, supported=duration is not None),
            stage_duration_seconds=_value(_seconds(current_stage.started_at, current_stage.completed_at) if current_stage else None, supported=current_stage is not None),
            pricing_availability=_value("available" if usage_available else None, supported=usage_available),
            workflow_state_version=run.state_version,
            operational_statistics=stats,
            evidence_references=evidence,
        )
