"""Shared, read-only semantic projection for cross-phase Assistant consumers."""

from __future__ import annotations

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
    LlmInvocationModel,
    MigrationRunModel,
    MigrationStageModel,
    StageStepModel,
    SourceSnapshotModel,
    UsageCostRecordModel,
    WorkflowEventModel,
)


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


class WorkflowProjectionService:
    """Composes persisted records without interpreting event names as truth."""

    def build(self, session, run_id: str) -> AssistantWorkflowProjectionDto:
        run = session.get(MigrationRunModel, run_id)
        if run is None:
            raise ValueError("Migration run does not exist.")
        stages = list(session.scalars(select(MigrationStageModel).where(MigrationStageModel.run_id == run_id).order_by(MigrationStageModel.stage_order)))
        steps = list(session.scalars(select(StageStepModel).where(StageStepModel.run_id == run_id).order_by(StageStepModel.id)))
        events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run_id).order_by(WorkflowEventModel.sequence)))
        commands = list(session.scalars(select(CommandExecutionModel).where(CommandExecutionModel.run_id == run_id).order_by(CommandExecutionModel.requested_at, CommandExecutionModel.id)))
        invocations = list(session.scalars(select(LlmInvocationModel).where(LlmInvocationModel.run_id == run_id).order_by(LlmInvocationModel.created_at, LlmInvocationModel.id)))
        usage = {item.invocation_id: item for item in session.scalars(select(UsageCostRecordModel).where(UsageCostRecordModel.run_id == run_id))}
        artifacts = list(session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id).order_by(ArtifactMetadataModel.created_at, ArtifactMetadataModel.id)))
        snapshot = session.scalar(select(SourceSnapshotModel).where(SourceSnapshotModel.run_id == run_id).order_by(SourceSnapshotModel.created_at.desc()))
        g02 = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == run_id).order_by(G02ApprovalModel.updated_at.desc()))
        execution_profile = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.updated_at.desc()))

        current_stage = next((item for item in reversed(stages) if item.status not in {"PASSED", "CANCELLED"}), None) or (stages[-1] if stages else None)
        current_step = next((item for item in reversed(steps) if item.status not in {"PASSED", "CANCELLED"}), None)
        current_event = events[-1] if events else None
        terminal = str(run.status).upper() in {"COMPLETED", "CANCELLED", "FAILED", "TIMED_OUT", "WORKER_LOST", "ORPHANED", "CLEANUP_FAILED"}
        end = run.updated_at if terminal else None
        duration = _seconds(run.created_at, end or (max((item.occurred_at for item in events), default=None)))
        counts: dict[str, int] = {}
        for command in commands:
            counts[command.status] = counts.get(command.status, 0) + 1
        completed = [stage.id for stage in stages if stage.status in {"PASSED", "COMPLETED"}]
        role_counts: dict[str, int] = {}
        for invocation in invocations:
            role_counts[invocation.role] = role_counts.get(invocation.role, 0) + 1
        records = [usage[item.id] for item in invocations if item.status == "completed" and item.id in usage]
        has_commands = bool(commands)
        has_invocations = bool(invocations)
        stats = AssistantOperationalStatisticsDto(
            run_start_timestamp=run.created_at,
            recorded_workflow_duration_seconds=duration,
            current_active_run_age_seconds=None if terminal else _seconds(run.created_at, datetime.now(UTC)),
            stage_durations_seconds=(stage_durations := {item.id: value for item in stages if (value := _seconds(item.started_at, item.completed_at)) is not None}) or None,
            command_totals_by_status=counts if has_commands else None,
            successful_commands=sum(value for key, value in counts.items() if key in {"succeeded", "completed"}) if has_commands else None,
            failed_commands=sum(value for key, value in counts.items() if key in {"failed", "timed_out", "rejected", "interrupted"}) if has_commands else None,
            relevant_command_ids=[item.id for item in commands],
            llm_calls_by_role=role_counts if has_invocations else None,
            input_tokens=sum(item.input_tokens for item in records) if records else None,
            output_tokens=sum(item.output_tokens for item in records) if records else None,
            total_tokens=sum(item.total_tokens for item in records) if records else None,
            input_cost_usd=sum(item.input_cost_usd for item in records) if records else None,
            output_cost_usd=sum(item.output_cost_usd for item in records) if records else None,
            total_cost_usd=sum(item.total_cost_usd for item in records) if records else None,
        )
        referenced_artifact_ids = [artifact_id for event in events for artifact_id in (event.payload.get("artifact_ids", []) if isinstance(event.payload.get("artifact_ids", []), list) else [])]
        if snapshot is not None and snapshot.status == "created":
            referenced_artifact_ids.extend(snapshot.artifact_ids or [])
        if g02 is not None and g02.status == "approved":
            referenced_artifact_ids.extend(g02.artifact_ids or [])
        if execution_profile is not None:
            referenced_artifact_ids.extend(execution_profile.artifact_ids or [])
        referenced_order = {artifact_id: index for index, artifact_id in enumerate(referenced_artifact_ids)}
        def canonical_ids(item):
            return {item.id, item.id.removeprefix("metadata-")}
        selected_artifacts = [item for item in artifacts if item.immutable and canonical_ids(item) & referenced_order.keys()]
        selected_artifacts.sort(key=lambda item: referenced_order.get(item.id, len(referenced_order)))
        evidence = [AssistantEvidenceReferenceDto(artifact_id=item.id, label=item.relative_path, checksum=item.checksum, run_id=item.run_id, stage_id=item.stage_id, category=item.artifact_type, lineage=item.owner_reference, immutable=item.immutable) for item in selected_artifacts]
        phase_labels = {"PREFLIGHT_SNAPSHOT": "Preflight Snapshot", "DISCOVERY_BASELINE": "Baseline", "FEASIBILITY_PLANNING": "Planning", "STAGED_MIGRATION": "Transformation", "FINAL_ASSURANCE": "Validation", "DELIVERY_REPORTING": "Completion"}
        completed_work = list(completed)
        if snapshot is not None and snapshot.status == "created":
            completed_work.append("Immutable source snapshot")
        if g02 is not None and g02.status == "approved":
            completed_work.append("G02 approval")
        completed_work = list(dict.fromkeys(completed_work))
        remaining_work: list[str] = []
        current_gate = run.approval_status if run.approval_status not in {None, "not_required"} else None
        current_stage_value = current_stage.id if current_stage else None
        current_step_value = current_step.name if current_step else None
        profile_blockers = list(execution_profile.blockers or []) if execution_profile is not None else []
        profile_guidance = list(execution_profile.guidance or []) if execution_profile is not None else []
        failed_event = next((event for event in reversed(events) if event.event_type.endswith("_FAILED")), None)
        blocker_value = profile_blockers[0] if execution_profile is not None and execution_profile.status == "blocked" and profile_blockers else None
        failure_value = failed_event.event_type if failed_event is not None else None
        next_action_value = None
        if blocker_value and profile_guidance:
            next_action_value = f"{profile_guidance[0]} Retry runtime-profile resolution."
        return AssistantWorkflowProjectionDto(
            application_name=_value(None, supported=False),
            run_id=run_id,
            current_angular_version=_value(run.source_angular_version),
            target_angular_version=_value(run.target_angular_version),
            node_execution_profile=_value((run.workspace_aliases or {}).get("NODE_EXECUTION_PROFILE"), supported=True),
            package_manager=_value((run.run_policy_snapshot or {}).get("package_manager"), supported=True),
            migration_route=_value((run.target_policy_snapshot or {}).get("migration_route"), supported=True),
            stage_workspace_reference=_value((run.workspace_aliases or {}).get("STAGE_SANDBOX"), supported=True),
            source_fingerprint=_value((run.run_policy_snapshot or {}).get("source_fingerprint"), supported=True),
            stage_fingerprint=_value(None, supported=False),
            phase=_value(phase_labels.get(run.run_phase, run.run_phase)), stage=_value(current_stage_value),
            step=_value(current_step_value), gate=_value(current_gate),
            status=_value(run.status), completed_work=completed_work,
            remaining_work=remaining_work,
            blocker=_value(blocker_value), waiting_reason=_value(None), failure_reason=_value(failure_value),
            repair_state=_value(run.repair_status), next_permitted_action=_value(next_action_value),
            workflow_state_version=run.state_version, operational_statistics=stats, evidence_references=evidence,
        )
